"""Licitacions públiques: detecció, avaluació go/no-go i fitxa de decisió.

    python -m radar licitacions            # cerca a PSCP, PLACSP i TED i escriu sortida/licitacions.md

Fonts oficials:
- PSCP (Plataforma de Serveis de Contractació Pública de Catalunya): dades obertes de la Generalitat
  (Socrata, conjunt ybgg-dgi6). Els noms de columna es resolen en temps d'execució a partir de les
  metadades del conjunt, perquè no depenguin d'un esquema fix.
- PLACSP (Plataforma de Contratación del Sector Público): sindicació ATOM amb CODICE. Opcionalment,
  el canal d'agregació, que inclou les plataformes autonòmiques (config.licitacions.placsp_agregades_url).
- TED (Diari Oficial de la UE): API v3, per als contractes que superen els llindars europeus.

Cap d'aquestes fonts no s'ha pogut provar en viu des de l'entorn de desenvolupament: cada font falla de
manera aïllada i l'error queda a l'informe i a la pàgina de l'aplicació.

L'avaluació només fa servir les dades estructurades de l'anunci (CPV, import, termini, procediment i
lloc). El que decideix de debò (solvència, criteris i pes del preu, propietat intel·lectual) és als
plecs: la fitxa de decisió ho converteix en una llista de comprovacions, i l'assistent de l'aplicació
pot llegir els plecs per omplir-la.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .vigilancia import _get, coincidencies, normalitza

PSCP_DOMINI = "https://analisi.transparenciacatalunya.cat"
PSCP_DATASET = "ybgg-dgi6"
PLACSP_URL = ("https://contrataciondelestado.es/sindicacion/sindicacion_643/"
              "licitacionesPerfilesContratanteCompleto3.atom")
TED_URL = "https://api.ted.europa.eu/v3/notices/search"
ESTATS = ["nova", "en anàlisi", "go", "no-go", "presentada", "guanyada", "perduda", "descartada"]
ESTATS_ACTIUS = ("en anàlisi", "go")
DIES_RECORDATORI = (7, 3, 1, 0)

CONFIG_PER_DEFECTE = {
    # CPV: 8 xifres = codi exacte; menys xifres = família (prefix). Calibrat amb les dades reals d'octubre de 2026
    "cpv_principals": ["7132", "79930000", "79933000", "79934000", "733", "7342"],
    "cpv": ["7312", "734", "73100000"],
    "paraules_clau": [],
    "exclou": [],
    "import_min": 15000,
    "import_max": 750000,
    "dies_minims": 10,
    "xifra_negoci_anual": None,
    "pscp_dataset": PSCP_DATASET,
    "placsp_agregades_url": "",
    "dies_cerca": 7,
}

# Columnes del conjunt de la PSCP: per a cada camp, fragments del nom de columna per ordre de preferència
COLUMNES_PSCP = {
    "id": ["id_intern", "codi_expedient"],
    "expedient": ["codi_expedient", "expedient"],
    "titol": ["denominacio", "objecte_contracte", "objecte", "descripcio"],
    "organ": ["nom_organ", "organ_contractacio", "nom_ambit", "organ"],
    "tipus": ["tipus_contracte"],
    "procediment": ["procediment"],
    "fase": ["fase_publicacio", "tipus_publicacio", "fase"],
    "import": ["pressupost_licitacio_sense", "pressupost_base_sense", "pressupost_licitacio", "pressupost"],
    "valor_estimat": ["valor_estimat"],
    "publicada": ["data_publicacio_anunci", "data_publicacio"],
    "termini": ["termini_presentacio", "data_limit_presentacio", "data_presentacio_ofertes"],
    "cpv": ["codi_cpv", "cpv"],
    "url": ["enllac_publicacio", "enllac", "url"],
    "lloc": ["lloc_execucio", "codi_nuts", "nuts"],
    "lot": ["numero_lot", "descripcio_lot", "lot"],
}


@dataclass
class Licitacio:
    id: str
    font: str
    titol: str
    organ: str
    url: str = ""
    expedient: str = ""
    tipus: str = ""
    procediment: str = ""
    fase: str = ""
    cpv: list[str] = field(default_factory=list)
    import_eur: float | None = None
    valor_estimat: float | None = None
    publicada: dt.date | None = None
    termini: dt.date | None = None
    lloc: str = ""
    lot: str = ""

    def a_dict(self) -> dict:
        d = asdict(self)
        d["publicada"] = self.publicada.isoformat() if self.publicada else None
        d["termini"] = self.termini.isoformat() if self.termini else None
        return d

    @classmethod
    def de_dict(cls, d: dict) -> "Licitacio":
        d = dict(d)
        for k in ("publicada", "termini"):
            d[k] = dt.date.fromisoformat(d[k]) if d.get(k) else None
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Avaluacio:
    punts: int
    semafor: str  # verd / groc / gris / vermell
    recomanacio: str  # Analitzar / Vigilar / Descartar / Informació
    motius: list[str]
    alertes: list[str]
    dies: int | None
    encaix: bool = False  # té CPV o paraules del perfil

    def a_dict(self) -> dict:
        return asdict(self)


# --- Utilitats de lectura -------------------------------------------------------------------------

def _num(valor) -> float | None:
    if valor in (None, ""):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    text = str(valor).strip().replace("€", "").replace(" ", "")
    if "," in text and "." in text:  # 1.234,56
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _data(valor) -> dt.date | None:
    if not valor:
        return None
    text = str(valor).strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        return dt.date(int(m[1]), int(m[2]), int(m[3]))
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", text)
    if m:
        return dt.date(int(m[3]), int(m[2]), int(m[1]))
    return None


def _cpvs(valor) -> list[str]:
    return re.findall(r"\d{8}", str(valor or ""))


def _text(valor) -> str:
    if isinstance(valor, dict):  # Socrata: camps URL com {"url": "..."}
        return str(valor.get("url") or valor.get("description") or "")
    return " ".join(str(valor or "").split())


# --- PSCP (dades obertes de la Generalitat) -------------------------------------------------------

def resol_columnes(columnes: list[str]) -> dict[str, str]:
    """Nom real de cada camp segons les columnes del conjunt (les que no es trobin queden fora)."""
    resultat = {}
    for camp, candidats in COLUMNES_PSCP.items():
        for c in candidats:
            trobada = next((col for col in columnes if col == c), None) or \
                next((col for col in columnes if c in col), None)
            if trobada:
                resultat[camp] = trobada
                break
    return resultat


def pscp_parse(files: list[dict], mapa: dict[str, str]) -> list[Licitacio]:
    def v(fila, camp):
        return fila.get(mapa[camp]) if camp in mapa else None

    sortida = []
    for f in files:
        expedient = _text(v(f, "expedient"))
        clau = _text(v(f, "id")) or expedient
        lot = _text(v(f, "lot"))
        if not clau:
            continue
        sortida.append(Licitacio(
            id=f"pscp:{clau}" + (f":{lot}" if lot and clau == expedient else ""), font="PSCP",
            titol=_text(v(f, "titol")), organ=_text(v(f, "organ")), url=_text(v(f, "url")),
            expedient=expedient, tipus=_text(v(f, "tipus")), procediment=_text(v(f, "procediment")),
            fase=_text(v(f, "fase")), cpv=_cpvs(v(f, "cpv")), import_eur=_num(v(f, "import")),
            valor_estimat=_num(v(f, "valor_estimat")), publicada=_data(v(f, "publicada")),
            termini=_data(v(f, "termini")), lloc=_text(v(f, "lloc")) or "Catalunya", lot=lot))
    return sortida


def pscp(cfg: dict, avui: dt.date) -> list[Licitacio]:
    dataset = cfg.get("pscp_dataset") or PSCP_DATASET
    meta = json.loads(_get(f"{PSCP_DOMINI}/api/views/{dataset}.json"))
    mapa = resol_columnes([c.get("fieldName", "") for c in meta.get("columns", [])])
    falten = [c for c in ("titol", "publicada") if c not in mapa]
    if falten:
        raise RuntimeError(f"PSCP: no es troben les columnes {falten}; revisar COLUMNES_PSCP")
    desde = (avui - dt.timedelta(days=cfg.get("dies_cerca", 7))).isoformat()
    params = {"$where": f"{mapa['publicada']} >= '{desde}T00:00:00'", "$limit": 5000,
              "$order": f"{mapa['publicada']} DESC"}
    files = json.loads(_get(f"{PSCP_DOMINI}/resource/{dataset}.json?" + urllib.parse.urlencode(params)))
    return pscp_parse(files, mapa)


# --- PLACSP (CODICE sobre ATOM) -------------------------------------------------------------------

def _local(el) -> str:
    return el.tag.rsplit("}", 1)[-1]


def _fill(el, *cami: str):
    """Primer descendent que segueix el camí de noms locals (sense espais de noms)."""
    actuals = [el]
    for nom in cami:
        seguents = [d for a in actuals for d in a.iter() if d is not a and _local(d) == nom]
        if not seguents:
            return None
        actuals = seguents
    return actuals[0]


def _fill_text(el, *cami: str) -> str:
    f = _fill(el, *cami)
    return (f.text or "").strip() if f is not None and f.text else ""


def placsp_parse(xml: bytes, font: str = "PLACSP") -> list[Licitacio]:
    arrel = ET.fromstring(xml)
    sortida = []
    for e in arrel.iter():
        if _local(e) != "entry":
            continue
        titol = _fill_text(e, "ProcurementProject", "Name") or _fill_text(e, "title")
        enllac = next((d.get("href", "") for d in e if _local(d) == "link"), "")
        expedient = _fill_text(e, "ContractFolderID")
        organ = _fill_text(e, "LocatedContractingParty", "Party", "PartyName", "Name")
        sortida.append(Licitacio(
            id=f"placsp:{expedient or _fill_text(e, 'id')[-40:]}:{normalitza(organ)[:40]}", font=font,
            titol=titol, organ=organ, url=enllac, expedient=expedient,
            tipus=_fill_text(e, "ProcurementProject", "TypeCode"),
            procediment=_fill_text(e, "TenderingProcess", "ProcedureCode"),
            fase=_fill_text(e, "ContractFolderStatusCode"),
            cpv=[d.text.strip() for d in e.iter() if _local(d) == "ItemClassificationCode" and d.text],
            import_eur=_num(_fill_text(e, "BudgetAmount", "TaxExclusiveAmount")),
            valor_estimat=_num(_fill_text(e, "BudgetAmount", "EstimatedOverallContractAmount")),
            publicada=_data(_fill_text(e, "updated")),
            termini=_data(_fill_text(e, "TenderSubmissionDeadlinePeriod", "EndDate")),
            lloc=_fill_text(e, "RealizedLocation", "CountrySubentityCode")
            or _fill_text(e, "RealizedLocation", "CountrySubentity")))
    return sortida


# Estats CODICE: PUB publicada, EV en avaluació, ADJ adjudicada, RES resolta, ANUL anul·lada, PRE anunci previ
FASES_OBERTES = {"pub", "pre", "anunci de licitacio", "anunci previ", "licitacio", "en termini"}


# --- TED -------------------------------------------------------------------------------------------

def ted_parse(payload: dict) -> list[Licitacio]:
    sortida = []
    for n in payload.get("notices", []):
        titol = n.get("notice-title") or {}
        if isinstance(titol, dict):
            titol = titol.get("cat") or titol.get("spa") or titol.get("eng") or next(iter(titol.values()), "")
        comprador = n.get("buyer-name") or {}
        if isinstance(comprador, dict):
            comprador = ", ".join(v[0] if isinstance(v, list) else str(v) for v in comprador.values())
        termini = n.get("deadline-receipt-tender-date-lot") or ""
        if isinstance(termini, list):
            termini = termini[0] if termini else ""
        cpv = n.get("classification-cpv") or []
        pub = n.get("publication-number", "")
        sortida.append(Licitacio(
            id=f"ted:{pub}", font="TED", titol=_text(titol), organ=_text(comprador),
            url=f"https://ted.europa.eu/ca/notice/-/detail/{pub}", expedient=pub,
            cpv=_cpvs(" ".join(cpv) if isinstance(cpv, list) else cpv),
            publicada=_data(n.get("publication-date")), termini=_data(termini), lloc="UE"))
    return sortida


def ted(cpvs: list[str], paisos: list[str], avui: dt.date, dies: int = 7) -> list[Licitacio]:
    desde = (avui - dt.timedelta(days=dies)).strftime("%Y%m%d")
    consulta = (f"classification-cpv IN ({' '.join(cpvs)}) AND buyer-country IN ({' '.join(paisos)}) "
                f"AND publication-date>={desde}")
    cos = json.dumps({"query": consulta, "limit": 100, "page": 1, "scope": "ACTIVE",
                      "fields": ["publication-number", "notice-title", "buyer-name", "publication-date",
                                 "deadline-receipt-tender-date-lot", "classification-cpv"]}).encode()
    return ted_parse(json.loads(_get(TED_URL, cos, {"Content-Type": "application/json"})))


# --- Avaluació go/no-go ---------------------------------------------------------------------------

def coincideix_cpv(cpv: str, entrada) -> bool:
    """Una entrada de 8 xifres és un codi exacte; una de menys xifres, una família (prefix)."""
    entrada = str(entrada).strip()
    return cpv == entrada if len(entrada) >= 8 else cpv.startswith(entrada)


def _es_catalunya(l: Licitacio) -> bool:
    return l.font == "PSCP" or l.lloc.upper().startswith("ES51") or "catalu" in normalitza(l.lloc)


def avalua(l: Licitacio, cfg: dict, avui: dt.date) -> Avaluacio:
    """Puntuació 0–100 amb les dades de l'anunci: tema 45, temps 20, import 20, zona 10, procediment 5."""
    cfg = {**CONFIG_PER_DEFECTE, **cfg}
    motius, alertes = [], []
    text = f"{l.titol} {l.organ}"

    # Si ja no és en termini de licitació, és informació (adjudicacions: competència i preus)
    fase = normalitza(l.fase)
    informativa = bool(fase) and not any(f in fase for f in FASES_OBERTES)

    principals = [c for c in l.cpv if any(coincideix_cpv(c, p) for p in cfg["cpv_principals"])]
    generals = [c for c in l.cpv if any(coincideix_cpv(c, p) for p in cfg.get("cpv", []))]
    paraules = coincidencies(text, cfg["paraules_clau"])
    tema = 25 if principals else 12 if generals else 0
    tema = min(45, tema + 10 * min(2, len(paraules)))
    if principals or generals:
        motius.append("CPV: " + ", ".join(sorted(set(principals or generals))))
    if paraules:
        motius.append("paraules: " + ", ".join(paraules))
    excloses = coincidencies(l.titol, cfg["exclou"])

    dies = (l.termini - avui).days if l.termini else None
    if dies is None:
        temps = 10
        alertes.append("Termini per confirmar a l'anunci.")
    elif dies < 0:
        temps = 0
    elif dies < 5:
        temps = 0
        alertes.append(f"Queden {dies} dies: gairebé impossible preparar una oferta de qualitat.")
    elif dies < cfg["dies_minims"]:
        temps = 6
        alertes.append(f"Termini just: {dies} dies.")
    else:
        temps = 20 if dies >= 20 else 14

    import_ = l.import_eur or l.valor_estimat
    if import_ is None:
        diners = 10
        alertes.append("Import per confirmar.")
    elif import_ < cfg["import_min"]:
        diners = 8
        motius.append(f"import petit ({import_:,.0f} €)".replace(",", "."))
    elif import_ > cfg["import_max"]:
        diners = 8
        alertes.append("Import alt: comprova solvència i valora presentar-t'hi en UTE amb un soci.")
    else:
        diners = 20
    if import_ and cfg.get("xifra_negoci_anual") and import_ * 1.5 > cfg["xifra_negoci_anual"]:
        alertes.append("Solvència econòmica: sovint es demana una xifra de negoci ≥ 1,5 × el valor anual; "
                       "probablement no hi arribem sols.")

    zona = 10 if _es_catalunya(l) else 6 if l.font in ("PLACSP", "PLACSP-agregades") else 4
    proc = normalitza(l.procediment)
    procediment = 5 if any(p in proc for p in ("obert", "abierto", "simplific", "abreujat", "abreviado")) else 3 if proc else 2

    punts = round(tema + temps + diners + zona + procediment) if tema else min(25, round(temps + diners))
    if informativa:
        semafor, recomanacio = "gris", "Informació"
        motius.append(f"fase: {l.fase} (no admet ofertes)")
    elif excloses:
        semafor, recomanacio = "gris", "Descartar"
        motius.append("fora d'abast: " + ", ".join(excloses))
    elif dies is not None and dies < 5:
        semafor, recomanacio = "vermell", "Descartar"
    elif not tema:
        semafor, recomanacio = "gris", "Descartar"
    elif punts >= 70 and tema >= 33:  # verd: CPV de disseny i paraula clau, o dues paraules clau
        semafor, recomanacio = "verd", "Analitzar"
    elif punts >= 50:
        semafor, recomanacio = "groc", "Vigilar"
    else:
        semafor, recomanacio = "gris", "Descartar"
    return Avaluacio(punts, semafor, recomanacio, motius, alertes, dies, encaix=bool(tema) and not excloses)


# --- Orquestració ---------------------------------------------------------------------------------

def _clau_duplicat(l: Licitacio) -> str:
    return f"{normalitza(l.expedient)}|{normalitza(l.organ)[:30]}" if l.expedient else l.id


def deduplica(licitacions: list[Licitacio]) -> list[Licitacio]:
    """El mateix expedient pot arribar per la PSCP i per l'agregació de la PLACSP: es queda el de la PSCP."""
    ordre = {"PSCP": 0, "PLACSP-agregades": 1, "PLACSP": 2, "TED": 3, "manual": 4}
    vistos, sortida = set(), []
    for l in sorted(licitacions, key=lambda x: ordre.get(x.font, 9)):
        clau = _clau_duplicat(l)
        if clau not in vistos:
            vistos.add(clau)
            sortida.append(l)
    return sortida


def cerca(cfg: dict, avui: dt.date, cpvs: list[str], paisos: list[str]) -> tuple[list[Licitacio], dict[str, str]]:
    fonts = {
        "pscp": lambda: pscp(cfg, avui),
        "placsp": lambda: placsp_parse(_get(PLACSP_URL)),
        "ted": lambda: ted(cpvs, paisos, avui, cfg.get("dies_cerca", 7)),
    }
    if cfg.get("placsp_agregades_url"):
        fonts["placsp_agregades"] = lambda: placsp_parse(_get(cfg["placsp_agregades_url"]), "PLACSP-agregades")
    totes, errors = [], {}
    for nom, funcio in fonts.items():
        try:
            totes.extend(funcio())
        except Exception as e:  # una font caiguda no atura la resta
            errors[nom] = f"{type(e).__name__}: {e}"
    return deduplica(totes), errors


def rellevants(licitacions: list[Licitacio], cfg: dict, avui: dt.date) -> list[tuple[Licitacio, Avaluacio]]:
    """Només les que tenen encaix temàtic, ordenades per semàfor i punts."""
    ordre = {"verd": 0, "groc": 1, "vermell": 2, "gris": 3}
    parells = [(l, avalua(l, cfg, avui)) for l in licitacions]
    parells = [(l, a) for l, a in parells if a.encaix and (a.dies is None or a.dies >= 0)]
    return sorted(parells, key=lambda p: (ordre[p[1].semafor], -p[1].punts))


def config(cat) -> dict:
    """Configuració de licitacions (perfils.yaml > config.licitacions).

    `cpv_ted` són els codis que es demanen a TED (la consulta hi afina); la puntuació fa servir
    `cpv_principals` i `cpv`, més estrets.
    """
    vig = cat.config.get("vigilancia", {})
    cfg = {**CONFIG_PER_DEFECTE, **cat.config.get("licitacions", {})}
    cfg["cpv"] = [str(c) for c in cfg.get("cpv", [])]
    cfg["cpv_principals"] = [str(c) for c in cfg.get("cpv_principals", [])]
    cfg["cpv_ted"] = [str(c) for c in vig.get("cpv", [])]
    cfg["paisos_ted"] = vig.get("paisos_ted", ["ESP"])
    return cfg


def executa(cat, avui: dt.date, dir_sortida: Path, fitxer_vistos: Path, db=None) -> dict:
    """Cerca, avalua i desa: informe públic (sortida/), llista de noves i, si hi ha aplicació, la BD."""
    cfg = config(cat)
    totes, errors = cerca(cfg, avui, cfg["cpv_ted"], cfg["paisos_ted"])
    parells = rellevants(totes, cfg, avui)
    vistos = set(json.loads(fitxer_vistos.read_text())) if fitxer_vistos.exists() else set()
    noves = [(l, a) for l, a in parells if l.id not in vistos]
    fitxer_vistos.parent.mkdir(parents=True, exist_ok=True)
    fitxer_vistos.write_text(json.dumps(sorted(vistos | {l.id for l, _ in parells}), indent=0))
    dir_sortida.mkdir(parents=True, exist_ok=True)
    (dir_sortida / "licitacions.md").write_text(markdown(parells, errors, avui), encoding="utf-8")
    (dir_sortida / "licitacions-noves.json").write_text(json.dumps(
        [{"licitacio": l.a_dict(), "avaluacio": a.a_dict()} for l, a in noves], ensure_ascii=False, indent=1),
        encoding="utf-8")
    if db is not None:
        for l, a in parells:
            db.desa_licitacio(l.a_dict(), a.a_dict())
    return {"totes": len(totes), "rellevants": len(parells), "noves": noves, "errors": errors}


def llegeix_noves(path: Path) -> list[tuple[Licitacio, Avaluacio]]:
    if not path.exists():
        return []
    return [(Licitacio.de_dict(x["licitacio"]), Avaluacio(**x["avaluacio"]))
            for x in json.loads(path.read_text(encoding="utf-8"))]


# --- Textos ---------------------------------------------------------------------------------------

def eur(v: float | None) -> str:
    return f"{v:,.0f} €".replace(",", ".") if v else "—"


def resum_curt(l: Licitacio, a: Avaluacio) -> str:
    termini = f"termini {l.termini:%d/%m/%Y} ({a.dies} dies)" if l.termini else "termini per confirmar"
    return f"{l.titol} — {l.organ} · {eur(l.import_eur or l.valor_estimat)} · {termini} · {a.punts}/100"


def markdown(parells: list[tuple[Licitacio, Avaluacio]], errors: dict, avui: dt.date) -> str:
    t = [f"# Licitacions — {avui:%d/%m/%Y}", "",
         "Anuncis de PSCP, PLACSP i TED amb encaix per a Stimulo. Semàfor: 🟢 analitzar · 🟡 vigilar · "
         "🔴 termini massa just · ⚪ informació.", ""]
    icones = {"verd": "🟢", "groc": "🟡", "vermell": "🔴", "gris": "⚪"}
    if parells:
        t += ["| | Punts | Licitació | Òrgan | Import | Termini | Font |", "|---|---|---|---|---|---|---|"]
        for l, a in parells:
            nom = l.titol.replace("|", "/")[:110]
            t.append(f"| {icones[a.semafor]} | {a.punts} | [{nom}]({l.url}) | {l.organ.replace('|', '/')[:60]} | "
                     f"{eur(l.import_eur or l.valor_estimat)} | {l.termini or '—'} | {l.font} |")
    else:
        t.append("Cap licitació amb encaix en aquesta revisió.")
    if errors:
        t += ["", "**Fonts amb error:** " + "; ".join(f"{k}: {v}" for k, v in errors.items())]
    return "\n".join(t) + "\n"


def fitxa_decisio(l: Licitacio, a: Avaluacio, estat: dict | None = None) -> str:
    """Fitxa per decidir go/no-go i compartir-la amb l'equip o amb un soci (Markdown)."""
    estat = estat or {}
    limit_intern = l.termini - dt.timedelta(days=3) if l.termini else None
    t = [f"# Fitxa de decisió: {l.titol}", "",
         f"**Recomanació del radar:** {a.recomanacio} ({a.punts}/100)"
         + (f" · **Estat:** {estat.get('estat')}" if estat.get("estat") else "")
         + (f" · **Responsable:** {estat.get('responsable')}" if estat.get("responsable") else ""), "",
         "## Dades de l'anunci", "",
         "| Camp | Valor |", "|---|---|",
         f"| Òrgan de contractació | {l.organ} |", f"| Expedient | {l.expedient or '—'} |",
         f"| Tipus i procediment | {l.tipus or '—'} · {l.procediment or '—'} |",
         f"| Pressupost base (sense IVA) | {eur(l.import_eur)} |", f"| Valor estimat | {eur(l.valor_estimat)} |",
         f"| Termini d'ofertes | {l.termini:%d/%m/%Y} |" if l.termini else "| Termini d'ofertes | per confirmar |",
         f"| Data límit interna (go/no-go) | {limit_intern:%d/%m/%Y} |" if limit_intern else "| Data límit interna | — |",
         f"| CPV | {', '.join(l.cpv) or '—'} |", f"| Lloc | {l.lloc or '—'} |",
         f"| Font | {l.font}{': ' + l.url if l.url else ''} |", "",
         "## Per què ens hi fixem", ""] + [f"- {m}" for m in a.motius or ["(sense motius)"]]
    if a.alertes:
        t += ["", "## Alertes", ""] + [f"- {x}" for x in a.alertes]
    t += ["", "## Comprovacions als plecs (PCAP i PPT)", "",
          "- [ ] Solvència econòmica: xifra de negoci mínima demanada i any de referència.",
          "- [ ] Solvència tècnica: treballs similars dels darrers 3 anys (import i certificats).",
          "- [ ] Classificació empresarial o inscripció al RELI / ROLECE.",
          "- [ ] Criteris d'adjudicació: pes del preu, criteris automàtics i criteris de judici de valor.",
          "- [ ] Propietat intel·lectual i industrial: cessió de drets dels dissenys i dels prototips.",
          "- [ ] Equip mínim, dedicació i perfils obligatoris.",
          "- [ ] Termini d'execució, fites i penalitats.",
          "- [ ] Garantia definitiva (habitualment el 5 %) i forma de pagament.",
          "- [ ] Subcontractació permesa i possibilitat d'UTE amb un soci.",
          "- [ ] Lots: a quins ens podem presentar.",
          "- [ ] Data límit per a preguntes i sessió informativa, si n'hi ha.",
          "- [ ] Documentació: DEUC, declaracions, sobre digital i signatura electrònica.",
          "", "## Decisió", "",
          f"- **Go / No-go:** {estat.get('estat') if estat.get('estat') in ('go', 'no-go') else '[pendent]'}",
          f"- **Motiu:** {estat.get('motiu') or '[pendent]'}",
          f"- **Responsable:** {estat.get('responsable') or '[pendent]'}",
          "- **Hores estimades de preparació:** [pendent]",
          "- **Socis o subcontractes:** [pendent]"]
    if estat.get("notes"):
        t += ["", "## Notes", "", estat["notes"]]
    return "\n".join(t) + "\n"
