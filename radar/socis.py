"""Socis potencials per a cada ajut, a partir dels contactes de Holded.

1. Agrupa els contactes per organització (NIF o domini de correu) i hi associa les persones.
2. Classifica cada organització: tipus (recerca, hospital, empresa, startup, cluster, inversor),
   zona i temes (focus). Fonts, per ordre de prioritat:
   - fitxer privat de classificació (privat/socis.yaml o la variable RADAR_SOCIS_YAML);
   - etiquetes de Holded amb el prefix `radar-` (p. ex. `radar-robotica`, `radar-tipus-recerca`);
   - heurístiques pel nom.
3. Puntua cada organització per a una convocatòria: tipus de soci que cal, temes compartits,
   elegibilitat per zona (si hauria de ser la sol·licitant) i relació amb Stimulo.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .dades import FOCUS, TIPUS_SOCI, Convocatoria
from .holded import Contacte, zona
from .vigilancia import normalitza
from .zones import Zones

DOMINIS_PERSONALS = {"gmail.com", "hotmail.com", "outlook.com", "yahoo.es", "yahoo.com", "icloud.com",
                     "mail.com", "live.com", "msn.com", "hotmail.es"}
PREFIXOS_GENERICS = ("factura", "facturas", "facturacion", "facturaracion", "admin", "administracion",
                     "administracio", "comptabilitat", "contabilidad", "conta", "finance", "financiero",
                     "accounting", "legal", "marketing", "comunicacio", "info", "informacion", "admon",
                     "comercial", "contact", "contacto", "hola", "hello", "office", "sales", "ventas",
                     "institutrecerca", "orto")
# Paraules que indiquen que un contacte és una organització i no una persona (coincidència de prefix)
RE_ORGANITZACIO = re.compile(r"\b(s\.?\s?l\.?u?\b|s\.?\s?a\.?\b|sgeic|sociedad|fundaci|universit|institut|instituto"
                             r"|csic|hospital|cluster|agencia|coop|centre|centro|inc\b|gmbh|ltd)", re.I)
RELACIO = {"client": 2.0, "supplier": 1.5, "lead": 1.0}

HEURISTIQUES_TIPUS = [
    (r"universit|\bupc\b|\buab\b|\bupf\b|\biqs\b|escola tecnica", "recerca"),
    (r"\bcsic\b|instituto de|institut d|institut de|fundacio.*(recerca|investigacio)|research|eurecat|leitat"
     r"|centre tecnologic|centro tecnologico|idib", "recerca"),
    (r"hospital|clinic|investigacion sanitaria|recerca sanitaria|institut de recerca biomedica", "hospital"),
    (r"cluster|secpho|southern european cluster", "cluster"),
    (r"capital|ventures|inversiones|invest\b|sgeic", "inversor"),
]
HEURISTIQUES_FOCUS = [
    (r"robot", ["robotica"]), (r"optic|photon|fotonic|laser|vision", ["fotonica"]),
    (r"quant", ["deep_tech", "fotonica"]), (r"medic|surgi|biomed|health|salut|sanitar|ortho|orto|implant|diagnos",
                                             ["salut", "dispositius_medics"]),
    (r"hospital|recerca biomedica|investigacio biomedica|investigacion sanitaria", ["salut", "dispositius_medics"]),
    (r"water|aqua|aigua|agua", ["aigua"]), (r"agro|agri|farm", ["agrotech"]),
    (r"energ|power|charg|solar", ["energia"]), (r"motor|automoci|automotive|vehic", ["automocio", "mobilitat"]),
    (r"drone|dron", ["dual", "robotica"]), (r"materials", ["deep_tech", "sostenibilitat"]),
    (r"plastic|recicl|circular", ["economia_circular"]),
]


@dataclass
class Soci:
    clau: str
    nom: str
    tipus: str  # recerca / hospital / empresa / startup / cluster / inversor
    relacio: str  # client / supplier / lead
    zona: str | None
    focus: list[str]
    persones: list[dict] = field(default_factory=list)  # [{nom, email, carrec}]
    emails_generics: list[str] = field(default_factory=list)
    nota: str = ""
    ids_holded: list[str] = field(default_factory=list)

    @property
    def destinatari(self) -> dict | None:
        if self.persones:
            return self.persones[0]
        if self.emails_generics:
            return {"nom": "", "email": self.emails_generics[0], "carrec": "", "generic": True}
        return None


@dataclass
class Proposta:
    soci: Soci
    punts: float
    rol: str  # sol·licitant / soci de consorci / client beneficiari / inversor
    motius: list[str]


def _es_generic(email: str) -> bool:
    local, _, domini = email.lower().partition("@")
    if local and local in domini.split(".")[0]:
        return True  # p. ex. empresa@empresa.com
    return any(local == p or local.startswith(p + ".") or (local.startswith(p) and len(local) <= len(p) + 2)
               for p in PREFIXOS_GENERICS)


def nom_des_del_correu(email: str) -> str:
    """'anna.puig@exemple.com' -> 'Anna' (només si té forma de nom.cognom)."""
    local = email.split("@")[0]
    parts = re.split(r"[._-]", local)
    if len(parts) >= 2 and all(p.isalpha() and len(p) > 1 for p in parts[:2]):
        return parts[0].capitalize()
    return ""


def _es_persona_sense_empresa(c: Contacte) -> bool:
    return (c.nom.lower() in ("name", "") or c.domini in DOMINIS_PERSONALS) and not c.nom_comercial


def _clau_organitzacio(c: Contacte) -> str | None:
    nif = re.sub(r"\s", "", c.nif).upper()
    if re.fullmatch(r"[A-Z]{1,2}\d{7,8}[A-Z0-9]?", nif) and not nif.startswith("Q"):
        return "nif:" + nif
    if c.domini and c.domini not in DOMINIS_PERSONALS:
        return "dom:" + c.domini
    if c.nom_comercial:
        return "nom:" + normalitza(c.nom_comercial)
    return None


def carrega_classificacio(path: Path | None = None) -> list[dict]:
    """Classificació manual privada (no es desa al repositori)."""
    text = os.environ.get("RADAR_SOCIS_YAML", "")
    if not text:
        path = path or Path(os.environ.get("RADAR_SOCIS", "privat/socis.yaml"))
        if path.exists():
            text = path.read_text(encoding="utf-8")
    if not text:
        return []
    return (yaml.safe_load(text) or {}).get("socis", [])


def _troba_override(noms: str, ids: list[str], dominis: set[str], classificacio: list[dict]) -> dict | None:
    n = normalitza(noms)
    for o in classificacio:
        if o.get("holded_id") and o["holded_id"] in ids:
            return o
        if o.get("domini") and o["domini"].lower() in dominis:
            return o
        if o.get("nom") and normalitza(o["nom"]) in n:
            return o
    return None


def construeix(contactes: list[Contacte], classificacio: list[dict] | None = None) -> list[Soci]:
    classificacio = classificacio if classificacio is not None else carrega_classificacio()
    grups: dict[str, list[Contacte]] = {}
    for c in contactes:
        if _es_persona_sense_empresa(c):
            continue
        clau = _clau_organitzacio(c)
        if clau:
            grups.setdefault(clau, []).append(c)
    # Uneix grups per NIF i per domini quan comparteixen domini (persones de la mateixa empresa)
    per_domini: dict[str, str] = {}
    for clau, cs in list(grups.items()):
        for c in cs:
            if c.domini and c.domini not in DOMINIS_PERSONALS and clau.startswith("nif:"):
                per_domini.setdefault(c.domini, clau)
    for clau in [k for k in grups if k.startswith("dom:")]:
        desti = per_domini.get(clau[4:])
        if desti and desti != clau:
            grups[desti] += grups.pop(clau)

    socis = []
    for clau, cs in grups.items():
        empresa = next((c for c in cs if RE_ORGANITZACIO.search(c.nom)), cs[0])
        nom = empresa.nom_comercial if empresa.nom_comercial and len(empresa.nom_comercial) < 40 else empresa.nom
        nom = nom.strip(" .'\"")
        persones, generics, vistos = [], [], set()

        def es_nom_de_persona(c: Contacte) -> bool:
            return bool(c.nom) and c.nom.lower() != "name" and not RE_ORGANITZACIO.search(c.nom)

        # Primer les persones (contactPersons i contactes amb nom de persona), després l'adreça de l'empresa
        for c in sorted(cs, key=lambda c: not es_nom_de_persona(c)):
            for p in c.persones:
                if p["email"] and p["email"] not in vistos:
                    vistos.add(p["email"])
                    persones.append(p)
            if c.email and c.email not in vistos:
                vistos.add(c.email)
                if _es_generic(c.email):
                    generics.append(c.email)
                else:
                    persones.append({"nom": c.nom if es_nom_de_persona(c) else "", "email": c.email, "carrec": ""})
        relacio = min((c.tipus for c in cs if c.tipus in RELACIO), key=lambda t: -RELACIO[t], default="lead")
        text = normalitza(" ".join([c.nom + " " + c.nom_comercial + " " + c.domini for c in cs]))
        tags = {t for c in cs for t in c.tags}
        ids = [c.id for c in cs]
        dominis = {c.domini for c in cs if c.domini}

        noms = " | ".join(f"{c.nom} {c.nom_comercial}" for c in cs)
        o = _troba_override(noms, ids, dominis, classificacio) or {}
        tipus = o.get("tipus") or next((t[len("radar-tipus-"):] for t in tags if t.startswith("radar-tipus-")), None)
        if not tipus:
            tipus = next((t for patro, t in HEURISTIQUES_TIPUS if re.search(patro, text)), "empresa")
        focus = list(o.get("focus") or [])
        focus += [t[len("radar-"):] for t in tags if t.startswith("radar-") and t[len("radar-"):] in FOCUS]
        if not focus:
            for patro, temes in HEURISTIQUES_FOCUS:
                if re.search(patro, text):
                    focus += temes
        if tipus in ("recerca", "hospital") and "transferencia" not in focus:
            focus.append("transferencia")
        if o.get("exclou"):
            continue
        soci_zona = o.get("zona") or next((z for z in (zona(c) for c in cs) if z), None)
        socis.append(Soci(
            clau=clau, nom=o.get("nom_visible") or nom, tipus=tipus if tipus in TIPUS_SOCI else "empresa",
            relacio=relacio, zona=soci_zona, focus=sorted(set(focus)), persones=persones,
            emails_generics=generics, nota=o.get("nota", ""), ids_holded=ids,
        ))
    # Fusiona organitzacions que han quedat duplicades (p. ex. dos dominis del mateix institut)
    fusionats: dict[str, Soci] = {}
    for s in socis:
        clau_nom = normalitza(s.nom)
        if clau_nom in fusionats:
            a = fusionats[clau_nom]
            a.persones += [p for p in s.persones if p["email"] not in {x["email"] for x in a.persones}]
            a.emails_generics += [g for g in s.emails_generics if g not in a.emails_generics]
            a.focus = sorted(set(a.focus) | set(s.focus))
            a.ids_holded += s.ids_holded
            a.zona = a.zona or s.zona
            if RELACIO.get(s.relacio, 0) > RELACIO.get(a.relacio, 0):
                a.relacio = s.relacio
        else:
            fusionats[clau_nom] = s
    return list(fusionats.values())


def tipus_necessaris(c: Convocatoria) -> list[str]:
    """Quins tipus de soci cal buscar per a una convocatòria."""
    if c.socis_cal:
        return c.socis_cal
    b = set(c.beneficiaris)
    sortida = []
    if b & {"universitat", "centre_recerca"} or "transferencia" in c.focus or "consorci" in b:
        sortida.append("recerca")
    if "hospital" in b or {"salut", "dispositius_medics"} & set(c.focus) and b & {"universitat", "centre_recerca"}:
        sortida.append("hospital")
    if b & {"pime", "gran_empresa"}:
        sortida.append("empresa")
    if "startup" in b:
        sortida.append("startup")
    if c.instrument == "capital":
        sortida.append("inversor")
    return sortida or ["empresa"]


def proposa(c: Convocatoria, socis: list[Soci], zones: Zones, maxim: int = 3) -> list[Proposta]:
    necessaris = tipus_necessaris(c)
    sollicitants = set(c.beneficiaris)
    propostes = []
    for s in socis:
        tipus_ok = s.tipus in necessaris or (s.tipus == "startup" and "empresa" in necessaris) \
            or (s.tipus == "empresa" and "startup" in necessaris)
        if not tipus_ok:
            continue
        temes = [f for f in c.focus if f in s.focus]
        if not temes and s.tipus not in ("inversor", "cluster"):
            continue
        # Seria el sol·licitant? Llavors ha de ser elegible per zona
        es_sollicitant = (s.tipus == "recerca" and sollicitants & {"universitat", "centre_recerca"}) or \
                         (s.tipus == "hospital" and "hospital" in sollicitants) or \
                         (s.tipus in ("empresa", "startup") and sollicitants & {"pime", "gran_empresa", "startup"})
        motius = []
        if temes:
            motius.append("temes: " + ", ".join(temes))
        if es_sollicitant:
            if s.zona is None:
                motius.append("zona per confirmar")
            elif not zones.es_elegible(s.zona, c.zones):
                continue
            else:
                motius.append(f"elegible ({zones.nom(s.zona)})")
        punts = 3 + 2 * len(temes) + RELACIO.get(s.relacio, 1.0)
        if s.persones:
            punts += 1
        elif not s.emails_generics:
            punts -= 1
        if es_sollicitant and "proveidor_extern" in c.rols_stimulo:
            rol = "sol·licitant (Stimulo com a proveïdor)"
        elif es_sollicitant:
            rol = "sol·licitant o soci del consorci"
        elif s.tipus in ("recerca", "hospital", "empresa", "startup"):
            rol = "soci de consorci"
        else:
            rol = "inversor" if s.tipus == "inversor" else "enllaç / clúster"
        motius.insert(0, {"client": "client", "supplier": "proveïdor", "lead": "contacte"}.get(s.relacio, s.relacio))
        propostes.append(Proposta(s, punts, rol, motius))
    propostes.sort(key=lambda p: -p.punts)
    # Diversitat: no més de 2 del mateix tipus si n'hi ha d'altres
    triats, per_tipus = [], {}
    for p in propostes:
        if per_tipus.get(p.soci.tipus, 0) >= 2 and len(necessaris) > 1:
            continue
        triats.append(p)
        per_tipus[p.soci.tipus] = per_tipus.get(p.soci.tipus, 0) + 1
        if len(triats) >= maxim:
            break
    return triats
