"""Programes en seguiment actiu (p. ex. els Cupons ACCIÓ): estat de cada modalitat i recordatoris.

Una convocatòria està en seguiment si té `seguiment: true` a data/convocatories.yaml; si a més té
`programa`, s'agrupa amb les altres modalitats del mateix programa (data/programes.yaml).
El correu del matí n'inclou els recordatoris de termini i el pla i l'aplicació en mostren un bloc propi.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

from . import calendari
from .dades import Cataleg, Convocatoria, Programa

DIES_TANCAMENT = (30, 21, 14, 7, 3, 1, 0)
DIES_OBERTURA = (30, 7, 1, 0)
URGENT_DIES = 21
ORDRE_ESTAT = {"oberta": 0, "permanent": 1, "propera": 2, "tancada": 3, "sense_dades": 4}


@dataclass
class Estat:
    f: calendari.Finestra
    etiqueta: str  # Oberta / Propera / Tancada / Tot l'any / Sense dades
    text: str  # «Tanca el 16/11/2026 (d'aquí a 37 dies)»
    dies: int | None  # fins al tancament (oberta) o fins a l'obertura (propera)
    urgent: bool


def nom_curt(c: Convocatoria) -> str:
    """«Cupons ACCIÓ per a programes europeus d'R+D+I 2026» → «programes europeus d'R+D+I»."""
    nom = re.sub(r"\s+20\d\d$", "", c.nom)
    if c.programa:
        nom = re.sub(r"^Cupons ACCIÓ\s+", "", nom)
        nom = re.sub(r"^(per a (la )?|de |d')", "", nom)
    return nom


def _quan(dies: int) -> str:
    return "avui" if dies == 0 else "demà" if dies == 1 else f"d'aquí a {dies} dies"


def estat(c: Convocatoria, avui: dt.date) -> Estat:
    f = calendari.propera_finestra(c, avui)
    m = "≈ " if f.estimada else ""
    if f.estat == "oberta":
        if f.tancament:
            dies = (f.tancament - avui).days
            return Estat(f, "Oberta", f"Tanca el {m}{f.tancament:%d/%m/%Y} ({_quan(dies)})", dies, dies <= URGENT_DIES)
        return Estat(f, "Oberta", "Oberta (termini per confirmar)", None, False)
    if f.estat == "propera":
        if f.obertura:
            dies = (f.obertura - avui).days
            return Estat(f, "Propera", f"Obre el {m}{f.obertura:%d/%m/%Y} ({_quan(dies)})", dies, False)
        return Estat(f, "Propera", "Anunciada: dates per confirmar", None, False)
    if f.estat == "permanent":
        return Estat(f, "Tot l'any", "Oberta tot l'any", None, False)
    if f.estat == "tancada":
        return Estat(f, "Tancada", f"Tancada{f' el {f.tancament:%d/%m/%Y}' if f.tancament else ''}", None, False)
    return Estat(f, "Sense dades", "Dates pendents de publicar", None, False)


def en_seguiment(cat: Cataleg) -> list[Convocatoria]:
    return [c for c in cat.convocatories if c.seguiment]


def per_programa(cat: Cataleg, avui: dt.date) -> list[tuple[Programa | None, list[tuple[Convocatoria, Estat]]]]:
    """Convocatòries en seguiment agrupades per programa (les que no en tenen, cadascuna sola).
    Dins de cada programa: obertes (per tancament), properes i tancades."""
    grups: dict[str, list[tuple[Convocatoria, Estat]]] = {}
    for c in en_seguiment(cat):
        grups.setdefault(c.programa or f"_{c.id}", []).append((c, estat(c, avui)))

    def clau(x: tuple[Convocatoria, Estat]):
        c, e = x
        return (ORDRE_ESTAT.get(e.f.estat, 9), e.dies if e.dies is not None else 10 ** 6, c.nom)

    sortida = [(cat.programes.get(k), sorted(v, key=clau)) for k, v in grups.items()]
    sortida.sort(key=lambda g: min(clau(x)[:2] for x in g[1]))
    return sortida


def recordatoris(cat: Cataleg, avui: dt.date) -> list[str]:
    """Recordatoris per al correu del matí: tancament a 30, 21, 14, 7, 3, 1 i 0 dies i obertura a 30, 7, 1
    i 0 dies. Les modalitats d'un mateix programa que coincideixen en data surten en una sola línia."""
    grups: dict[tuple, list[Convocatoria]] = {}
    for c in en_seguiment(cat):
        e = estat(c, avui)
        if e.dies is None:
            continue
        if e.f.estat == "oberta" and e.dies in DIES_TANCAMENT:
            grups.setdefault((c.programa or c.id, "tanca", e.f.tancament, e.f.estimada), []).append(c)
        elif e.f.estat == "propera" and e.dies in DIES_OBERTURA:
            grups.setdefault((c.programa or c.id, "obre", e.f.obertura, e.f.estimada), []).append(c)
    sortida = []
    for (clau, tipus, data, estimada), cs in sorted(grups.items(), key=lambda x: x[0][2]):
        programa = cat.programes.get(clau)
        dies = (data - avui).days
        m = "≈ " if estimada else ""
        if programa:
            qui = f"{programa.nom} ({', '.join(nom_curt(c) for c in cs)})"
        else:
            qui = f"{cs[0].nom} ({cs[0].entitat})"
        per_clients = any(c.compartir_clients for c in cs)
        if tipus == "tanca":
            ordre = " o quan s'exhaureixi el pressupost" if any(c.instrument == "cupo" for c in cs) else ""
            text = (f"Seguiment · {qui}: {'tanca' if len(cs) == 1 else 'tanquen'} {_quan(dies)} "
                    f"({m}{data:%d/%m/%Y}){ordre}." + (" Avisa els clients que hi encaixin." if per_clients else ""))
        else:
            text = (f"Seguiment · {qui}: {'obre' if len(cs) == 1 else 'obren'} {_quan(dies)} ({m}{data:%d/%m/%Y}). "
                    "Si és per ordre d'entrada, tingues les sol·licituds a punt.")
        url = programa.url if programa and programa.url else cs[0].url
        sortida.append(text + (f" — {url}" if url else ""))
    return sortida


def candidats_holded(socis: list, zona: str = "ES-CT", maxim: int = 40) -> list:
    """Clients i contactes de Holded a qui oferir un programa de pimes de Catalunya (empreses i startups)."""
    tries = [s for s in socis if s.relacio in ("client", "lead") and s.tipus in ("empresa", "startup")
             and (s.zona or "").startswith(zona)]
    tries.sort(key=lambda s: (s.relacio != "client", s.nom.lower()))
    return tries[:maxim]
