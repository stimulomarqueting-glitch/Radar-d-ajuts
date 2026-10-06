"""Screening d'ajuts per a un client de Stimulo, divisió per divisió.

    python -m radar screening doga                    # informe a privat/clients/doga/
    python -m radar screening doga --divisio motors   # només una divisió

Cada divisió del client (data/clients/<id>.yaml, o privat/clients/<id>.yaml si hi és) es puntua
com un perfil del radar. Per a cada divisió en surt una llista curta d'oportunitats elegibles amb la
idea de projecte que hi encaixa, el paper de Stimulo i el que cal tenir en compte. L'entrega és un
informe HTML sense JavaScript (es pot obrir, imprimir o publicar tal qual), un Markdown i un
calendari .ics amb les senyals per al client.
"""

from __future__ import annotations

import datetime as dt
import html
import json
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import yaml

from . import calendari, ecosistema, ics
from .dades import ARREL, DIR_DADES, FOCUS, Cataleg, Convocatoria, ErrorValidacio, Perfil, _perfil
from .puntuacio import Encaix, puntua
from .socis import tipus_necessaris

NOMS_FOCUS = {
    "deep_tech": "deep tech", "dual": "ús dual", "defensa": "defensa", "espai": "espai",
    "sostenibilitat": "sostenibilitat", "economia_circular": "economia circular", "transferencia": "transferència",
    "prova_concepte": "prova de concepte", "mobilitat": "mobilitat", "automocio": "automoció",
    "robotica": "robòtica", "agrotech": "agrotech", "aigua": "aigua", "salut": "salut",
    "dispositius_medics": "dispositius mèdics", "fotonica": "fotònica", "digital": "digital", "ia": "IA",
    "industria": "indústria", "energia": "energia", "internacionalitzacio": "internacionalització",
    "creixement_startup": "creixement de startups", "talent": "talent", "disseny": "disseny",
    "cooperacio": "cooperació",
}
NOMS_SOCI = {"recerca": "universitat o centre de recerca", "hospital": "hospital o institut sanitari",
             "empresa": "empresa", "startup": "startup", "cluster": "clúster", "inversor": "inversor"}
MESOS = ["gen", "febr", "març", "abr", "maig", "juny", "jul", "ag", "set", "oct", "nov", "des"]
DIR_CLIENTS = DIR_DADES / "clients"
DIR_CLIENTS_PRIVAT = ARREL / "privat" / "clients"


# --- Model ----------------------------------------------------------------------------------------

@dataclass
class Idea:
    titol: str
    focus: list[str]
    stimulo: str = ""


@dataclass
class Divisio:
    id: str
    nom: str
    descripcio: str
    mercats: list[str]
    perfil: Perfil
    idees: list[Idea]


@dataclass
class Client:
    id: str
    nom: str
    rao_social: str
    web: str
    zona: str
    ubicacio: str
    mida: str
    contacte: str
    descripcio: str
    estat_dades: str
    consideracions: list[str]
    preguntes: list[str]
    fonts: list[str]
    divisions: list[Divisio]

    def divisio(self, id_: str) -> Divisio:
        for d in self.divisions:
            if d.id == id_:
                return d
        raise KeyError(id_)


@dataclass
class Oportunitat:
    c: Convocatoria
    f: calendari.Finestra
    e: Encaix
    idees: list[Idea]
    rol_client: str
    rol_stimulo: str
    atencio: list[str]


@dataclass
class ResultatDivisio:
    divisio: Divisio
    oportunitats: list[Oportunitat]


@dataclass
class Screening:
    client: Client
    avui: dt.date
    horitzo_dies: int
    resultats: list[ResultatDivisio]
    n_convocatories: int
    matriu: list[dict] = field(default_factory=list)  # [{c, f, punts: {divisio: Encaix}}]
    sector: dict | None = None  # entrar a defensa i ús dual (divisions amb aquests temes)

    @property
    def oportunitats(self) -> list[Oportunitat]:
        vistes, sortida = set(), []
        for r in self.resultats:
            for o in r.oportunitats:
                if o.c.id not in vistes:
                    vistes.add(o.c.id)
                    sortida.append(o)
        return sortida


# --- Càrrega --------------------------------------------------------------------------------------

def _client(d: dict, cat: Cataleg) -> Client:
    id_ = d["id"]
    if not cat.zones.existeix(d["zona"]):
        raise ErrorValidacio(f"client {id_}: zona desconeguda '{d['zona']}'")
    divisions = []
    for dv in d.get("divisions", []):
        perfil = _perfil(f"{id_}-{dv['id']}", {
            "nom": f"{d['nom']} · {dv['nom']}", "tipus": "client", "zona": dv.get("zona", d["zona"]),
            "beneficiari_com": dv.get("beneficiari_com", d.get("beneficiari_com", [])),
            "rols": dv.get("rols", d.get("rols", ["beneficiari"])), "focus": dv.get("focus", {}),
            "trl": dv.get("trl"), "descripcio": dv.get("descripcio", ""), "paraules_clau": dv.get("paraules_clau", []),
        }, cat.zones)
        idees = []
        for i in dv.get("idees", []):
            for f_ in i.get("focus", []):
                if f_ not in FOCUS:
                    raise ErrorValidacio(f"client {id_}, divisió {dv['id']}: tema desconegut '{f_}' a una idea")
            idees.append(Idea(i["titol"], list(i.get("focus", [])), i.get("stimulo", "")))
        divisions.append(Divisio(dv["id"], dv["nom"], " ".join(dv.get("descripcio", "").split()),
                                 list(dv.get("mercats", [])), perfil, idees))
    if not divisions:
        raise ErrorValidacio(f"client {id_}: cal com a mínim una divisió")
    return Client(id_, d["nom"], d.get("rao_social", d["nom"]), d.get("web", ""), d["zona"], d.get("ubicacio", ""),
                  d.get("mida", ""), d.get("contacte", ""), " ".join(d.get("descripcio", "").split()),
                  d.get("estat_dades", ""), list(d.get("consideracions", [])), list(d.get("preguntes", [])),
                  list(d.get("fonts", [])), divisions)


def carrega_clients(cat: Cataleg, dirs: tuple[Path, ...] = (DIR_CLIENTS, DIR_CLIENTS_PRIVAT)) -> dict[str, Client]:
    """Clients de servei. Un fitxer a privat/clients/ substitueix el del mateix id a data/clients/."""
    brut: dict[str, dict] = {}
    for dir_ in dirs:
        if dir_.exists():
            for p in sorted(dir_.glob("*.yaml")):
                d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                if d.get("id"):
                    brut[d["id"]] = d
    return {id_: _client(d, cat) for id_, d in brut.items()}


# --- Screening ------------------------------------------------------------------------------------

def _rol_stimulo(c: Convocatoria) -> str:
    r = set(c.rols_stimulo)
    if r & {"proveidor_extern", "subcontractat"}:
        return "Proveïdor tecnològic: disseny, prototip i validació del producte."
    if r & {"soci", "beneficiari"}:
        return "Soci del projecte (pime): disseny i desenvolupament de producte."
    return "Preparació i seguiment de la sol·licitud."


def _atencio(c: Convocatoria, f: calendari.Finestra, client: Client) -> list[str]:
    a = []
    if f.estimada:
        a.append("Dates estimades a partir de l'edició anterior: cal confirmar-les quan surtin les bases.")
    if c.confianca == "baixa":
        a.append("Fitxa pendent de verificar a la font oficial.")
    if "consorci" in c.beneficiaris or c.socis_cal:
        tipus = [NOMS_SOCI.get(t, t) for t in tipus_necessaris(c)]
        a.append("Es presenta en consorci" + (f": cal sumar-hi {', '.join(tipus)}." if tipus else "."))
    if c.intensitat_max and c.instrument == "subvencio" and client.mida == "gran_empresa" \
            and c.nivell in ("catalunya", "estat", "local"):
        a.append(f"La intensitat de la fitxa ({c.intensitat_max:g} %) és la màxima; per a una gran empresa sol ser més baixa.")
    if c.instrument.startswith("prestec"):
        a.append("Finançament en forma de préstec: una part s'ha de retornar.")
    if "minimis" in f"{c.ajuda_text} {c.notes} {c.descripcio}".lower():
        a.append("Règim de minimis: cal saber quins ajuts ha rebut l'empresa en els darrers tres exercicis.")
    return a


def _idees(c: Convocatoria, d: Divisio, maxim: int = 2) -> list[Idea]:
    puntuades = [(len(set(i.focus) & set(c.focus)), n, i) for n, i in enumerate(d.idees)]
    return [i for punts, _, i in sorted(puntuades, key=lambda x: (-x[0], x[1])) if punts][:maxim]


def _dins_horitzo(f: calendari.Finestra, avui: dt.date, horitzo: int) -> bool:
    if f.estat in ("oberta", "permanent"):
        return True
    if f.estat != "propera":
        return False
    referencia = f.obertura or f.tancament
    return referencia is None or (referencia - avui).days <= horitzo


def screening(cat: Cataleg, client: Client, avui: dt.date, divisions: list[str] | None = None,
              maxim: int = 8, horitzo_dies: int = 365) -> Screening:
    pesos = cat.config.get("pesos")
    triades = [d for d in client.divisions if not divisions or d.id in divisions]
    finestres = {c.id: calendari.propera_finestra(c, avui) for c in cat.convocatories}
    resultats = []
    for d in triades:
        candidates = []
        for c in cat.convocatories:
            f = finestres[c.id]
            if not _dins_horitzo(f, avui, horitzo_dies):
                continue
            e = puntua(c, d.perfil, cat.zones, pesos)
            if e.prioritat not in ("A", "B") or not e.rol:
                continue
            candidates.append(Oportunitat(
                c, f, e, _idees(c, d),
                "Sol·licitant" if e.rol == "beneficiari" else "Soci d'un consorci",
                _rol_stimulo(c), _atencio(c, f, client)))
        candidates.sort(key=lambda o: (-o.e.punts, o.f.estat == "permanent",
                                       (o.f.tancament if o.f.estat == "oberta" else o.f.obertura) or dt.date.max))
        resultats.append(ResultatDivisio(d, candidates[:maxim]))
    sc = Screening(client, avui, horitzo_dies, resultats, len(cat.convocatories))
    for o in sc.oportunitats:
        sc.matriu.append({"c": o.c, "f": o.f,
                          "punts": {r.divisio.id: puntua(o.c, r.divisio.perfil, cat.zones, pesos) for r in resultats}})
    sc.matriu.sort(key=lambda m: -max(e.punts for e in m["punts"].values()))
    sc.sector = _sector(cat, client, triades, finestres, avui, horitzo_dies)
    return sc


def _sector(cat: Cataleg, client: Client, divisions: list[Divisio], finestres: dict, avui: dt.date,
            horitzo: int) -> dict | None:
    """Ajuts duals elegibles, portes d'entrada, actors i requisits per a les divisions amb temes de defensa."""
    divs = [d for d in divisions if set(d.perfil.focus) & ecosistema.AMBITS_SECTOR]
    if not divs:
        return None
    pesos, linies = cat.config.get("pesos"), []
    for c in cat.convocatories:
        if not set(c.focus) & ecosistema.AMBITS_SECTOR or not _dins_horitzo(finestres[c.id], avui, horitzo):
            continue
        millor = max(((puntua(c, d.perfil, cat.zones, pesos), d) for d in divs), key=lambda x: x[0].punts)
        if millor[0].rol:
            linies.append({"c": c, "f": finestres[c.id], "e": millor[0], "divisio": millor[1]})
    linies.sort(key=lambda x: -x["e"].punts)
    eco = ecosistema.carrega(cat)
    temes = ecosistema.AMBITS_SECTOR | {t for d in divs for t in d.perfil.focus}
    actors = [a for a in eco.actors if set(a.ambits) & ecosistema.AMBITS_SECTOR and set(a.ambits) & temes]
    trobades = [t for t in ecosistema.trobades_actives(eco, avui, horitzo) if set(t.ambits) & temes]
    return {"divisions": divs, "linies": linies[:6], "actors": actors, "trobades": trobades,
            "requisits": eco.requisits}


# --- Textos comuns --------------------------------------------------------------------------------

def _data(d: dt.date | None) -> str:
    return f"{d:%d/%m/%Y}" if d else ""


def finestra_text(f: calendari.Finestra) -> str:
    m = "≈ " if f.estimada else ""
    if f.estat == "permanent":
        return "Oberta tot l'any"
    if f.estat == "oberta":
        return f"Oberta fins al {m}{_data(f.tancament)}" if f.tancament else "Oberta (termini per confirmar)"
    if f.obertura and f.tancament:
        return f"{m}{_data(f.obertura)} → {_data(f.tancament)}"
    if f.obertura:
        return f"Obre el {m}{_data(f.obertura)}"
    if f.tancament:
        return f"Termini: {m}{_data(f.tancament)}"
    return "Anunciada (dates per confirmar)"


def ajut_text(c: Convocatoria) -> str:
    if c.ajuda_text:
        return c.ajuda_text
    parts = []
    if c.import_max_eur:
        parts.append(f"fins a {c.import_max_eur:,.0f} €".replace(",", "."))
    if c.intensitat_max:
        parts.append(f"{c.intensitat_max:g} %")
    return " · ".join(parts) or "Per confirmar"


def xifres(sc: Screening) -> dict:
    ops = sc.oportunitats
    obertes = [o for o in ops if o.f.estat in ("oberta", "permanent")]
    properes = [o for o in ops if o.f.estat == "propera" and o.f.obertura
                and 0 <= (o.f.obertura - sc.avui).days <= 90]
    return {"linies": len(ops), "obertes": len(obertes), "properes": len(properes),
            "a": len({o.c.id for r in sc.resultats for o in r.oportunitats if o.e.prioritat == "A"})}


def _curt(nom: str, maxim: int = 60) -> str:
    return nom if len(nom) <= maxim else nom[:maxim].rsplit(" ", 1)[0] + "…"


def missatge_divisio(r: ResultatDivisio) -> str:
    """Una línia per divisió: el projecte suggerit, el proper termini i l'opció oberta tot l'any."""
    if not r.oportunitats:
        return "Cap línia prioritària en els propers 12 mesos amb el perfil actual."
    parts = []
    idea = next((o.idees[0] for o in r.oportunitats if o.idees), None)
    if idea:
        parts.append(f"Projecte suggerit: {idea.titol}.")
    amb_data = [o for o in r.oportunitats if o.f.estat in ("oberta", "propera") and o.f.tancament]
    if amb_data:
        o = min(amb_data, key=lambda o: o.f.tancament)
        parts.append(f"Proper termini: {_curt(o.c.nom)}, {'≈ ' if o.f.estimada else ''}{o.f.tancament:%d/%m/%Y}.")
    permanent = next((o for o in r.oportunitats if o.f.estat == "permanent"), None)
    if permanent:
        parts.append(f"Oberta tot l'any: {_curt(permanent.c.nom)}.")
    return " ".join(parts)


# --- Calendari (senyals .ics per al client) -------------------------------------------------------

def senyals(sc: Screening, antelacio: dict | None = None) -> list[calendari.Senyal]:
    limit = sc.avui + dt.timedelta(days=sc.horitzo_dies)
    totes = [s for o in sc.oportunitats for s in calendari.senyals(o.c, sc.avui, antelacio) if s.data <= limit]
    return sorted(totes, key=lambda s: (s.data, s.convocatoria.nom))


# --- Markdown -------------------------------------------------------------------------------------

def markdown(sc: Screening) -> str:
    cl, x = sc.client, xifres(sc)
    t = [f"# Screening d'ajuts — {cl.nom}", "",
         f"_Preparat per Stimulo el {sc.avui:%d/%m/%Y}. Horitzó: 12 mesos. {sc.n_convocatories} línies revisades._", ""]
    if cl.estat_dades:
        t += [f"> {cl.estat_dades}", ""]
    t += ["## Resum", "",
          f"- {x['linies']} línies elegibles amb encaix per a alguna divisió ({x['a']} de prioritat A).",
          f"- {x['obertes']} obertes ara o tot l'any; {x['properes']} obren en els propers 90 dies.", ""]
    for r in sc.resultats:
        t.append(f"- **{r.divisio.nom}:** {missatge_divisio(r)}")
    t += ["", "## Matriu divisions × línies", ""]
    caps = [r.divisio.nom for r in sc.resultats]
    t += ["| Línia | Finestra | " + " | ".join(caps) + " |", "|---|---|" + "---|" * len(caps)]
    for m in sc.matriu:
        cel = []
        for r in sc.resultats:
            e = m["punts"][r.divisio.id]
            cel.append(f"{e.punts} {e.prioritat}" if e.prioritat in ("A", "B") else "—")
        t.append(f"| {m['c'].nom} | {finestra_text(m['f'])} | " + " | ".join(cel) + " |")
    for r in sc.resultats:
        d = r.divisio
        t += ["", f"## {d.nom}", "", d.descripcio, ""]
        for o in r.oportunitats:
            t += [f"### {o.c.nom} — {o.e.punts}/100 ({o.e.prioritat})", "",
                  f"- **Entitat:** {o.c.entitat}", f"- **Finestra:** {finestra_text(o.f)}",
                  f"- **Ajut:** {ajut_text(o.c)}", f"- **Paper de {cl.nom}:** {o.rol_client}",
                  f"- **Paper de Stimulo:** {o.rol_stimulo}",
                  f"- **Què finança:** {' '.join(o.c.descripcio.split())}"]
            if o.idees:
                t.append("- **Idea de projecte:** " + "; ".join(
                    f"{i.titol}" + (f" (Stimulo: {i.stimulo})" if i.stimulo else "") for i in o.idees))
            for a in o.atencio:
                t.append(f"- ⚠ {a}")
            if o.c.url:
                t.append(f"- Fitxa: {o.c.url}")
            t.append("")
    if sc.sector:
        st = sc.sector
        t += ["## Entrar al sector de defensa i ús dual", "",
              f"Per a {', '.join(d.nom for d in st['divisions'])}.", "", "**Ajuts d'ús dual i defensa**", ""]
        t += [f"- {x['c'].nom} — {x['e'].punts}/100 ({x['e'].prioritat}) · {finestra_text(x['f'])}" for x in st["linies"]]
        t += ["", "**Portes d'entrada**", ""]
        t += [f"- {x.nom} · {x.quan()}" + (f" · {x.lloc}" if x.lloc else "") for x in st["trobades"]]
        t += ["", "**Amb qui parlar**", ""]
        t += [f"- {a.nom}: {a.per_als_clients}" for a in st["actors"]]
        t += ["", "**Requisits que demanaran**", ""]
        t += [f"- {r.nom}: {r.quan}" for r in st["requisits"]]
        t.append("")
    if cl.consideracions:
        t += ["## A tenir en compte", ""] + [f"- {c}" for c in cl.consideracions] + [""]
    if cl.preguntes:
        t += ["## Preguntes per validar", ""] + [f"{i}. {p}" for i, p in enumerate(cl.preguntes, 1)] + [""]
    t += ["## Metodologia", "",
          "Cada divisió es puntua de 0 a 100 amb el radar de Stimulo: temes 40, rol 20, zona 15, TRL 10 i "
          "import 15. Prioritat A ≥ 80, B ≥ 65. Només hi entren les línies on l'empresa és elegible (zona, "
          "mida i tipus d'entitat) i que obren o tanquen en els propers 12 mesos. Les dates amb ≈ són "
          "estimades a partir de l'edició anterior.", ""]
    return "\n".join(t)


# --- HTML (informe per al client) -----------------------------------------------------------------

def _e(text) -> str:
    return html.escape(str(text or ""), quote=True)


CSS = """
/* Informe de lliurament: capçalera, resum, mètode, filtre per divisió (sense JS), matriu, fitxes per divisió i calendari */
:root {
  --bg: #F3F5F9; --surface: #FFFFFF; --ink: #131A2A; --muted: #5B6579; --line: #DCE1EA;
  --accent: #2A3DBA; --accent-soft: #E7EAFB; --accent-ink: #FFFFFF;
  --ok: #19744B; --ok-soft: #E1F2E9; --warn: #9A5800; --warn-soft: #FAEED8; --off-soft: #ECEFF4;
  --f-display: "Schibsted Grotesk", "Helvetica Neue", Arial, sans-serif;
  --f-body: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --f-mono: "IBM Plex Mono", ui-monospace, Menlo, monospace;
  --r: 10px;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #0D121C; --surface: #151C2A; --ink: #E6EAF2; --muted: #9AA3B6; --line: #273145;
  --accent: #8F9DFF; --accent-soft: #222A50; --accent-ink: #0D121C;
  --ok: #5BC892; --ok-soft: #153126; --warn: #EFB25A; --warn-soft: #382912; --off-soft: #1C2332; color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #0D121C; --surface: #151C2A; --ink: #E6EAF2; --muted: #9AA3B6; --line: #273145;
  --accent: #8F9DFF; --accent-soft: #222A50; --accent-ink: #0D121C;
  --ok: #5BC892; --ok-soft: #153126; --warn: #EFB25A; --warn-soft: #382912; --off-soft: #1C2332; color-scheme: dark; }
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--ink); font: 15px/1.55 var(--f-body); margin: 0; }
.informe { max-width: 1120px; margin: 0 auto; padding-inline: 20px; padding-block: 32px 64px; display: grid; gap: 28px; }
a { color: var(--accent); }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
h1, h2, h3 { font-family: var(--f-display); text-wrap: balance; margin: 0; }
h1 { font-size: clamp(30px, 4.6vw, 46px); line-height: 1.05; letter-spacing: -.02em; font-weight: 800; }
h2 { font-size: 22px; line-height: 1.2; font-weight: 800; }
h3 { font-size: 17px; line-height: 1.3; font-weight: 600; }
p { margin: 0; }
.eti { font: 500 12px/1.3 var(--f-mono); letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
.sub { color: var(--muted); max-width: 68ch; }
.cap { display: grid; gap: 10px; }
.meta { display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 13px; color: var(--muted); }
.meta b { color: var(--ink); font-weight: 500; }
.xip { display: inline-flex; align-items: center; gap: 6px; font: 600 12px/1 var(--f-body); padding: 6px 9px; border-radius: 6px; width: fit-content; }
.xip-avis { background: var(--warn-soft); color: var(--warn); }
.seccio { display: grid; gap: 14px; }
.seccio > header { display: grid; gap: 4px; }
.xifres { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1px; background: var(--line); border: 1px solid var(--line); border-radius: var(--r); overflow: hidden; }
.xifres div { background: var(--surface); padding: 14px 16px; display: grid; gap: 2px; }
.xifres b { font: 800 28px/1.1 var(--f-display); font-variant-numeric: tabular-nums; }
.xifres span { color: var(--muted); font-size: 13px; }
.missatges { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
.missatges li { display: grid; grid-template-columns: 210px minmax(0, 1fr); gap: 4px 16px; padding: 10px 0; border-top: 1px solid var(--line); }
.missatges li b { font-weight: 600; }
.passos { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; margin: 0; padding: 0; list-style: none; counter-reset: pas; }
.passos li { background: var(--surface); border: 1px solid var(--line); border-radius: var(--r); padding: 14px; display: grid; gap: 6px; align-content: start; counter-increment: pas; font-size: 14px; }
.passos li::before { content: counter(pas); font: 500 12px/1 var(--f-mono); color: var(--accent); }
.passos b { font-weight: 600; }
.passos span { color: var(--muted); }
.filtre-input { position: absolute; opacity: 0; pointer-events: none; }
.filtre { display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center; position: sticky; top: env(safe-area-inset-top, 0px); z-index: 2; background: var(--bg); padding-block: 10px; }
.filtre > span { font: 500 12px/1 var(--f-mono); letter-spacing: .06em; text-transform: uppercase; color: var(--muted); }
.seg { display: inline-flex; flex-wrap: wrap; background: var(--surface); border: 1px solid var(--line); border-radius: 999px; padding: 3px; gap: 2px; }
.seg label { font: 600 14px/1 var(--f-body); color: var(--ink); border-radius: 999px; padding: 9px 14px; cursor: pointer; }
.contingut { display: grid; gap: 28px; }
.taula-embolcall { overflow-x: auto; background: var(--surface); border: 1px solid var(--line); border-radius: var(--r); }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th { text-align: left; font: 500 11px/1.3 var(--f-mono); letter-spacing: .05em; text-transform: uppercase; color: var(--muted); padding: 10px 12px; border-bottom: 1px solid var(--line); white-space: nowrap; }
td { padding: 9px 12px; border-bottom: 1px solid var(--line); vertical-align: top; }
tr:last-child td { border-bottom: 0; }
td.nom { min-width: 240px; }
td.nom small { display: block; color: var(--muted); }
td.punt { text-align: center; white-space: nowrap; }
.p { display: inline-grid; place-items: center; min-width: 46px; padding: 5px 6px; border-radius: 7px; font: 500 13px/1 var(--f-mono); font-variant-numeric: tabular-nums; }
.p-A { background: var(--accent); color: var(--accent-ink); }
.p-B { background: var(--accent-soft); color: var(--accent); }
.p-no { color: var(--muted); }
.estat { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 500; padding: 4px 8px; border-radius: 6px; width: fit-content; white-space: nowrap; }
.estat::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.e-oberta { background: var(--ok-soft); color: var(--ok); }
.e-propera { background: var(--warn-soft); color: var(--warn); }
.e-permanent { background: var(--accent-soft); color: var(--accent); }
.e-estimada { outline: 1px dashed currentColor; outline-offset: -1px; }
.divisio { display: grid; gap: 14px; }
.divisio > header { display: grid; gap: 6px; padding-top: 18px; border-top: 2px solid var(--ink); }
.etiquetes { display: flex; flex-wrap: wrap; gap: 6px; }
.etiquetes span { font: 12px/1 var(--f-mono); padding: 5px 7px; border-radius: 5px; background: var(--off-soft); color: var(--muted); }
.ops { display: grid; gap: 10px; }
.op { background: var(--surface); border: 1px solid var(--line); border-radius: var(--r); min-width: 0; }
.op[open] { border-color: color-mix(in srgb, var(--accent) 45%, var(--line)); }
.op-cap { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 14px; align-items: center; padding: 12px 16px; cursor: pointer; list-style: none; }
.op-cap::-webkit-details-marker { display: none; }
.op-cap .p { min-width: 52px; padding: 10px 6px; font-size: 16px; }
.op-tit { display: grid; gap: 2px; min-width: 0; }
.op-tit small { color: var(--muted); font-size: 13px; }
.op-cos { display: grid; gap: 12px; padding: 0 18px 16px 82px; }
.fitxa { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px 20px; margin: 0; }
.fitxa dt { font: 500 11px/1.3 var(--f-mono); letter-spacing: .05em; text-transform: uppercase; color: var(--muted); }
.fitxa dd { margin: 2px 0 0; font-size: 14px; overflow-wrap: anywhere; }
.idea { border-left: 3px solid var(--accent); padding: 2px 0 2px 12px; display: grid; gap: 2px; font-size: 14px; }
.idea b { font-weight: 600; }
.idea span { color: var(--muted); }
.atencio { margin: 0; padding-left: 18px; font-size: 13px; color: var(--muted); display: grid; gap: 2px; }
.op-peu { display: flex; flex-wrap: wrap; gap: 8px 18px; font-size: 14px; }
.boto { display: inline-block; font: 600 14px/1 var(--f-body); background: var(--accent); color: var(--accent-ink); text-decoration: none; border-radius: 8px; padding: 9px 13px; }
.buit { padding: 18px; color: var(--muted); background: var(--surface); border: 1px dashed var(--line); border-radius: var(--r); }
.cal { background: var(--surface); border: 1px solid var(--line); border-radius: var(--r); overflow-x: auto; }
.cal-grid { min-width: 760px; display: grid; grid-template-columns: 260px minmax(0, 1fr); }
.cal-mesos { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); border-bottom: 1px solid var(--line); }
.cal-mesos span { font: 500 11px/1 var(--f-mono); text-transform: uppercase; letter-spacing: .05em; color: var(--muted); padding: 10px 6px; border-left: 1px solid var(--line); }
.cal-nom { padding: 8px 12px; font-size: 13px; border-bottom: 1px solid var(--line); min-width: 0; }
.cal-nom small { color: var(--muted); display: block; }
.cal-fila { position: relative; border-bottom: 1px solid var(--line); background-image: linear-gradient(to right, var(--line) 1px, transparent 1px); background-size: calc(100% / 12) 100%; }
.cal-barra { position: absolute; top: 50%; height: 14px; margin-top: -7px; left: var(--l); width: var(--w); min-width: 6px; border-radius: 4px; background: var(--accent); }
.cal-barra.estimada { background: repeating-linear-gradient(135deg, var(--accent) 0 6px, var(--accent-soft) 6px 10px); }
.cal-barra.permanent { background: var(--accent-soft); }
.cal-cap { border-bottom: 1px solid var(--line); }
.llegenda { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 13px; color: var(--muted); }
.llegenda i { display: inline-block; width: 18px; height: 10px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; }
.llegenda .l1 { background: var(--accent); }
.llegenda .l2 { background: repeating-linear-gradient(135deg, var(--accent) 0 6px, var(--accent-soft) 6px 10px); }
.llegenda .l3 { background: var(--accent-soft); }
.dues { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.bloc { background: var(--surface); border: 1px solid var(--line); border-radius: var(--r); padding: 16px 18px; display: grid; gap: 10px; align-content: start; }
.bloc ul, .bloc ol { margin: 0; padding-left: 20px; display: grid; gap: 6px; font-size: 14px; }
.serveis { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.serveis div { background: var(--surface); border: 1px solid var(--line); border-radius: var(--r); padding: 14px 16px; display: grid; gap: 6px; align-content: start; font-size: 14px; }
.serveis b { font-family: var(--f-display); font-size: 16px; }
.serveis span { color: var(--muted); }
.llista-neta { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
.llista-neta li { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 10px; align-items: start; font-size: 14px; }
.llista-neta li:not(:has(> .p, > .xip-tipus)) { grid-template-columns: minmax(0, 1fr); }
.llista-neta li span { min-width: 0; }
.llista-neta small { display: block; color: var(--muted); font-size: 13px; }
.llista-neta .p { min-width: 40px; }
.xip-tipus { font: 500 10px/1.2 var(--f-mono); letter-spacing: .05em; text-transform: uppercase; color: var(--accent); background: var(--accent-soft); padding: 4px 6px; border-radius: 4px; white-space: nowrap; margin-top: 2px; }
.sector > header { padding-top: 18px; border-top: 2px solid var(--ink); }
.bloc h3 { font-size: 16px; }
footer { color: var(--muted); font-size: 13px; display: grid; gap: 6px; border-top: 1px solid var(--line); padding-top: 16px; }
footer p { max-width: 100ch; overflow-wrap: anywhere; }
@media (max-width: 900px) {
  .passos, .serveis { grid-template-columns: minmax(0, 1fr); }
  .dues { grid-template-columns: minmax(0, 1fr); }
  .missatges li { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 640px) {
  .informe { padding-inline: 16px; }
  .xifres { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .op-cap { grid-template-columns: auto minmax(0, 1fr); }
  .op-cap .estat { grid-column: 2; }
  .op-cos { padding-left: 16px; }
  .filtre { position: static; }
}
@media print {
  .filtre, .filtre-input { display: none !important; }
  .informe { padding-block: 0; }
  .op, .bloc, .divisio > header { break-inside: avoid; }
}
"""


def _css_filtre(ids: list[str]) -> str:
    regles = []
    for i in ids:
        regles.append(f'#f-{i}:checked ~ .contingut [data-divisio]:not([data-divisio~="{i}"]) {{ display: none; }}')
        regles.append(f'#f-{i}:checked ~ .filtre label[for="f-{i}"] {{ background: var(--accent); color: var(--accent-ink); }}')
    regles.append('#f-tot:checked ~ .filtre label[for="f-tot"] { background: var(--accent); color: var(--accent-ink); }')
    regles += [f'#f-{i}:focus-visible ~ .filtre label[for="f-{i}"]' + " { outline: 2px solid var(--accent); }"
               for i in ["tot", *ids]]
    return "\n".join(regles)


def _punt(e: Encaix) -> str:
    if e.prioritat in ("A", "B"):
        return f'<span class="p p-{e.prioritat}" title="Encaix {e.punts}/100, prioritat {e.prioritat}">{e.punts} {e.prioritat}</span>'
    return '<span class="p p-no" title="Sense encaix prioritari">—</span>'


def _estat(f: calendari.Finestra) -> str:
    return f'<span class="estat e-{f.estat}{" e-estimada" if f.estimada else ""}">{_e(finestra_text(f))}</span>'


def _suma_mesos(d: dt.date, n: int) -> dt.date:
    return dt.date(d.year + (d.month - 1 + n) // 12, (d.month - 1 + n) % 12 + 1, 1)


def _calendari_html(sc: Screening) -> str:
    inici = sc.avui.replace(day=1)
    final = _suma_mesos(inici, 12)
    total = (final - inici).days
    mesos = []
    for k in range(12):
        m = _suma_mesos(inici, k)
        mesos.append(MESOS[m.month - 1] + (f" {m:%y}" if k == 0 or m.month == 1 else ""))
    files = []
    for o in sorted(sc.oportunitats, key=lambda o: ((o.f.obertura or o.f.tancament or sc.avui), o.c.nom)):
        f = o.f
        if f.estat == "permanent":
            a, b, classe = inici, final, "permanent"
        elif not f.tancament:
            continue  # anunciada o oberta sense termini: no es pot dibuixar
        else:
            a = f.obertura if f.obertura and f.estat != "oberta" else sc.avui
            b = f.tancament
            classe = "estimada" if f.estimada else ""
        a, b = max(a, inici), min(b, final)
        if b < inici or a > final:
            continue
        esquerra = 100 * (a - inici).days / total
        amplada = max(1.0, 100 * (b - a).days / total)
        divs = " ".join(r.divisio.id for r in sc.resultats if any(x.c.id == o.c.id for x in r.oportunitats))
        files.append(
            f'<div class="cal-nom" data-divisio="{divs}"><b>{_e(o.c.nom)}</b><small>{_e(finestra_text(f))}</small></div>'
            f'<div class="cal-fila" data-divisio="{divs}"><span class="cal-barra {classe}" '
            f'style="--l:{esquerra:.2f}%;--w:{amplada:.2f}%" title="{_e(finestra_text(f))}"></span></div>')
    return ('<div class="cal"><div class="cal-grid"><div class="cal-cap"></div><div class="cal-mesos">'
            + "".join(f"<span>{m}</span>" for m in mesos) + "</div>" + "".join(files) + "</div></div>")


def _sector_html(sc: Screening) -> str:
    st = sc.sector
    divs = " ".join(d.id for d in st["divisions"])
    h = [f'<section class="seccio sector" data-divisio="{_e(divs)}" aria-labelledby="t-sector"><header>'
         '<span class="eti">Defensa, ús dual i espai</span>'
         '<h2 id="t-sector">Entrar al sector de defensa i ús dual</h2>'
         f'<p class="sub">Per a {_e(", ".join(d.nom for d in st["divisions"]))}: ajuts on '
         f'{_e(sc.client.nom)} pot participar, portes d\'entrada al sector, amb qui parlar i què demanaran els compradors.</p>'
         '</header><div class="dues">']
    h.append('<div class="bloc"><h3>Ajuts d\'ús dual i defensa</h3><ul class="llista-neta">'
             + "".join(f'<li><span class="p p-{x["e"].prioritat if x["e"].prioritat in ("A", "B") else "no"}">'
                       f'{x["e"].punts}</span><span><b>{_e(x["c"].nom)}</b><small>{_e(finestra_text(x["f"]))} · '
                       f'{_e(x["divisio"].nom)}</small></span></li>' for x in st["linies"])
             + "</ul></div>")
    h.append('<div class="bloc"><h3>Portes d\'entrada</h3><ul class="llista-neta">'
             + "".join(f'<li><span class="xip-tipus">{_e(ecosistema.NOMS_TIPUS[t.tipus])}</span><span><b>'
                       + (f'<a href="{_e(t.url)}" target="_blank" rel="noopener">{_e(t.nom)}</a>' if t.url else _e(t.nom))
                       + f'</b><small>{_e(t.quan())}{" · " + _e(t.lloc) if t.lloc else ""}</small>'
                       + (f"<small>{_e(t.per_als_clients)}</small>" if t.per_als_clients else "") + "</span></li>"
                       for t in st["trobades"])
             + "</ul></div></div><div class=\"dues\">")
    h.append('<div class="bloc"><h3>Amb qui parlar</h3><ul class="llista-neta">'
             + "".join(f'<li><span class="xip-tipus">{_e(ecosistema.NOMS_TIPUS[a.tipus])}</span><span><b>{_e(a.nom)}</b>'
                       f'<small>{_e(a.per_als_clients)}</small></span></li>' for a in st["actors"])
             + "</ul></div>")
    h.append('<div class="bloc"><h3>Requisits que demanaran</h3><ul class="llista-neta">'
             + "".join(f'<li><span><b>{_e(r.nom)}</b><small>{_e(r.quan)}'
                       + (" Per verificar." if r.confianca == "baixa" else "") + "</small></span></li>"
                       for r in st["requisits"])
             + "</ul></div></div></section>")
    return "".join(h)


def informe_html(sc: Screening, app: bool = False) -> str:
    """Contingut de la pàgina (sense <!doctype>): <title>, estils i informe. Sense JavaScript."""
    cl, x = sc.client, xifres(sc)
    ids = [r.divisio.id for r in sc.resultats]
    h = [f"<title>Screening d'ajuts {_e(cl.nom)}</title>",
         '<link rel="preconnect" href="https://fonts.googleapis.com">',
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500'
         '&family=IBM+Plex+Sans:wght@400;500;600&family=Schibsted+Grotesk:wght@600;800&display=swap">',
         f"<style>{CSS}\n{_css_filtre(ids)}</style>", '<main class="informe">']

    # Capçalera
    h.append('<header class="cap">'
             f'<span class="eti">Stimulo · Screening d\'ajuts i finançament</span>'
             f'<h1>Oportunitats d\'ajut per a {_e(cl.nom)}</h1>'
             f'<p class="sub">{_e(cl.descripcio)}</p>'
             '<div class="meta">'
             f'<span>Preparat el <b>{sc.avui:%d/%m/%Y}</b></span>'
             f'<span>Divisions: <b>{len(sc.resultats)}</b></span>'
             f'<span>Horitzó: <b>12 mesos</b></span>'
             f'<span>Línies revisades: <b>{sc.n_convocatories}</b></span>'
             f'<span>Ubicació: <b>{_e(cl.ubicacio or cl.zona)}</b></span></div>'
             + (f'<span class="xip xip-avis">{_e(cl.estat_dades)}</span>' if cl.estat_dades else "")
             + "</header>")

    # Resum
    h.append('<section class="seccio" aria-labelledby="t-resum"><header><h2 id="t-resum">Resum</h2></header>'
             '<div class="xifres">'
             f'<div><b>{x["linies"]}</b><span>línies elegibles amb encaix</span></div>'
             f'<div><b>{x["a"]}</b><span>de prioritat A</span></div>'
             f'<div><b>{x["obertes"]}</b><span>obertes ara o tot l\'any</span></div>'
             f'<div><b>{x["properes"]}</b><span>obren en 90 dies</span></div></div>'
             '<ul class="missatges">'
             + "".join(f'<li><b>{_e(r.divisio.nom)}</b><span>{_e(missatge_divisio(r))}</span></li>' for r in sc.resultats)
             + "</ul></section>")

    # Com ho fem
    h.append('<section class="seccio" aria-labelledby="t-metode"><header><h2 id="t-metode">Com ho fem</h2>'
             '<p class="sub">El mateix radar que fa servir Stimulo, aplicat a cada divisió per separat.</p></header>'
             '<ol class="passos">'
             '<li><b>Perfil per divisió</b><span>Productes, mercats, TRL i full de ruta de cada divisió.</span></li>'
             f'<li><b>Radar</b><span>{sc.n_convocatories} línies públiques i privades: Catalunya, Estat i Europa, amb el calendari de cada una.</span></li>'
             '<li><b>Filtre d\'elegibilitat</b><span>Zona, mida d\'empresa i paper possible (sol·licitant o soci).</span></li>'
             '<li><b>Revisió experta</b><span>Idea de projecte per a cada línia, socis necessaris i riscos.</span></li>'
             '<li><b>Entrega i seguiment</b><span>Aquest informe, calendari d\'alertes i avís quan surti una línia nova.</span></li>'
             "</ol></section>")

    # Filtre per divisió (CSS, sense JS)
    h.append('<input class="filtre-input" type="radio" name="divisio" id="f-tot" checked>')
    for r in sc.resultats:
        h.append(f'<input class="filtre-input" type="radio" name="divisio" id="f-{_e(r.divisio.id)}">')
    h.append('<nav class="filtre" aria-label="Divisió"><span>Divisió</span><div class="seg">'
             '<label for="f-tot">Totes</label>'
             + "".join(f'<label for="f-{_e(r.divisio.id)}">{_e(r.divisio.nom)}</label>' for r in sc.resultats)
             + "</div></nav>")
    h.append('<div class="contingut">')

    # Matriu
    h.append('<section class="seccio" aria-labelledby="t-matriu"><header><h2 id="t-matriu">Línies × divisions</h2>'
             '<p class="sub">Encaix de 0 a 100 per a cada divisió. A ≥ 80, B ≥ 65; «—» vol dir sense encaix prioritari.</p></header>'
             '<div class="taula-embolcall"><table><thead><tr><th>Línia</th><th>Finestra</th>'
             + "".join(f"<th>{_e(r.divisio.nom)}</th>" for r in sc.resultats) + "</tr></thead><tbody>")
    for m in sc.matriu:
        divs = " ".join(i for i in ids if m["punts"][i].prioritat in ("A", "B"))
        h.append(f'<tr data-divisio="{divs}"><td class="nom"><b>{_e(m["c"].nom)}</b><small>{_e(m["c"].entitat)}</small></td>'
                 f'<td>{_estat(m["f"])}</td>'
                 + "".join(f'<td class="punt">{_punt(m["punts"][i])}</td>' for i in ids) + "</tr>")
    h.append("</tbody></table></div></section>")

    # Per divisió
    for r in sc.resultats:
        d = r.divisio
        h.append(f'<section class="divisio" data-divisio="{_e(d.id)}" aria-labelledby="t-{_e(d.id)}"><header>'
                 f'<span class="eti">Divisió</span><h2 id="t-{_e(d.id)}">{_e(d.nom)}</h2>'
                 f'<p class="sub">{_e(d.descripcio)}</p><div class="etiquetes">'
                 + "".join(f"<span>{_e(mk)}</span>" for mk in d.mercats)
                 + (f"<span>TRL {d.perfil.trl[0]}–{d.perfil.trl[1]}</span>" if d.perfil.trl else "")
                 + "</div></header>")
        if not r.oportunitats:
            h.append('<p class="buit">Cap línia prioritària en els propers 12 mesos amb aquest perfil.</p></section>')
            continue
        h.append('<div class="ops">')
        for n, o in enumerate(r.oportunitats):
            c = o.c
            h.append(f'<details class="op"{" open" if n < 2 else ""}><summary class="op-cap">'
                     f'<span class="p p-{o.e.prioritat}">{o.e.punts}</span>'
                     f'<span class="op-tit"><h3>{_e(c.nom)}</h3><small>{_e(c.entitat)} · {_e(_curt(ajut_text(c), 70))}</small></span>'
                     f'{_estat(o.f)}</summary><div class="op-cos">'
                     '<dl class="fitxa">'
                     f'<div><dt>Ajut</dt><dd>{_e(ajut_text(c))}</dd></div>'
                     f'<div><dt>Paper de {_e(cl.nom)}</dt><dd>{_e(o.rol_client)}</dd></div>'
                     f'<div><dt>Paper de Stimulo</dt><dd>{_e(o.rol_stimulo)}</dd></div>'
                     f'<div><dt>Àmbit</dt><dd>{_e(c.ambit_geografic or "Vegeu les bases")}</dd></div></dl>'
                     f'<p>{_e(" ".join(c.descripcio.split()))}</p>')
            for i in o.idees:
                h.append(f'<div class="idea"><b>Idea de projecte: {_e(i.titol)}</b>'
                         + (f"<span>Stimulo: {_e(i.stimulo)}</span>" if i.stimulo else "") + "</div>")
            if o.atencio:
                h.append('<ul class="atencio">' + "".join(f"<li>{_e(a)}</li>" for a in o.atencio) + "</ul>")
            peu = []
            if c.url:
                peu.append(f'<a href="{_e(c.url)}" target="_blank" rel="noopener">Fitxa o bases oficials ↗</a>')
            if app:
                peu.append(f'<a class="boto" href="/expedients/nou?convocatoria={_e(c.id)}&amp;client={_e(cl.id)}'
                           f'&amp;divisio={_e(d.id)}">Preparar sol·licitud</a>')
            if peu:
                h.append('<div class="op-peu">' + "".join(peu) + "</div>")
            h.append("</div></details>")
        h.append("</div></section>")

    # Calendari
    h.append('<section class="seccio" aria-labelledby="t-cal"><header><h2 id="t-cal">Calendari dels propers 12 mesos</h2>'
             '<div class="llegenda"><span><i class="l1"></i>Dates confirmades</span>'
             '<span><i class="l2"></i>Dates estimades (edició anterior)</span><span><i class="l3"></i>Oberta tot l\'any</span>'
             f'</div></header>{_calendari_html(sc)}</section>')
    if sc.sector:
        h.append(_sector_html(sc))
    h.append("</div>")  # .contingut

    # Consideracions i preguntes
    h.append('<section class="dues" aria-label="Consideracions i preguntes">'
             '<div class="bloc"><h2>A tenir en compte</h2><ul>'
             + "".join(f"<li>{_e(c)}</li>" for c in cl.consideracions) + "</ul></div>"
             '<div class="bloc"><h2>Preguntes per validar</h2><ol>'
             + "".join(f"<li>{_e(p)}</li>" for p in cl.preguntes) + "</ol></div></section>")

    # Propers passos
    h.append('<section class="seccio" aria-labelledby="t-passos"><header><h2 id="t-passos">Propers passos</h2></header>'
             '<div class="serveis">'
             '<div><b>1 · Validar i prioritzar</b><span>Revisar les divisions i triar 2 o 3 projectes amb el seu responsable. '
             'Omplir una fitxa per projecte: objectiu, TRL, pressupost i socis.</span></div>'
             '<div><b>2 · Preparar les sol·licituds</b><span>Stimulo redacta la memòria, el pla de treball i el pressupost '
             'i hi participa com a proveïdor tecnològic o soci quan l\'ajut ho permet.</span></div>'
             '<div><b>3 · Radar continu</b><span>Avís per correu a cada divisió quan surti una línia nova amb encaix, '
             'i calendari d\'alertes compartit.</span></div></div></section>')

    h.append("<footer><p>Puntuació del radar de Stimulo: temes 40, rol 20, zona 15, TRL 10 i import 15. Només hi entren "
             "les línies on l'empresa és elegible i que obren o tanquen en els propers 12 mesos. Les dates amb ≈ són "
             "estimades a partir de l'edició anterior i s'han de confirmar a la font oficial.</p>"
             + (f"<p>Fonts del perfil de {_e(cl.nom)}: " + " · ".join(
                 f'<a href="{_e(f)}" target="_blank" rel="noopener">{_e(urlparse(f).netloc)}</a>' for f in cl.fonts)
                + "</p>" if cl.fonts else "")
             + "</footer></main>")
    return "\n".join(h)


def context_client(client: Client, divisio: Divisio | None) -> str:
    """Bloc de context per a l'assistent quan la sol·licitud és per a un client de Stimulo."""
    t = [f"Client: {client.rao_social} ({client.nom}) · {client.ubicacio or client.zona} · mida: {client.mida}",
         client.descripcio]
    if divisio:
        t += [f"Divisió: {divisio.nom}. {divisio.descripcio}",
              f"Mercats: {', '.join(divisio.mercats)}" if divisio.mercats else "",
              f"TRL habitual: {divisio.perfil.trl[0]}–{divisio.perfil.trl[1]}" if divisio.perfil.trl else "",
              "Idees de projecte de partida:"]
        t += [f"- {i.titol}" + (f" (aportació de Stimulo: {i.stimulo})" if i.stimulo else "") for i in divisio.idees]
    if client.consideracions:
        t += ["A tenir en compte:"] + [f"- {c}" for c in client.consideracions]
    if client.estat_dades:
        t.append(f"Estat de les dades del client: {client.estat_dades}")
    t.append(f"El sol·licitant és {client.nom}; Stimulo prepara la sol·licitud i hi participa com a proveïdor "
             "tecnològic o soci quan l'ajut ho permet. Redacta els documents en nom del client.")
    return "\n".join(x for x in t if x)


def dades_json(sc: Screening) -> dict:
    return {
        "client": sc.client.id, "nom": sc.client.nom, "generat": sc.avui.isoformat(), "xifres": xifres(sc),
        "divisions": [{
            "id": r.divisio.id, "nom": r.divisio.nom,
            "oportunitats": [{"id": o.c.id, "nom": o.c.nom, "entitat": o.c.entitat, "punts": o.e.punts,
                              "prioritat": o.e.prioritat, "finestra": finestra_text(o.f), "ajut": ajut_text(o.c),
                              "rol_client": o.rol_client, "rol_stimulo": o.rol_stimulo,
                              "idees": [i.titol for i in o.idees], "atencio": o.atencio, "url": o.c.url}
                             for o in r.oportunitats]} for r in sc.resultats],
    }


def genera(sc: Screening, dir_sortida: Path, antelacio: dict | None = None) -> dict[str, Path]:
    """Escriu l'informe (HTML autònom), el Markdown, el JSON i el calendari .ics."""
    dir_sortida.mkdir(parents=True, exist_ok=True)
    base = f"screening-{sc.client.id}-{sc.avui:%Y-%m-%d}"
    cos = informe_html(sc)
    pagina = ('<!doctype html>\n<html lang="ca">\n<head>\n<meta charset="utf-8">\n'
              '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
              + cos.replace("</style>", "</style>\n</head>\n<body>", 1) + "\n</body>\n</html>\n")
    fitxers = {
        "html": dir_sortida / f"{base}.html", "md": dir_sortida / f"{base}.md",
        "json": dir_sortida / f"{base}.json", "ics": dir_sortida / f"alertes-{sc.client.id}.ics",
    }
    fitxers["html"].write_text(pagina, encoding="utf-8")
    fitxers["md"].write_text(markdown(sc), encoding="utf-8")
    fitxers["json"].write_text(json.dumps(dades_json(sc), ensure_ascii=False, indent=2), encoding="utf-8")
    fitxers["ics"].write_text(ics.genera(senyals(sc, antelacio), dt.datetime.now(dt.timezone.utc),
                                         f"Ajuts {sc.client.nom} (Stimulo)"), encoding="utf-8")
    return fitxers
