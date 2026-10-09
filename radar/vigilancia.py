"""Vigilants de fonts obertes: detecten convocatòries noves (BDNS, Funding & Tenders) que coincideixen
amb les paraules clau dels perfils i les deixen a sortida/novetats.md per revisar.

Pensats per executar-se setmanalment des de GitHub Actions (.github/workflows/radar.yml).
Cada vigilant falla de manera aïllada: si una API canvia, la resta continua i l'error queda a l'informe.

Formats d'API documentats per l'emissor però pendents de validar en la primera execució real
(l'entorn on s'ha desenvolupat no tenia accés de xarxa a aquests dominis).
"""

from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path

AGENT = "RadarAjutsStimulo/0.1 (+https://github.com/stimulomarqueting-glitch/Radar-d-ajuts)"
TEMPS_MAX = 40


@dataclass
class Troballa:
    font: str
    id: str
    titol: str
    organisme: str
    data: str
    termini: str
    url: str
    paraules: list[str]


def normalitza(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", text.lower())


def coincidencies(text: str, paraules: list[str]) -> list[str]:
    t = normalitza(text)
    return [p for p in paraules if re.search(r"\b" + re.escape(normalitza(p)) + r"\b", t)]


def _get(url: str, dades: bytes | None = None, capcaleres: dict | None = None) -> bytes:
    req = urllib.request.Request(url, data=dades, headers={"User-Agent": AGENT, **(capcaleres or {})})
    with urllib.request.urlopen(req, timeout=TEMPS_MAX) as r:  # noqa: S310 (URLs fixes de fonts públiques)
        return r.read()


# --- BDNS (Base de Datos Nacional de Subvenciones) -------------------------------------------

BDNS_URL = "https://www.infosubvenciones.es/bdnstrans/api/convocatorias/busqueda"


# Òrgans que s'avisen sempre (encara que el títol no tingui paraules clau): totes les línies d'ACCIÓ
ORGANISMES_SEMPRE = {"ACCIÓ": ["competitivitat de l'empresa", "competitividad de la empresa", "accio"]}


def bdns_parse(payload: dict, paraules: list[str], organismes: dict[str, list[str]] | None = None) -> list[Troballa]:
    organismes = ORGANISMES_SEMPRE if organismes is None else organismes
    sortida = []
    for item in payload.get("content", []):
        titol = item.get("descripcion") or item.get("descripcionLeng") or ""
        organisme = " / ".join(filter(None, [item.get("nivel1"), item.get("nivel2"), item.get("nivel3")]))
        trobades = coincidencies(f"{titol} {organisme}", paraules)
        trobades += [nom for nom, patrons in organismes.items() if coincidencies(organisme, patrons)]
        if not trobades:
            continue
        num = str(item.get("numeroConvocatoria") or item.get("id"))
        sortida.append(Troballa(
            font="BDNS", id=f"bdns-{num}", titol=titol.strip(), organisme=organisme,
            data=str(item.get("fechaRecepcion", "")), termini="",
            url=f"https://www.infosubvenciones.es/bdnstrans/GE/es/convocatorias/{num}", paraules=trobades,
        ))
    return sortida


def bdns(paraules: list[str], dies: int = 10, max_pagines: int = 20) -> list[Troballa]:
    desde = (dt.date.today() - dt.timedelta(days=dies)).strftime("%d/%m/%Y")
    sortida: list[Troballa] = []
    for pagina in range(max_pagines):
        params = {"vpd": "GE", "page": pagina, "pageSize": 200, "order": "fechaRecepcion", "direccion": "desc",
                  "fechaDesde": desde}
        payload = json.loads(_get(BDNS_URL + "?" + urllib.parse.urlencode(params)))
        sortida += bdns_parse(payload, paraules)
        if payload.get("last", True) or len(payload.get("content", [])) < 200:
            break
    return sortida


# --- Funding & Tenders Portal (Comissió Europea, API SEDIA) ----------------------------------

SEDIA_URL = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
SEDIA_ESTATS = {"31094501": "oberta", "31094502": "propera"}


def _primer(meta: dict, clau: str) -> str:
    valor = meta.get(clau)
    if isinstance(valor, list):
        return str(valor[0]) if valor else ""
    return str(valor or "")


def sedia_parse(payload: dict, paraules: list[str]) -> list[Troballa]:
    sortida = []
    for res in payload.get("results", []):
        meta = res.get("metadata", {})
        ident = _primer(meta, "identifier") or res.get("reference", "")
        titol = _primer(meta, "title") or res.get("summary", "") or res.get("content", "")
        text = " ".join([titol, res.get("summary") or "", _primer(meta, "keywords"), _primer(meta, "tags")])
        trobades = coincidencies(text, paraules)
        if not trobades:
            continue
        estat = SEDIA_ESTATS.get(_primer(meta, "status"), _primer(meta, "status"))
        sortida.append(Troballa(
            font="EU Funding & Tenders", id=f"sedia-{ident}", titol=f"{ident} — {titol}".strip(" —"),
            organisme=_primer(meta, "frameworkProgramme") or "Comissió Europea",
            data=_primer(meta, "startDate")[:10], termini=_primer(meta, "deadlineDate")[:10] + f" ({estat})",
            url=f"https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{ident.lower()}",
            paraules=trobades,
        ))
    return sortida


def sedia(paraules: list[str], text: str = "***") -> list[Troballa]:
    consulta = {"bool": {"must": [
        {"terms": {"type": ["1", "2", "8"]}},
        {"terms": {"status": list(SEDIA_ESTATS)}},
    ]}}
    limit = "\r\n"
    frontera = "radarajuts"
    cos = ""
    for nom, valor in (("query", consulta), ("languages", ["en"])):
        cos += (f"--{frontera}{limit}Content-Disposition: form-data; name=\"{nom}\"; filename=\"blob\"{limit}"
                f"Content-Type: application/json{limit}{limit}{json.dumps(valor)}{limit}")
    cos += f"--{frontera}--{limit}"
    sortida: list[Troballa] = []
    for pagina in range(1, 6):
        params = {"apiKey": "SEDIA", "text": text, "pageSize": 100, "pageNumber": pagina}
        payload = json.loads(_get(SEDIA_URL + "?" + urllib.parse.urlencode(params), cos.encode(),
                                  {"Content-Type": f"multipart/form-data; boundary={frontera}"}))
        sortida += sedia_parse(payload, paraules)
        if len(payload.get("results", [])) < 100:
            break
    return sortida


# --- TED (licitacions europees, API v3) ------------------------------------------------------

TED_URL = "https://api.ted.europa.eu/v3/notices/search"


def ted_parse(payload: dict, paraules: list[str]) -> list[Troballa]:
    sortida = []
    for n in payload.get("notices", []):
        titol_brut = n.get("notice-title") or {}
        titol = titol_brut.get("spa") or titol_brut.get("cat") or titol_brut.get("eng") or next(
            iter(titol_brut.values()), "") if isinstance(titol_brut, dict) else str(titol_brut)
        comprador = n.get("buyer-name") or {}
        if isinstance(comprador, dict):
            comprador = ", ".join(v[0] if isinstance(v, list) else str(v) for v in comprador.values())
        trobades = coincidencies(f"{titol} {comprador}", paraules) or ["CPV"]
        pub = n.get("publication-number", "")
        termini = n.get("deadline-receipt-tender-date-lot") or ""
        if isinstance(termini, list):
            termini = termini[0] if termini else ""
        sortida.append(Troballa(
            font="TED", id=f"ted-{pub}", titol=str(titol), organisme=str(comprador),
            data=str(n.get("publication-date", ""))[:10], termini=str(termini)[:10],
            url=f"https://ted.europa.eu/ca/notice/-/detail/{pub}", paraules=trobades,
        ))
    return sortida


def ted(cpvs: list[str], paisos: list[str], dies: int = 10) -> list[Troballa]:
    desde = (dt.date.today() - dt.timedelta(days=dies)).strftime("%Y%m%d")
    consulta = (f"classification-cpv IN ({' '.join(cpvs)}) AND buyer-country IN ({' '.join(paisos)}) "
                f"AND publication-date>={desde}")
    cos = json.dumps({"query": consulta, "limit": 100, "page": 1, "scope": "ACTIVE",
                      "fields": ["publication-number", "notice-title", "buyer-name", "publication-date",
                                 "deadline-receipt-tender-date-lot"]}).encode()
    payload = json.loads(_get(TED_URL, cos, {"Content-Type": "application/json"}))
    return ted_parse(payload, [])


# --- PLACSP (Plataforma de Contratación del Sector Público, sindicació ATOM) -----------------

PLACSP_URL = ("https://contrataciondelestado.es/sindicacion/sindicacion_643/"
              "licitacionesPerfilesContratanteCompleto3.atom")
ATOM = "{http://www.w3.org/2005/Atom}"


def placsp_parse(xml: bytes, paraules: list[str], cpvs: list[str]) -> list[Troballa]:
    arrel = ET.fromstring(xml)
    sortida = []
    for e in arrel.iter(f"{ATOM}entry"):
        titol = (e.findtext(f"{ATOM}title") or "").strip()
        resum = (e.findtext(f"{ATOM}summary") or "").strip()
        codis = [el.text for el in e.iter() if el.tag.endswith("ItemClassificationCode") and el.text]
        cpv_ok = any(c.startswith(p) for c in codis for p in cpvs)
        trobades = coincidencies(f"{titol} {resum}", paraules)
        if not (cpv_ok and trobades) and not (trobades and len(trobades) >= 2):
            continue
        enllac = e.find(f"{ATOM}link")
        sortida.append(Troballa(
            font="PLACSP", id=f"placsp-{(e.findtext(f'{ATOM}id') or titol)[-40:]}", titol=titol,
            organisme=resum[:160], data=(e.findtext(f"{ATOM}updated") or "")[:10], termini="",
            url=enllac.get("href") if enllac is not None else "", paraules=trobades + (["CPV"] if cpv_ok else []),
        ))
    return sortida


def placsp(paraules: list[str], cpvs: list[str]) -> list[Troballa]:
    return placsp_parse(_get(PLACSP_URL), paraules, cpvs)


# --- Orquestració ------------------------------------------------------------------------------

def executa(config: dict, paraules: list[str], fitxer_vistos: Path) -> tuple[list[Troballa], dict[str, str]]:
    """Executa tots els vigilants i retorna només les troballes noves (no vistes abans)."""
    vistos = set(json.loads(fitxer_vistos.read_text())) if fitxer_vistos.exists() else set()
    # Les licitacions (TED, PLACSP i PSCP) tenen el seu propi mòdul: radar/licitacions.py
    vigilants = {
        "bdns": lambda: bdns(paraules),
        "sedia": lambda: sedia(paraules),
    }
    noves, errors = [], {}
    for nom, funcio in vigilants.items():
        try:
            for t in funcio():
                if t.id not in vistos:
                    noves.append(t)
                    vistos.add(t.id)
        except Exception as e:  # una font caiguda no ha d'aturar la resta
            errors[nom] = f"{type(e).__name__}: {e}"
    fitxer_vistos.parent.mkdir(parents=True, exist_ok=True)
    fitxer_vistos.write_text(json.dumps(sorted(vistos), indent=0))
    return noves, errors


def informe_novetats(noves: list[Troballa], errors: dict[str, str], avui: dt.date) -> str:
    l = [f"# Novetats del radar — {avui:%d/%m/%Y}", ""]
    if not noves:
        l.append("Cap convocatòria o licitació nova que coincideixi amb les paraules clau.")
    for font in sorted({t.font for t in noves}):
        l += ["", f"## {font}", "", "| Títol | Organisme | Publicació | Termini | Coincidències |", "|---|---|---|---|---|"]
        for t in [t for t in noves if t.font == font]:
            titol = t.titol.replace("|", "/")[:160]
            l.append(f"| [{titol}]({t.url}) | {t.organisme.replace('|', '/')[:80]} | {t.data} | {t.termini} | "
                     f"{', '.join(t.paraules)} |")
    if errors:
        l += ["", "## Fonts amb error (revisar)", ""] + [f"- **{k}**: {v}" for k, v in errors.items()]
    l += ["", "_Pas següent: revisar cada troballa i, si encaixa, crear-ne la fitxa a `data/convocatories.yaml`._"]
    return "\n".join(l) + "\n"


def a_json(noves: list[Troballa]) -> str:
    return json.dumps([asdict(t) for t in noves], ensure_ascii=False, indent=1)
