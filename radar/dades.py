"""Càrrega i validació del catàleg del radar (data/*.yaml)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .zones import Zones

ARREL = Path(__file__).resolve().parent.parent
DIR_DADES = ARREL / "data"

NIVELLS = ("local", "catalunya", "estat", "europa", "internacional")
ORIGENS = ("public", "privat", "universitat", "fundacio_publica", "fundacio_privada", "corporatiu", "mixt")
INSTRUMENTS = (
    "subvencio",
    "prestec",
    "prestec_parcialment_reemborsable",
    "cupo",
    "premi",
    "capital",
    "acceleracio",
    "licitacio",
    "compra_publica_innovacio",
    "beca_contracte",
    "mixt",
)
RECURRENCIES = ("anual", "multiples_talls", "continua", "puntual", "desconeguda")
ESTATS = ("oberta", "tancada", "prevista", "permanent", "desconegut")
# Etiquetes temàtiques comunes (perfils i convocatòries comparteixen aquest vocabulari)
FOCUS = (
    "deep_tech",
    "dual",
    "defensa",
    "espai",
    "sostenibilitat",
    "economia_circular",
    "transferencia",
    "prova_concepte",
    "mobilitat",
    "automocio",
    "robotica",
    "agrotech",
    "aigua",
    "salut",
    "dispositius_medics",
    "fotonica",
    "digital",
    "ia",
    "industria",
    "energia",
    "internacionalitzacio",
    "creixement_startup",
    "talent",
    "disseny",
    "cooperacio",
)
ROLS = ("beneficiari", "soci", "proveidor_extern", "subcontractat", "assessor")
# Tipus de soci que el radar busca a Holded per a cada convocatòria (radar/socis.py)
TIPUS_SOCI = ("recerca", "hospital", "empresa", "startup", "cluster", "inversor")


@dataclass
class Calendari:
    recurrencia: str = "desconeguda"
    estat: str = "desconegut"
    obertura: dt.date | None = None
    tancament: dt.date | None = None
    talls: list[dt.date] = field(default_factory=list)
    mes_obertura_habitual: int | None = None
    mes_tancament_habitual: int | None = None
    finestra_habitual: str = ""
    verificat: dt.date | None = None
    revisar: dt.date | None = None  # data en què cal tornar a mirar la font (genera un senyal)
    revisar_motiu: str = ""


@dataclass
class Convocatoria:
    id: str
    nom: str
    entitat: str
    nivell: str
    origen: str
    instrument: str
    descripcio: str
    zones: list[str]
    ambit_geografic: str
    beneficiaris: list[str]
    focus: list[str]
    rols_stimulo: list[str]
    calendari: Calendari
    url: str = ""
    fons: str = ""
    intensitat_max: float | None = None
    import_max_eur: float | None = None
    pressupost_min_eur: float | None = None
    pressupost_total_eur: float | None = None
    durada_max_mesos: int | None = None
    trl: tuple[int, int] | None = None
    modalitat: str = ""
    ajuda_text: str = ""
    notes: str = ""
    fonts_verificacio: list[str] = field(default_factory=list)
    excel_fila: int | None = None
    confianca: str = "mitjana"  # alta (font oficial verificada) / mitjana / baixa (estimació)
    encaix_stimulo: str = ""  # per què encaixa amb Stimulo (text curat per a l'avís per correu)
    punts_forts: list[str] = field(default_factory=list)  # altres consideracions positives
    socis_cal: list[str] = field(default_factory=list)  # tipus de soci a buscar (vegeu radar/socis.py)


@dataclass
class Perfil:
    id: str
    nom: str
    tipus: str  # agencia / client / startup
    zona: str
    beneficiari_com: list[str]  # p. ex. [pime, startup]
    rols: list[str]
    focus: dict[str, int]
    trl: tuple[int, int] | None
    descripcio: str = ""
    paraules_clau: list[str] = field(default_factory=list)
    sectors: list[str] = field(default_factory=list)
    contacte: str = ""
    actiu: bool = True  # els perfils inactius (clients de servei) no es puntuen per defecte


@dataclass
class Font:
    id: str
    nom: str
    nivell: str
    url: str
    metode: str  # api / rss / web / butlleti / manual
    frequencia: str
    cobreix: str = ""
    vigilant: str | None = None  # nom del vigilant automàtic a radar.vigilancia
    notes: str = ""


@dataclass
class Cataleg:
    convocatories: list[Convocatoria]
    perfils: dict[str, Perfil]
    fonts: list[Font]
    zones: Zones
    config: dict

    def per_id(self, id_: str) -> Convocatoria:
        for c in self.convocatories:
            if c.id == id_:
                return c
        raise KeyError(id_)


class ErrorValidacio(ValueError):
    pass


def _data(valor, context: str) -> dt.date | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, dt.datetime):
        return valor.date()
    if isinstance(valor, dt.date):
        return valor
    try:
        return dt.date.fromisoformat(str(valor))
    except ValueError as e:
        raise ErrorValidacio(f"{context}: data no vàlida '{valor}' (format AAAA-MM-DD)") from e


def _trl(valor, context: str) -> tuple[int, int] | None:
    if valor in (None, ""):
        return None
    if isinstance(valor, int):
        return (valor, valor)
    if isinstance(valor, (list, tuple)) and len(valor) == 2:
        a, b = int(valor[0]), int(valor[1])
        if not (1 <= a <= b <= 9):
            raise ErrorValidacio(f"{context}: TRL fora de rang {valor}")
        return (a, b)
    raise ErrorValidacio(f"{context}: TRL ha de ser [min, max], no {valor!r}")


def _comprova(valor, permesos, context: str):
    if valor not in permesos:
        raise ErrorValidacio(f"{context}: valor '{valor}' no permès; opcions: {', '.join(permesos)}")


def _llegeix_yaml(path: Path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _convocatoria(d: dict, zones: Zones) -> Convocatoria:
    cid = d.get("id") or "?"
    ctx = f"convocatòria {cid}"
    for obligatori in ("id", "nom", "entitat", "nivell", "origen", "instrument", "zones"):
        if obligatori not in d:
            raise ErrorValidacio(f"{ctx}: falta el camp '{obligatori}'")
    _comprova(d["nivell"], NIVELLS, ctx)
    _comprova(d["origen"], ORIGENS, ctx)
    _comprova(d["instrument"], INSTRUMENTS, ctx)
    for z in d["zones"]:
        if not zones.existeix(z):
            raise ErrorValidacio(f"{ctx}: zona desconeguda '{z}' (afegeix-la a data/zones.yaml)")
    for f_ in d.get("focus", []):
        _comprova(f_, FOCUS, ctx + " (focus)")
    for r in d.get("rols_stimulo", []):
        _comprova(r, ROLS, ctx + " (rols_stimulo)")
    for s in d.get("socis_cal", []):
        _comprova(s, TIPUS_SOCI, ctx + " (socis_cal)")

    cal = d.get("calendari", {}) or {}
    _comprova(cal.get("recurrencia", "desconeguda"), RECURRENCIES, ctx + " (recurrencia)")
    _comprova(cal.get("estat", "desconegut"), ESTATS, ctx + " (estat)")
    calendari = Calendari(
        recurrencia=cal.get("recurrencia", "desconeguda"),
        estat=cal.get("estat", "desconegut"),
        obertura=_data(cal.get("obertura"), ctx),
        tancament=_data(cal.get("tancament"), ctx),
        talls=sorted(_data(t, ctx) for t in cal.get("talls", []) or []),
        mes_obertura_habitual=cal.get("mes_obertura_habitual"),
        mes_tancament_habitual=cal.get("mes_tancament_habitual"),
        finestra_habitual=cal.get("finestra_habitual", ""),
        verificat=_data(cal.get("verificat"), ctx),
        revisar=_data(cal.get("revisar"), ctx),
        revisar_motiu=cal.get("revisar_motiu", ""),
    )
    for mes in (calendari.mes_obertura_habitual, calendari.mes_tancament_habitual):
        if mes is not None and not 1 <= int(mes) <= 12:
            raise ErrorValidacio(f"{ctx}: mes fora de rang {mes}")
    if calendari.obertura and calendari.tancament and calendari.obertura > calendari.tancament:
        raise ErrorValidacio(f"{ctx}: obertura posterior al tancament")

    return Convocatoria(
        id=d["id"],
        nom=d["nom"],
        entitat=d["entitat"],
        nivell=d["nivell"],
        origen=d["origen"],
        instrument=d["instrument"],
        descripcio=d.get("descripcio", "").strip(),
        zones=list(d["zones"]),
        ambit_geografic=d.get("ambit_geografic", "").strip(),
        beneficiaris=list(d.get("beneficiaris", [])),
        focus=list(d.get("focus", [])),
        rols_stimulo=list(d.get("rols_stimulo", [])),
        calendari=calendari,
        url=d.get("url", ""),
        fons=d.get("fons", ""),
        intensitat_max=d.get("intensitat_max"),
        import_max_eur=d.get("import_max_eur"),
        pressupost_min_eur=d.get("pressupost_min_eur"),
        pressupost_total_eur=d.get("pressupost_total_eur"),
        durada_max_mesos=d.get("durada_max_mesos"),
        trl=_trl(d.get("trl"), ctx),
        modalitat=d.get("modalitat", ""),
        ajuda_text=d.get("ajuda_text", "").strip(),
        notes=d.get("notes", "").strip(),
        fonts_verificacio=list(d.get("fonts_verificacio", [])),
        excel_fila=d.get("excel_fila"),
        confianca=d.get("confianca", "mitjana"),
        encaix_stimulo=d.get("encaix_stimulo", "").strip(),
        punts_forts=list(d.get("punts_forts", [])),
        socis_cal=list(d.get("socis_cal", [])),
    )


def _perfil(id_: str, d: dict, zones: Zones) -> Perfil:
    ctx = f"perfil {id_}"
    if not zones.existeix(d["zona"]):
        raise ErrorValidacio(f"{ctx}: zona desconeguda '{d['zona']}'")
    for f_ in d.get("focus", {}):
        _comprova(f_, FOCUS, ctx + " (focus)")
    for r in d.get("rols", []):
        _comprova(r, ROLS, ctx + " (rols)")
    return Perfil(
        id=id_,
        nom=d["nom"],
        tipus=d["tipus"],
        zona=d["zona"],
        beneficiari_com=list(d.get("beneficiari_com", [])),
        rols=list(d.get("rols", [])),
        focus=dict(d.get("focus", {})),
        trl=_trl(d.get("trl"), ctx),
        descripcio=d.get("descripcio", "").strip(),
        paraules_clau=list(d.get("paraules_clau", [])),
        sectors=list(d.get("sectors", [])),
        contacte=d.get("contacte", ""),
        actiu=bool(d.get("actiu", True)),
    )


def carrega(dir_dades: Path = DIR_DADES, inclou_inactius: bool = False) -> Cataleg:
    """Carrega el catàleg. Per defecte només hi entren els perfils actius (Stimulo)."""
    zones = Zones(_llegeix_yaml(dir_dades / "zones.yaml"))
    brut = _llegeix_yaml(dir_dades / "convocatories.yaml")
    convocatories = [_convocatoria(d, zones) for d in brut["convocatories"]]
    ids = [c.id for c in convocatories]
    duplicats = {i for i in ids if ids.count(i) > 1}
    if duplicats:
        raise ErrorValidacio(f"Ids duplicats: {', '.join(sorted(duplicats))}")

    perfils_brut = _llegeix_yaml(dir_dades / "perfils.yaml")
    perfils = {pid: _perfil(pid, d, zones) for pid, d in perfils_brut["perfils"].items()}
    if not inclou_inactius:
        perfils = {pid: p for pid, p in perfils.items() if p.actiu}
    if not perfils:
        raise ErrorValidacio("Cal com a mínim un perfil actiu a data/perfils.yaml")

    fonts = [Font(**f) for f in _llegeix_yaml(dir_dades / "fonts.yaml")["fonts"]]
    for f in fonts:
        _comprova(f.nivell, NIVELLS + ("transversal",), f"font {f.id}")

    config = perfils_brut.get("config", {})
    return Cataleg(convocatories=convocatories, perfils=perfils, fonts=fonts, zones=zones, config=config)
