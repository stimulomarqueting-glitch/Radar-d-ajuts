"""Aplicació web privada del radar: tauler, expedients amb l'assistent, socis de Holded i avisos.

    python -m radar web                       # http://127.0.0.1:8000 (en local)
    docker compose up -d                      # al VPS, darrere de Caddy amb HTTPS (vegeu docs/desplegament.md)

Accés d'un sol usuari: contrasenya (PBKDF2), segon factor opcional (TOTP), galeta de sessió signada
(HttpOnly, Secure, SameSite) i límit d'intents per IP. Les peticions que modifiquen dades han de venir
del mateix origen. Sense RADAR_CONTRASENYA_HASH i RADAR_SECRET no es pot entrar.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hmac
import io
import json
import os
import re
import threading
import time
import unicodedata
import uuid
from pathlib import Path
from urllib.parse import quote, urlparse

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from .. import avisos, calendari, dades, diari, ecosistema, informe, licitacions, screening
from .. import socis as mod_socis
from ..puntuacio import puntua
from . import auth, context, exporta, ia, plantilles
from .config import Config
from .db import BaseDades
from .render import markdown_html

DIR = Path(__file__).resolve().parent
ESTATS = ["en preparació", "presentat", "concedit", "denegat", "arxivat"]
PREFIX_LICITACIO = "licitacio:"
PUBLIQUES = ("/entrar", "/static/", "/salut")
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; object-src 'none'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
CSP_INFORME = ("default-src 'none'; style-src 'unsafe-inline' https://fonts.googleapis.com; "
               "font-src https://fonts.gstatic.com; img-src data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
CSP_AVIS = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'none'; base-uri 'none'"
RE_AVIS = re.compile(r"^avis-\d{4}-\d{2}-\d{2}\.html$")
MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DOC_IDEA = "idea"


# --- Utilitats -------------------------------------------------------------------------------------

def json_script(dades_) -> Markup:
    """JSON per incrustar dins de <script type="application/json"> sense poder tancar l'etiqueta."""
    text = json.dumps(dades_, ensure_ascii=False)
    return Markup(text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))


def data_curta(valor) -> str:
    if not valor:
        return ""
    if isinstance(valor, str):
        try:
            valor = dt.date.fromisoformat(valor) if len(valor) == 10 else dt.datetime.fromisoformat(valor)
        except ValueError:
            return valor
    if isinstance(valor, dt.datetime):
        if valor.tzinfo:
            valor = valor.astimezone()
        return f"{valor:%d/%m/%Y %H:%M}"
    return f"{valor:%d/%m/%Y}"


def eur(valor) -> str:
    if not valor:
        return ""
    return f"{valor:,.0f} €".replace(",", ".")


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()[:60] or "expedient"


def seguent_segur(valor: str | None) -> str:
    """Evita redireccions obertes: només rutes locals."""
    if valor and valor.startswith("/") and not valor.startswith("//") and "\\" not in valor:
        return valor
    return "/"


def mime_real(capcalera: bytes, nom: str, declarat: str | None) -> str | None:
    """Tipus del fitxer a partir dels primers bytes (no ens fiem del que declara el navegador)."""
    if capcalera.startswith(b"%PDF"):
        return "application/pdf"
    if capcalera.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if capcalera.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if capcalera[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if capcalera[:4] == b"RIFF" and capcalera[8:12] == b"WEBP":
        return "image/webp"
    if capcalera.startswith(b"PK\x03\x04") and nom.lower().endswith(".docx"):
        return MIME_DOCX
    tipus = ia.tipus_fitxer(nom, declarat)
    if tipus == "text" and b"\x00" not in capcalera:
        return {".md": "text/markdown", ".csv": "text/csv"}.get(Path(nom).suffix.lower(), "text/plain")
    return None


class Estat:
    """Estat compartit de l'aplicació (un sol procés)."""

    def __init__(self, cfg: Config, client=None):
        self.cfg = cfg
        self.db = BaseDades(cfg.db)
        self.limit = auth.LimitIntents()
        self.client = client
        self.ocupats: set[int] = set()
        self.tasques: set[asyncio.Task] = set()
        self.revisio_en_marxa = False
        self._cat = None
        self._cat_clau = None
        self._socis: list | None = None
        self._socis_motiu = ""
        self._socis_hora = 0.0
        self._lock = threading.Lock()

    @property
    def configurada(self) -> bool:
        return bool(self.cfg.contrasenya_hash) and len(self.cfg.secret) >= 32

    def cataleg(self) -> dades.Cataleg:
        clau = tuple(sorted((p.name, p.stat().st_mtime_ns) for p in dades.DIR_DADES.glob("*.yaml")))
        with self._lock:
            if clau != self._cat_clau:
                self._cat, self._cat_clau = dades.carrega(), clau
            return self._cat

    def clients(self) -> dict[str, screening.Client]:
        return screening.carrega_clients(self.cataleg())

    def socis(self, refresca: bool = False) -> tuple[list, str]:
        with self._lock:
            if refresca or self._socis is None or time.time() - self._socis_hora > 3600:
                contactes, motiu = diari.contactes_holded()
                self._socis = mod_socis.construeix(contactes) if contactes else []
                self._socis_motiu, self._socis_hora = motiu, time.time()
            return self._socis, self._socis_motiu

    def client_ia(self):
        if self.client is None:
            import anthropic

            self.client = anthropic.AsyncAnthropic()
        return self.client

    def ia_disponible(self) -> bool:
        return self.client is not None or bool(os.environ.get("ANTHROPIC_API_KEY"))


# --- Aplicació -------------------------------------------------------------------------------------

def crea_app(cfg: Config | None = None, client=None) -> FastAPI:
    cfg = cfg or Config()
    estat = Estat(cfg, client)
    app = FastAPI(title="Radar d'ajuts Stimulo", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.radar = estat
    app.mount("/static", StaticFiles(directory=str(DIR / "static")), name="static")
    plantilles_web = Jinja2Templates(directory=str(DIR / "templates"))
    plantilles_web.env.filters.update(data=data_curta, eur=eur, md=markdown_html, json_script=json_script)
    plantilles_web.env.globals.update(NOMS_FOCUS=avisos.NOMS_FOCUS, NOMS_TIPUS=avisos.NOMS_TIPUS,
                                      missatge=screening.missatge_divisio)

    def pagina(request: Request, nom: str, seccio: str = "", status_code: int = 200, **ctx) -> HTMLResponse:
        ctx.update(usuari=getattr(request.state, "usuari", None), seccio=seccio)
        return plantilles_web.TemplateResponse(request, nom, ctx, status_code=status_code)

    def expedient_o_404(id_: int) -> dict:
        e = estat.db.expedient(id_)
        if not e:
            raise HTTPException(404, "Expedient no trobat")
        return e

    def busca_convocatoria(cat: dades.Cataleg, id_: str):
        if not id_:
            return None
        try:
            return cat.per_id(id_)
        except KeyError:
            return None

    def client_i_divisio(id_client: str, id_divisio: str):
        """Client i divisió (o None) a partir dels identificadors; 400 si no existeixen."""
        if not id_client:
            return None, None
        cl = estat.clients().get(id_client)
        if not cl:
            raise HTTPException(400, "Client desconegut")
        try:
            return cl, (cl.divisio(id_divisio) if id_divisio else None)
        except KeyError:
            raise HTTPException(400, "Divisió desconeguda")

    def context_expedient(cat, c, titol: str, idea: str, socis: list[dict], client: dict | None) -> str:
        bloc = ""
        if client:
            cl, dv = client_i_divisio(client.get("id", ""), client.get("divisio", ""))
            bloc = screening.context_client(cl, dv)
        return context.construeix(cat, c, titol, idea, socis, dt.date.today(), bloc)

    def convocatoria_o_400(cat: dades.Cataleg, id_: str):
        c = busca_convocatoria(cat, id_)
        if not c:
            raise HTTPException(400, "Convocatòria desconeguda")
        return c

    # --- Seguretat
    def mateix_origen(request: Request) -> bool:
        origen = request.headers.get("origin") or request.headers.get("referer")
        if not origen or origen == "null":
            return False
        return urlparse(origen).netloc == request.headers.get("host", "")

    @app.middleware("http")
    async def seguretat(request: Request, call_next):
        ruta = request.url.path
        if request.method not in ("GET", "HEAD", "OPTIONS") and not mateix_origen(request):
            return PlainTextResponse("Origen de la petició no permès.", status_code=403)
        usuari = None
        if estat.configurada:
            usuari = auth.valida_sessio(cfg.secret, request.cookies.get(auth.NOM_COOKIE))
            if usuari and not hmac.compare_digest(usuari, cfg.usuari):
                usuari = None
        request.state.usuari = usuari
        if not usuari and not ruta.startswith(PUBLIQUES):
            if request.method == "GET":
                desti = ruta + (f"?{request.url.query}" if request.url.query else "")
                return RedirectResponse("/entrar?seguent=" + quote(desti, safe=""), status_code=303)
            return PlainTextResponse("Cal iniciar sessió.", status_code=401)
        resposta = await call_next(request)
        h = resposta.headers
        h.setdefault("Content-Security-Policy", CSP)
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "same-origin")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        h.setdefault("X-Robots-Tag", "noindex, nofollow")
        if cfg.cookie_segura:
            h.setdefault("Strict-Transport-Security", "max-age=31536000")
        if not ruta.startswith("/static/"):
            h.setdefault("Cache-Control", "no-store")
        return resposta

    @app.get("/salut", response_class=PlainTextResponse)
    def salut():
        return "ok"

    # --- Accés
    @app.get("/entrar", response_class=HTMLResponse)
    def entrar_form(request: Request, seguent: str = "/"):
        if request.state.usuari:
            return RedirectResponse(seguent_segur(seguent), status_code=303)
        return pagina(request, "entrar.html", seguent=seguent_segur(seguent), totp=bool(cfg.totp_secret),
                      configurada=estat.configurada, error="")

    @app.post("/entrar", response_class=HTMLResponse)
    def entrar(request: Request, usuari: str = Form(""), contrasenya: str = Form(""), codi: str = Form(""),
               seguent: str = Form("/")):
        ip = request.client.host if request.client else "?"
        ctx = dict(seguent=seguent_segur(seguent), totp=bool(cfg.totp_secret), configurada=estat.configurada)
        if not estat.configurada:
            return pagina(request, "entrar.html", status_code=503, error="L'accés encara no està configurat.", **ctx)
        if estat.limit.bloquejat(ip):
            return pagina(request, "entrar.html", status_code=429,
                          error="Massa intents fallits. Torna-ho a provar d'aquí a 15 minuts.", **ctx)
        ok_usuari = hmac.compare_digest(usuari.strip().lower().encode(), cfg.usuari.lower().encode())
        ok_contrasenya = auth.verifica_contrasenya(contrasenya, cfg.contrasenya_hash)
        ok_codi = not cfg.totp_secret or auth.verifica_totp(cfg.totp_secret, codi.strip())
        if not (ok_usuari and ok_contrasenya and ok_codi):
            estat.limit.falla(ip)
            estat.db.registra("acces_fallit", ip)
            return pagina(request, "entrar.html", status_code=401, error="Dades d'accés incorrectes.", **ctx)
        estat.limit.reinicia(ip)
        estat.db.registra("acces", ip)
        resposta = RedirectResponse(ctx["seguent"], status_code=303)
        resposta.set_cookie(auth.NOM_COOKIE, auth.crea_sessio(cfg.secret, cfg.usuari, cfg.hores_sessio),
                            max_age=cfg.hores_sessio * 3600, httponly=True, secure=cfg.cookie_segura,
                            samesite="lax", path="/")
        return resposta

    @app.post("/sortir")
    def sortir():
        resposta = RedirectResponse("/entrar", status_code=303)
        resposta.delete_cookie(auth.NOM_COOKIE, path="/", secure=cfg.cookie_segura, httponly=True, samesite="lax")
        return resposta

    # --- Tauler
    @app.get("/", response_class=HTMLResponse)
    def tauler(request: Request):
        cat = estat.cataleg()
        oberts = {}
        for e in estat.db.expedients():  # del més recent al més antic
            if e["estat"] != "arxivat":
                oberts.setdefault(e["convocatoria_id"], e["id"])
        return pagina(request, "tauler.html", "tauler", dades=informe.dades_json(cat, dt.date.today()),
                      app={"expedients": oberts})

    # --- Expedients
    @app.get("/expedients", response_class=HTMLResponse)
    def expedients(request: Request):
        cat, avui = estat.cataleg(), dt.date.today()
        files = []
        for e in estat.db.expedients():
            c = busca_convocatoria(cat, e["convocatoria_id"])
            f = calendari.propera_finestra(c, avui) if c else None
            if e["convocatoria_id"].startswith(PREFIX_LICITACIO):
                lic = estat.db.licitacio(e["convocatoria_id"][len(PREFIX_LICITACIO):])
                e = {**e, "licitacio": lic}
            files.append({"e": e, "c": c, "f": f, "docs": len(estat.db.documents_actuals(e["id"])),
                          "dies": (f.tancament - avui).days if f and f.estat == "oberta" and f.tancament else None})
        return pagina(request, "expedients.html", "expedients", files=files)

    @app.get("/expedients/nou", response_class=HTMLResponse)
    def expedient_nou(request: Request, convocatoria: str = "", client: str = "", divisio: str = ""):
        cat, avui = estat.cataleg(), dt.date.today()
        c = busca_convocatoria(cat, convocatoria)
        cl, dv = client_i_divisio(client, divisio)
        llista = sorted(cat.convocatories, key=lambda x: x.nom.lower())
        propostes, motiu, linia, encaix_client, idees = [], "", None, None, []
        if c:
            linia = avisos.linia(cat, c, avui)
            socis, motiu = estat.socis()
            propostes = mod_socis.proposa(c, socis, cat.zones, maxim=8) if socis else []
            if dv:
                encaix_client = puntua(c, dv.perfil, cat.zones, cat.config.get("pesos"))
                idees = screening._idees(c, dv, maxim=3)
        return pagina(request, "expedient_nou.html", "clients" if cl else "expedients", c=c, llista=llista,
                      linia=linia, propostes=propostes, motiu_socis=motiu, zones=cat.zones, cl=cl, dv=dv,
                      encaix_client=encaix_client, idees=idees)

    @app.post("/expedients")
    def crea_expedient(request: Request, convocatoria: str = Form(...), titol: str = Form(""), idea: str = Form(""),
                       socis: list[str] = Form(default=[]), socis_extra: str = Form(""), client: str = Form(""),
                       divisio: str = Form("")):
        cat = estat.cataleg()
        c = convocatoria_o_400(cat, convocatoria)
        cl, dv = client_i_divisio(client, divisio)
        dades_client = {"id": cl.id, "nom": cl.nom, "divisio": dv.id if dv else "",
                        "divisio_nom": dv.nom if dv else ""} if cl else None
        triats = []
        if socis:
            llista, _ = estat.socis()
            per_clau = {p.soci.clau: p for p in mod_socis.proposa(c, llista, cat.zones, maxim=50)}
            per_clau_soci = {s.clau: s for s in llista}
            for clau in socis:
                s = per_clau_soci.get(clau)
                if not s:
                    continue
                dest = s.destinatari or {}
                contacte = " ".join(filter(None, [dest.get("nom", ""), f"<{dest['email']}>" if dest.get("email") else ""]))
                triats.append({"nom": s.nom, "tipus": s.tipus, "relacio": s.relacio, "zona": s.zona,
                               "focus": s.focus, "contacte": contacte, "nota": s.nota,
                               "rol": per_clau[clau].rol if clau in per_clau else ""})
        for linia in socis_extra.splitlines():
            if linia.strip():
                triats.append({"nom": linia.strip()[:200], "tipus": "", "relacio": "afegit a mà", "focus": []})
        titol = (titol.strip() or (f"{cl.nom} · {c.nom}" if cl else c.nom))[:200]
        idea = idea.strip()[:8000]
        sistema = context_expedient(cat, c, titol, idea, triats, dades_client)
        id_ = estat.db.crea_expedient(c.id, titol, idea, triats, sistema, dades_client)
        estat.db.registra("expedient_creat", json.dumps({"id": id_, "convocatoria": c.id,
                                                         "client": dades_client["id"] if dades_client else ""}))
        return RedirectResponse(f"/expedients/{id_}", status_code=303)

    @app.get("/expedients/{id_}", response_class=HTMLResponse)
    def expedient(request: Request, id_: int):
        e = expedient_o_404(id_)
        cat, avui = estat.cataleg(), dt.date.today()
        lic = None
        if e["convocatoria_id"].startswith(PREFIX_LICITACIO):
            lic = estat.db.licitacio(e["convocatoria_id"][len(PREFIX_LICITACIO):])
        ambit = "licitacio" if e["convocatoria_id"].startswith(PREFIX_LICITACIO) else "ajut"
        c = busca_convocatoria(cat, e["convocatoria_id"]) if ambit == "ajut" else None
        f = calendari.propera_finestra(c, avui) if c else None
        missatges = [m for m in estat.db.missatges(id_) if m["rol"] in ("user", "assistant") and m["visible"].strip()]
        documents = estat.db.documents_actuals(id_)
        fets = {d["tipus"] for d in documents}
        propies = plantilles.per_ambit(ambit)
        return pagina(request, "expedient.html", "licitacions" if lic else "expedients", e=e, c=c, f=f, lic=lic,
                      missatges=missatges, documents=documents, fitxers=estat.db.fitxers(id_), plantilles=propies,
                      estats=ESTATS, ia_disponible=estat.ia_disponible(), ocupat=id_ in estat.ocupats,
                      mida_max=cfg.mida_max_fitxer_mb, tipus_acceptats=".pdf,.docx,.txt,.md,.csv,.png,.jpg,.jpeg,.webp,.gif",
                      app={"id": id_, "pendents": [t for t in plantilles.SEQUENCIES[ambit] if t not in fets],
                           "titols": {p.tipus: p.titol for p in propies}})

    @app.post("/expedients/{id_}")
    def actualitza_expedient(id_: int, titol: str = Form(None), estat_: str = Form(None, alias="estat"),
                             idea: str = Form(None)):
        e = expedient_o_404(id_)
        canvis = {}
        if titol is not None and titol.strip():
            canvis["titol"] = titol.strip()[:200]
        if estat_ in ESTATS:
            canvis["estat"] = estat_
        if idea is not None and idea.strip() != e["idea"]:
            canvis["idea"] = idea.strip()[:8000]
            if not estat.db.missatges(id_) and not e["convocatoria_id"].startswith(PREFIX_LICITACIO):
                cat = estat.cataleg()
                c = convocatoria_o_400(cat, e["convocatoria_id"])
                estat.db.actualitza_context(id_, context_expedient(
                    cat, c, canvis.get("titol", e["titol"]), canvis["idea"], e["socis"], e["client"]))
            else:  # la conversa ja ha començat: arriba a l'assistent com a document editat
                estat.db.desa_document(id_, DOC_IDEA, "Idea del projecte", canvis["idea"], origen="edició manual")
        estat.db.actualitza_expedient(id_, **canvis)
        return RedirectResponse(f"/expedients/{id_}", status_code=303)

    @app.post("/expedients/{id_}/xat")
    async def xat(request: Request, id_: int):
        e = expedient_o_404(id_)
        try:
            cos = await request.json()
        except ValueError:
            raise HTTPException(400, "Cos de la petició no vàlid")
        text = str(cos.get("text", ""))[:20000]
        accio = str(cos.get("accio", ""))
        if accio and accio not in plantilles.PER_TIPUS:
            raise HTTPException(400, "Document desconegut")
        if not accio and not text.strip():
            raise HTTPException(400, "Escriu un missatge")
        if not estat.ia_disponible():
            return PlainTextResponse("Falta ANTHROPIC_API_KEY al servidor: l'assistent no està disponible.",
                                     status_code=503)
        if id_ in estat.ocupats:
            return PlainTextResponse("L'assistent ja està treballant en aquest expedient. Espera que acabi.",
                                     status_code=409)
        estat.ocupats.add(id_)
        cua: asyncio.Queue = asyncio.Queue()

        async def executa():
            try:
                async for ev in ia.torn(estat.db, cfg, e, text, accio, client=estat.client_ia()):
                    await cua.put(ev)
            except Exception as ex:  # no es perd mai el final del flux
                await cua.put({"tipus": "error", "text": f"Error inesperat ({type(ex).__name__})."})
            finally:
                estat.ocupats.discard(id_)
                await cua.put(None)

        # El torn continua encara que es tanqui el navegador: la resposta es desa igualment
        tasca = asyncio.create_task(executa())
        estat.tasques.add(tasca)
        tasca.add_done_callback(estat.tasques.discard)

        async def flux():
            while True:
                try:
                    ev = await asyncio.wait_for(cua.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": treballant\n\n"
                    continue
                if ev is None:
                    return
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

        return StreamingResponse(flux(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @app.post("/expedients/{id_}/fitxers")
    async def puja_fitxer(id_: int, fitxer: UploadFile = File(...)):
        expedient_o_404(id_)
        nom = Path(fitxer.filename or "fitxer").name[:150]
        maxim = cfg.mida_max_fitxer_mb * 1024 * 1024
        contingut = await fitxer.read(maxim + 1)
        if len(contingut) > maxim:
            raise HTTPException(413, f"El fitxer supera els {cfg.mida_max_fitxer_mb} MB")
        if not contingut:
            raise HTTPException(400, "Fitxer buit")
        mime = mime_real(contingut[:16], nom, fitxer.content_type)
        if not mime:
            raise HTTPException(415, "Tipus de fitxer no admès: PDF, Word (.docx), text, Markdown, CSV o imatges")
        desti = cfg.dir_fitxers / str(id_)
        desti.mkdir(parents=True, exist_ok=True)
        ruta = desti / (uuid.uuid4().hex + Path(nom).suffix.lower()[:10])
        ruta.write_bytes(contingut)
        estat.db.afegeix_fitxer(id_, nom, str(ruta), mime, len(contingut))
        return RedirectResponse(f"/expedients/{id_}#fitxers", status_code=303)

    @app.post("/expedients/{id_}/fitxers/{fid}/esborra")
    def esborra_fitxer(id_: int, fid: int):
        expedient_o_404(id_)
        f = estat.db.fitxer(id_, fid)
        if f:
            estat.db.esborra_fitxer(id_, fid)
            ruta = Path(f["ruta"])
            if ruta.is_relative_to(cfg.dir_fitxers):
                ruta.unlink(missing_ok=True)
        return RedirectResponse(f"/expedients/{id_}#fitxers", status_code=303)

    @app.get("/expedients/{id_}/documents/{tipus}", response_class=HTMLResponse)
    def document(request: Request, id_: int, tipus: str, versio: int | None = None, edita: bool = False):
        e = expedient_o_404(id_)
        d = estat.db.document(id_, tipus, versio)
        if not d:
            raise HTTPException(404, "Document no trobat")
        return pagina(request, "document.html", "expedients", e=e, d=d, versions=estat.db.versions(id_, tipus),
                      edita=edita)

    @app.post("/expedients/{id_}/documents/{tipus}")
    def desa_document(id_: int, tipus: str, contingut: str = Form(...)):
        e = expedient_o_404(id_)
        actual = estat.db.document(id_, tipus)
        if not actual:
            raise HTTPException(404, "Document no trobat")
        contingut = contingut.replace("\r\n", "\n").strip()
        if contingut and contingut != actual["contingut"]:
            estat.db.desa_document(id_, tipus, actual["titol"], contingut, origen="edició manual")
            if tipus == DOC_IDEA:
                estat.db.actualitza_expedient(id_, idea=contingut)
        return RedirectResponse(f"/expedients/{e['id']}/documents/{tipus}", status_code=303)

    @app.get("/expedients/{id_}/exporta.docx")
    def exporta_docx(id_: int):
        e = expedient_o_404(id_)
        c = busca_convocatoria(estat.cataleg(), e["convocatoria_id"])
        contingut = exporta.docx(e, c.nom if c else e["convocatoria_id"], estat.db.documents_actuals(id_))
        return Response(contingut, media_type=MIME_DOCX,
                        headers={"Content-Disposition": f'attachment; filename="{slug(e["titol"])}.docx"'})

    @app.get("/expedients/{id_}/exporta.zip")
    def exporta_zip(id_: int):
        e = expedient_o_404(id_)
        return Response(exporta.zip_markdown(estat.db.documents_actuals(id_)), media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{slug(e["titol"])}.zip"'})

    # --- Clients de servei (screening per divisions)
    @app.get("/clients", response_class=HTMLResponse)
    def clients_pagina(request: Request):
        cat, avui = estat.cataleg(), dt.date.today()
        files = []
        for cl in estat.clients().values():
            sc = screening.screening(cat, cl, avui)
            files.append({"cl": cl, "sc": sc, "xifres": screening.xifres(sc),
                          "expedients": [e for e in estat.db.expedients() if (e["client"] or {}).get("id") == cl.id]})
        return pagina(request, "clients.html", "clients", files=files)

    @app.get("/clients/{id_}/informe", response_class=HTMLResponse)
    def client_informe(id_: str, divisio: list[str] = Query(default=[]), descarrega: bool = False):
        cl = estat.clients().get(id_)
        if not cl:
            raise HTTPException(404, "Client no trobat")
        cat, avui = estat.cataleg(), dt.date.today()
        sc = screening.screening(cat, cl, avui, divisio or None)
        cos = screening.informe_html(sc, app=not descarrega)
        pagina_html = ('<!doctype html><html lang="ca"><head><meta charset="utf-8">'
                       '<meta name="viewport" content="width=device-width, initial-scale=1">'
                       + cos.replace("</style>", "</style></head><body>", 1) + "</body></html>")
        capcaleres = {"Content-Security-Policy": CSP_INFORME}
        if descarrega:
            capcaleres["Content-Disposition"] = f'attachment; filename="screening-{slug(cl.nom)}-{avui:%Y-%m-%d}.html"'
        return HTMLResponse(pagina_html, headers=capcaleres)

    # --- Licitacions: detecció, decisió go/no-go i oferta
    def licitacio_o_404(id_: str) -> dict:
        r = estat.db.licitacio(id_)
        if not r:
            raise HTTPException(404, "Licitació no trobada")
        return r

    def amb_dies(r: dict, avui: dt.date) -> dict:
        termini = r["dades"].get("termini")
        return {**r, "dies": (dt.date.fromisoformat(termini) - avui).days if termini else None}

    @app.get("/licitacions", response_class=HTMLResponse)
    def licitacions_pagina(request: Request, estat_: str = Query("", alias="estat"), semafor: str = "",
                           q: str = "", missatge: str = ""):
        avui = dt.date.today()
        totes = [amb_dies(r, avui) for r in estat.db.licitacions()]
        files = totes
        if estat_ == "actives":
            files = [r for r in files if r["estat"] in ("nova", "en anàlisi", "go")
                     and (r["dies"] is None or r["dies"] >= 0)]
        elif estat_:
            files = [r for r in files if r["estat"] == estat_]
        if semafor:
            files = [r for r in files if r["avaluacio"]["semafor"] == semafor]
        if q.strip():
            nq = licitacions.normalitza(q)
            files = [r for r in files if nq in licitacions.normalitza(f"{r['dades']['titol']} {r['dades']['organ']}")]
        ordre = {"verd": 0, "groc": 1, "vermell": 2, "gris": 3}
        files.sort(key=lambda r: (r["dies"] is not None and r["dies"] < 0, ordre.get(r["avaluacio"]["semafor"], 9),
                                  r["dies"] if r["dies"] is not None else 9999))
        compte = {e: sum(1 for r in totes if r["estat"] == e) for e in licitacions.ESTATS}
        urgents = sum(1 for r in totes if r["estat"] in licitacions.ESTATS_ACTIUS and r["dies"] is not None
                      and 0 <= r["dies"] <= 7)
        return pagina(request, "licitacions.html", "licitacions", files=files, compte=compte, urgents=urgents,
                      filtre={"estat": estat_, "semafor": semafor, "q": q}, estats=licitacions.ESTATS,
                      en_marxa=estat.revisio_en_marxa, missatge=missatge[:200], avui=avui)

    @app.post("/licitacions/cerca")
    def licitacions_cerca():
        if estat.revisio_en_marxa:
            return RedirectResponse("/licitacions?missatge=" + quote("Ja hi ha una cerca en marxa."), status_code=303)
        estat.revisio_en_marxa = True

        def cerca():
            try:
                r = licitacions.executa(estat.cataleg(), dt.date.today(), dades.ARREL / "sortida",
                                        dades.ARREL / "data" / "estat" / "licitacions-vistes.json", estat.db)
                estat.db.registra("licitacions_cerca", json.dumps(
                    {"llegides": r["totes"], "rellevants": r["rellevants"], "noves": len(r["noves"]),
                     "errors": r["errors"]}, ensure_ascii=False))
            except Exception as ex:
                estat.db.registra("licitacions_cerca", json.dumps({"errors": {"general": type(ex).__name__}}))
            finally:
                estat.revisio_en_marxa = False

        threading.Thread(target=cerca, daemon=True).start()
        return RedirectResponse("/licitacions?missatge=" + quote("Cerca en marxa: recarrega d'aquí a un minut."),
                                status_code=303)

    @app.post("/licitacions/nova")
    def licitacio_nova(titol: str = Form(...), organ: str = Form(""), url: str = Form(""), expedient: str = Form(""),
                       termini: str = Form(""), import_eur: str = Form(""), cpv: str = Form(""),
                       procediment: str = Form("")):
        avui = dt.date.today()
        if url and not url.startswith(("http://", "https://")):
            raise HTTPException(400, "L'enllaç ha de començar per http:// o https://")
        lic = licitacions.Licitacio(
            id=f"manual:{slug(titol)[:40]}-{dt.datetime.now():%Y%m%d%H%M%S}", font="manual", titol=titol.strip()[:300],
            organ=organ.strip()[:200], url=url.strip()[:500], expedient=expedient.strip()[:80],
            procediment=procediment.strip()[:80], cpv=licitacions._cpvs(cpv), import_eur=licitacions._num(import_eur),
            termini=licitacions._data(termini), lloc="")
        av = licitacions.avalua(lic, licitacions.config(estat.cataleg()), avui)
        estat.db.desa_licitacio(lic.a_dict(), av.a_dict())
        estat.db.actualitza_licitacio(lic.id, estat="en anàlisi")
        return RedirectResponse("/licitacio?id=" + quote(lic.id, safe=""), status_code=303)

    @app.get("/licitacio", response_class=HTMLResponse)
    def licitacio_detall(request: Request, id: str):
        r = amb_dies(licitacio_o_404(id), dt.date.today())
        lic = licitacions.Licitacio.de_dict(r["dades"])
        av = licitacions.Avaluacio(**r["avaluacio"])
        resum = (f"{lic.titol}\n{lic.organ}\nImport: {licitacions.eur(lic.import_eur or lic.valor_estimat)} · "
                 f"Termini: {lic.termini:%d/%m/%Y}" if lic.termini else f"{lic.titol}\n{lic.organ}")
        resum += f"\nRadar: {av.recomanacio} ({av.punts}/100) · Estat: {r['estat']}\n{lic.url}"
        return pagina(request, "licitacio.html", "licitacions", r=r, lic=lic, av=av, estats=licitacions.ESTATS,
                      resum=resum, fitxa=licitacions.fitxa_decisio(lic, av, r))

    @app.post("/licitacio")
    def licitacio_actualitza(id: str, estat_: str = Form("", alias="estat"), responsable: str = Form(""),
                             motiu: str = Form(""), notes: str = Form("")):
        licitacio_o_404(id)
        canvis = {"responsable": responsable.strip()[:100], "motiu": motiu.strip()[:1000], "notes": notes.strip()[:8000]}
        if estat_ in licitacions.ESTATS:
            canvis["estat"] = estat_
        estat.db.actualitza_licitacio(id, **canvis)
        estat.db.registra("licitacio_decisio", json.dumps({"id": id, "estat": estat_}, ensure_ascii=False))
        return RedirectResponse("/licitacio?id=" + quote(id, safe=""), status_code=303)

    @app.get("/licitacio/fitxa.docx")
    def licitacio_fitxa_docx(id: str):
        r = licitacio_o_404(id)
        lic = licitacions.Licitacio.de_dict(r["dades"])
        md = licitacions.fitxa_decisio(lic, licitacions.Avaluacio(**r["avaluacio"]), r)
        import docx as python_docx

        document = python_docx.Document()
        exporta.markdown_a_docx(document, md)
        sortida = io.BytesIO()
        document.save(sortida)
        return Response(sortida.getvalue(), media_type=MIME_DOCX,
                        headers={"Content-Disposition": f'attachment; filename="fitxa-{slug(lic.titol)}.docx"'})

    @app.post("/licitacio/expedient")
    def licitacio_expedient(id: str):
        r = licitacio_o_404(id)
        if r["expedient_id"] and estat.db.expedient(r["expedient_id"]):
            return RedirectResponse(f"/expedients/{r['expedient_id']}", status_code=303)
        titol = f"Oferta: {r['dades']['titol']}"[:200]
        sistema = context.construeix_licitacio(estat.cataleg(), r["dades"], r["avaluacio"], titol, "", dt.date.today())
        id_exp = estat.db.crea_expedient(PREFIX_LICITACIO + id, titol, "", [], sistema)
        estat.db.actualitza_licitacio(id, expedient_id=id_exp,
                                      **({"estat": "en anàlisi"} if r["estat"] == "nova" else {}))
        return RedirectResponse(f"/expedients/{id_exp}", status_code=303)

    # --- Ecosistema de defensa, ús dual i espai
    @app.get("/ecosistema", response_class=HTMLResponse)
    def ecosistema_pagina(request: Request):
        cat, avui = estat.cataleg(), dt.date.today()
        eco = ecosistema.carrega(cat)
        linies = []
        for c in cat.convocatories:
            if set(c.focus) & ecosistema.AMBITS_SECTOR:
                f = calendari.propera_finestra(c, avui)
                if f.estat not in ("tancada", "sense_dades"):
                    linies.append({"c": c, "f": f, "e": avisos.linia(cat, c, avui).e})
        linies.sort(key=lambda x: -x["e"].punts)
        actors = sorted(eco.actors, key=lambda a: (ecosistema.TIPUS_ACTOR.index(a.tipus), a.nom))
        return pagina(request, "ecosistema.html", "ecosistema", trobades=ecosistema.trobades_actives(eco, avui),
                      actors=actors, requisits=eco.requisits, linies=linies, avui=avui,
                      NOMS=ecosistema.NOMS_TIPUS)

    # --- Socis (Holded)
    @app.get("/socis", response_class=HTMLResponse)
    def socis_pagina(request: Request, convocatoria: str = ""):
        cat, avui = estat.cataleg(), dt.date.today()
        llista, motiu = estat.socis()
        c = busca_convocatoria(cat, convocatoria)
        esborranys = []
        if c and llista:
            lin = avisos.linia(cat, c, avui)
            cfg_avisos = {**avisos.CONFIG_PER_DEFECTE, **cat.config.get("avisos", {})}
            for p in mod_socis.proposa(c, llista, cat.zones, maxim=8):
                d = avisos.esborrany(lin, p, cfg_avisos["signatura"])
                esborranys.append({"p": p, "d": d, "mailto": avisos._mailto(d) if d["per_a"] else ""})
        ordenats = sorted(llista, key=lambda s: (s.tipus, s.nom.lower()))
        return pagina(request, "socis.html", "socis", socis=ordenats, motiu=motiu, c=c, esborranys=esborranys,
                      llista=sorted(cat.convocatories, key=lambda x: x.nom.lower()), zones=cat.zones)

    @app.post("/socis/actualitza")
    def socis_actualitza():
        estat.socis(refresca=True)
        return RedirectResponse("/socis", status_code=303)

    # --- Avisos i revisió diària
    dir_avisos = dades.ARREL / "privat" / "avisos"

    @app.get("/avisos", response_class=HTMLResponse)
    def avisos_pagina(request: Request, missatge: str = ""):
        fitxers = sorted((p.name for p in dir_avisos.glob("avis-*.html") if RE_AVIS.match(p.name)), reverse=True) \
            if dir_avisos.exists() else []
        events = [ev for ev in estat.db.esdeveniments(80) if ev["tipus"].startswith("revisio")]
        for ev in events:
            try:
                ev["dades"] = json.loads(ev["detall"])
            except ValueError:
                ev["dades"] = {"missatge": ev["detall"]}
        return pagina(request, "avisos.html", "avisos", fitxers=fitxers[:60], events=events[:20],
                      en_marxa=estat.revisio_en_marxa, missatge=missatge[:200],
                      hora=os.environ.get("RADAR_HORA", "07:30"), smtp=avisos.smtp_configurat())

    @app.post("/avisos/revisio")
    def avisos_revisio(envia: str = Form("")):
        if estat.revisio_en_marxa:
            return RedirectResponse("/avisos?missatge=" + quote("Ja hi ha una revisió en marxa."), status_code=303)
        estat.revisio_en_marxa = True

        def revisio():
            try:
                r = diari.executa_diari(dt.date.today(), envia=bool(envia), path_db=cfg.db)
                estat.db.registra("revisio_manual", json.dumps(
                    {"assumpte": r.assumpte, "missatge": r.missatge, "linies": r.linies, "novetats": r.novetats,
                     "recordatoris": r.recordatoris, "errors": list(r.errors)}, ensure_ascii=False))
            except Exception as ex:
                estat.db.registra("revisio_manual", json.dumps({"missatge": f"Error: {type(ex).__name__}"}))
            finally:
                estat.revisio_en_marxa = False

        threading.Thread(target=revisio, daemon=True).start()
        text = "Revisió en marxa" + (" (s'enviarà el correu si hi ha novetats)." if envia else " (vista prèvia).")
        return RedirectResponse("/avisos?missatge=" + quote(text), status_code=303)

    @app.get("/avisos/{nom}", response_class=HTMLResponse)
    def avis(nom: str):
        if not RE_AVIS.match(nom) or not (dir_avisos / nom).is_file():
            raise HTTPException(404, "Avís no trobat")
        return HTMLResponse((dir_avisos / nom).read_text(encoding="utf-8"),
                            headers={"Content-Security-Policy": CSP_AVIS})

    # --- Configuració
    @app.get("/configuracio", response_class=HTMLResponse)
    def configuracio(request: Request):
        cat = estat.cataleg()
        return pagina(request, "configuracio.html", "configuracio", cfg=cfg, problemes=cfg.problemes(),
                      smtp=avisos.smtp_configurat(), destinatari=os.environ.get("RADAR_DESTINATARI", ""),
                      holded=bool(os.environ.get("HOLDED_API_KEY")) or (dades.ARREL / "privat" / "holded_contactes.json").exists(),
                      hora=os.environ.get("RADAR_HORA", "07:30"), n_convocatories=len(cat.convocatories),
                      events=estat.db.esdeveniments(30))

    return app
