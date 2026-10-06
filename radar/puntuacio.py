"""Puntuació d'encaix (0-100) d'una convocatòria amb un perfil.

Components (pesos per defecte, configurables a perfils.yaml > config.pesos):
- tematica   40  focus de la convocatòria x interessos ponderats del perfil
- rol        20  pot ser-ne beneficiari? o hi pot entrar com a soci / proveïdor?
- zona       15  el perfil és elegible per la seva ubicació (si no, puntuació 0)
- trl        10  solapament amb el rang TRL del perfil
- impacte    15  import màxim de l'ajut (escala logarítmica)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .dades import Convocatoria, Perfil
from .zones import Zones

PESOS_PER_DEFECTE = {"tematica": 40, "rol": 20, "zona": 15, "trl": 10, "impacte": 15}
LLINDAR_A, LLINDAR_B = 80, 65
VALOR_ROL = {"beneficiari": 1.0, "soci": 0.8, "proveidor_extern": 0.75, "subcontractat": 0.6, "assessor": 0.4}


@dataclass
class Encaix:
    punts: int
    prioritat: str  # A / B / C / NE (no elegible)
    elegible: bool
    rol: str | None
    detall: dict[str, float]
    motius: list[str]


def _tematica(c: Convocatoria, p: Perfil) -> tuple[float, list[str]]:
    if not p.focus:
        return 0.0, []
    coincidencies = sorted(((p.focus[f], f) for f in c.focus if f in p.focus), reverse=True)
    if not coincidencies:
        return 0.0, []
    millors = sorted(p.focus.values(), reverse=True)[:4]
    sostre = sum(millors) or 1
    valor = min(1.0, sum(w for w, _ in coincidencies[:4]) / sostre)
    return valor, [f for _, f in coincidencies]


def _rol(c: Convocatoria, p: Perfil, elegible_zona: bool) -> tuple[float, str | None]:
    # Beneficiari directe si el tipus d'entitat del perfil hi és admès i és a la zona.
    # Per a l'agència, a més, la fitxa ha de preveure-ho a rols_stimulo (ser pime no basta:
    # p. ex. a l'EIC Accelerator Stimulo hi entra com a proveïdor de la startup, no com a sol·licitant).
    pot_ser_beneficiari = set(p.beneficiari_com) & set(c.beneficiaris)
    if p.tipus == "agencia":
        pot_ser_beneficiari = pot_ser_beneficiari and "beneficiari" in c.rols_stimulo
    if elegible_zona and "beneficiari" in p.rols and pot_ser_beneficiari:
        return VALOR_ROL["beneficiari"], "beneficiari"
    # Rols indirectes (soci, proveïdor, subcontractat): no depenen de la zona del perfil,
    # sinó de la del client beneficiari
    millor, nom = 0.0, None
    for r in c.rols_stimulo:
        if r == "beneficiari":
            continue
        if r in p.rols and VALOR_ROL.get(r, 0) > millor:
            millor, nom = VALOR_ROL[r], r
    return millor, nom


def _trl(c: Convocatoria, p: Perfil) -> float:
    if not c.trl or not p.trl:
        return 0.5
    a = max(c.trl[0], p.trl[0])
    b = min(c.trl[1], p.trl[1])
    return 1.0 if a <= b else 0.0


def _impacte(c: Convocatoria) -> float:
    if not c.import_max_eur:
        return 0.3
    # 5.000 EUR -> 0 ; 2.500.000 EUR -> 1
    return max(0.0, min(1.0, math.log10(c.import_max_eur / 5_000) / math.log10(500)))


def puntua(c: Convocatoria, p: Perfil, zones: Zones, pesos: dict | None = None) -> Encaix:
    w = {**PESOS_PER_DEFECTE, **(pesos or {})}
    elegible = zones.es_elegible(p.zona, c.zones)
    tema, temes = _tematica(c, p)
    rol, nom_rol = _rol(c, p, elegible)
    trl = _trl(c, p)
    imp = _impacte(c)
    if elegible:
        zona = 1.0
    elif nom_rol is not None:
        zona = 0.5  # hi pot entrar via un client beneficiari d'aquella zona
    else:
        zona = 0.0
    detall = {
        "tematica": tema * w["tematica"],
        "rol": rol * w["rol"],
        "zona": zona * w["zona"],
        "trl": trl * w["trl"],
        "impacte": imp * w["impacte"],
    }
    total = round(sum(detall.values()))
    motius = []
    if temes:
        motius.append("temes: " + ", ".join(temes))
    if nom_rol:
        motius.append(f"rol: {nom_rol}")
    if not elegible:
        motius.append(f"fora de zona com a beneficiari ({p.zona})")
    if nom_rol is None:
        if not elegible:
            prioritat = "NE"
        else:
            motius.append("sense rol possible")
            prioritat = "C"
        total = min(total, 40)
    elif total >= LLINDAR_A:
        prioritat = "A"
    elif total >= LLINDAR_B:
        prioritat = "B"
    else:
        prioritat = "C"
    return Encaix(total, prioritat, elegible, nom_rol, detall, motius)
