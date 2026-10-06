"""Lectura de contactes de Holded (només lectura) per suggerir socis per a cada ajut.

Dues fonts possibles:
- API de Holded amb la clau a la variable d'entorn HOLDED_API_KEY (GitHub Actions).
- Un fitxer JSON exportat (privat/holded_contactes.json), amb el format de l'API o el del
  connector de Holded de Claude (camps nom, nomComercial, tipus, email, telefon, nif).

Les dades de contactes MAI es desen al repositori: només viatgen dins del correu de l'avís.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

API = "https://api.holded.com/api/invoicing/v1/contacts"

PROVINCIES = {
    "barcelona": "ES-CT-B", "girona": "ES-CT-GI", "gerona": "ES-CT-GI", "lleida": "ES-CT-L", "lerida": "ES-CT-L",
    "tarragona": "ES-CT-T", "madrid": "ES-MD", "valencia": "ES-VC", "alicante": "ES-VC", "alacant": "ES-VC",
    "castellon": "ES-VC", "castello": "ES-VC", "almeria": "ES-AN-AL", "sevilla": "ES-AN", "malaga": "ES-AN",
    "cadiz": "ES-AN", "cordoba": "ES-AN", "granada": "ES-AN", "huelva": "ES-AN", "jaen": "ES-AN",
    "navarra": "ES-NC", "gipuzkoa": "ES-PV", "guipuzcoa": "ES-PV", "bizkaia": "ES-PV", "vizcaya": "ES-PV",
    "alava": "ES-PV", "araba": "ES-PV", "zaragoza": "ES-AR", "huesca": "ES-AR", "teruel": "ES-AR",
    "murcia": "ES-MC", "baleares": "ES-IB", "illes balears": "ES-IB", "las palmas": "ES-CN",
    "santa cruz de tenerife": "ES-CN", "a coruna": "ES-GA", "la coruna": "ES-GA", "lugo": "ES-GA",
    "ourense": "ES-GA", "pontevedra": "ES-GA", "leon": "ES-CL", "burgos": "ES-CL", "valladolid": "ES-CL",
    "salamanca": "ES-CL", "segovia": "ES-CL", "avila": "ES-CL", "soria": "ES-CL", "palencia": "ES-CL",
    "zamora": "ES-CL", "toledo": "ES-CM", "ciudad real": "ES-CM", "cuenca": "ES-CM", "guadalajara": "ES-CM",
    "albacete": "ES-CM", "badajoz": "ES-EX", "caceres": "ES-EX",
}
# Prefixos de telèfon fix (quan no hi ha adreça): aproximació per províncies
PREFIXOS = [
    ("972", "ES-CT-GI"), ("872", "ES-CT-GI"), ("973", "ES-CT-L"), ("977", "ES-CT-T"), ("93", "ES-CT-B"),
    ("91", "ES-MD"), ("96", "ES-VC"), ("943", "ES-PV"), ("944", "ES-PV"), ("945", "ES-PV"), ("946", "ES-PV"),
    ("948", "ES-NC"), ("922", "ES-CN"), ("928", "ES-CN"), ("822", "ES-CN"), ("950", "ES-AN-AL"),
    ("95", "ES-AN"), ("968", "ES-MC"), ("971", "ES-IB"), ("976", "ES-AR"), ("974", "ES-AR"), ("978", "ES-AR"),
    ("981", "ES-GA"), ("986", "ES-GA"), ("988", "ES-GA"), ("982", "ES-GA"),
]
PAISOS = {"ES": "ES", "PT": "PT", "FR": "FR", "IT": "IT", "DE": "DE"}


@dataclass
class Contacte:
    id: str
    nom: str
    nom_comercial: str
    tipus: str  # client / supplier / lead / ...
    email: str
    telefon: str
    nif: str
    provincia: str = ""
    pais: str = ""
    tags: list[str] = field(default_factory=list)
    persones: list[dict] = field(default_factory=list)  # [{nom, email, carrec}]

    @property
    def domini(self) -> str:
        return self.email.split("@")[-1].lower() if self.email and "@" in self.email else ""


def _txt(v) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()


def normalitza(d: dict) -> Contacte:
    """Accepta el format de l'API de Holded i el del connector (claus en català)."""
    adreca = d.get("billAddress") or {}
    persones = [
        {"nom": _txt(p.get("name")), "email": _txt(p.get("email")), "carrec": _txt(p.get("job"))}
        for p in (d.get("contactPersons") or []) if p.get("email")
    ]
    return Contacte(
        id=_txt(d.get("id")),
        nom=_txt(d.get("name") or d.get("nom")),
        nom_comercial=_txt(d.get("tradeName") or d.get("nomComercial")).strip("\"'"),
        tipus=_txt(d.get("type") or d.get("tipus")),
        email=_txt(d.get("email")),
        telefon=_txt(d.get("phone") or d.get("mobile") or d.get("telefon")),
        nif=_txt(d.get("code") or d.get("vatnumber") or d.get("nif")),
        provincia=_txt(adreca.get("province")),
        pais=_txt(adreca.get("countryCode")).upper(),
        tags=[_txt(t).lower() for t in (d.get("tags") or [])],
        persones=persones,
    )


def des_de_fitxer(path: Path) -> list[Contacte]:
    dades = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(dades, dict):
        dades = dades.get("contacts") or dades.get("contactes") or []
    vistos, sortida = set(), []
    for d in dades:
        c = normalitza(d)
        if c.id and c.id not in vistos:
            vistos.add(c.id)
            sortida.append(c)
    return sortida


def des_de_api(clau: str | None = None, max_pagines: int = 20) -> list[Contacte]:
    clau = clau or os.environ.get("HOLDED_API_KEY", "")
    if not clau:
        raise RuntimeError("Falta HOLDED_API_KEY")
    sortida: list[Contacte] = []
    for pagina in range(1, max_pagines + 1):
        req = urllib.request.Request(f"{API}?{urllib.parse.urlencode({'page': pagina})}",
                                     headers={"key": clau, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=40) as r:  # noqa: S310 (URL fixa de l'API de Holded)
            lot = json.loads(r.read())
        if not isinstance(lot, list) or not lot:
            break
        sortida += [normalitza(d) for d in lot]
        if len(lot) < 500:
            break
    return sortida


def zona(c: Contacte) -> str | None:
    """Codi de zona (data/zones.yaml) a partir de la província, el país o el prefix telefònic."""
    from .vigilancia import normalitza as sense_accents

    prov = sense_accents(c.provincia)
    if prov in PROVINCIES:
        return PROVINCIES[prov]
    if c.pais and c.pais != "ES":
        return PAISOS.get(c.pais, "INT")
    nif = c.nif.replace(" ", "").upper()
    if len(nif) > 2 and nif[:2].isalpha() and nif[:2] not in ("ES",):
        return PAISOS.get(nif[:2], "INT")
    tel = re.sub(r"\D", "", c.telefon).removeprefix("34") if c.telefon else ""
    if len(tel) == 9 and tel[0] in "89":
        for prefix, codi in PREFIXOS:
            if tel.startswith(prefix):
                return codi
    return None
