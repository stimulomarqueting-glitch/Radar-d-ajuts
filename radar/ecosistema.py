"""Ecosistema de defensa, ús dual i espai: actors, trobades i requisits per entrar al sector.

Dades a data/ecosistema.yaml. No són ajuts sinó portes d'entrada: el radar en fa recordatoris al
correu del matí, una pàgina a l'aplicació, sortida/ecosistema.md i la secció «Entrar al sector» dels
informes de screening.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .dades import DIR_DADES, FOCUS, Cataleg, ErrorValidacio

TIPUS_ACTOR = ("prime", "enginyeria", "consultoria", "cluster", "talent", "estudi")
TIPUS_TROBADA = ("fira", "trobada", "jornada", "workshop", "programa")
NOMS_TIPUS = {
    "prime": "Contractista principal", "enginyeria": "Enginyeria i fabricació", "consultoria": "Consultoria",
    "cluster": "Clúster", "talent": "Talent", "estudi": "Estudi de referència",
    "fira": "Fira", "trobada": "Trobada", "jornada": "Jornada", "workshop": "Workshop", "programa": "Programa",
}
DIES_RECORDATORI = (21, 7, 1, 0)
AMBITS_SECTOR = {"dual", "defensa", "espai"}


@dataclass
class Actor:
    id: str
    nom: str
    tipus: str
    ambits: list[str]
    zona: str
    descripcio: str
    per_als_clients: str = ""
    accio: str = ""
    url: str = ""
    fonts: list[str] = field(default_factory=list)
    confianca: str = "mitjana"


@dataclass
class Trobada:
    id: str
    nom: str
    tipus: str
    organitza: str
    ambits: list[str]
    zona: str
    descripcio: str
    lloc: str = ""
    inici: dt.date | None = None
    fi: dt.date | None = None
    recurrencia: str = ""
    convocatoria: str = ""
    per_als_clients: str = ""
    url: str = ""
    fonts: list[str] = field(default_factory=list)
    confianca: str = "mitjana"
    nota: str = ""

    def estat(self, avui: dt.date) -> str:
        """propera / en curs / passada / per confirmar."""
        if not self.inici:
            return "per confirmar"
        if self.inici > avui:
            return "propera"
        if (self.fi or self.inici) >= avui or self.recurrencia == "continua":
            return "en curs"
        return "passada"

    def quan(self) -> str:
        if not self.inici:
            return "Data per confirmar"
        if self.fi and self.fi != self.inici:
            return f"{self.inici:%d/%m/%Y} – {self.fi:%d/%m/%Y}"
        return f"Des del {self.inici:%d/%m/%Y}" if self.recurrencia == "continua" else f"{self.inici:%d/%m/%Y}"


@dataclass
class Requisit:
    id: str
    nom: str
    quan: str
    descripcio: str
    fonts: list[str] = field(default_factory=list)
    confianca: str = "mitjana"


@dataclass
class Ecosistema:
    actors: list[Actor]
    trobades: list[Trobada]
    requisits: list[Requisit]


def _data(valor, ctx: str) -> dt.date | None:
    if valor in (None, ""):
        return None
    if isinstance(valor, dt.date):
        return valor
    try:
        return dt.date.fromisoformat(str(valor))
    except ValueError as e:
        raise ErrorValidacio(f"{ctx}: data no vàlida '{valor}'") from e


def _ambits(valors: list, ctx: str) -> list[str]:
    for a in valors:
        if a not in FOCUS:
            raise ErrorValidacio(f"{ctx}: àmbit desconegut '{a}'")
    return list(valors)


def carrega(cat: Cataleg, path: Path = DIR_DADES / "ecosistema.yaml") -> Ecosistema:
    if not path.exists():
        return Ecosistema([], [], [])
    d = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    ids_convocatories = {c.id for c in cat.convocatories}
    actors, trobades, requisits = [], [], []
    for a in d.get("actors", []):
        ctx = f"ecosistema, actor {a.get('id')}"
        if a["tipus"] not in TIPUS_ACTOR:
            raise ErrorValidacio(f"{ctx}: tipus desconegut '{a['tipus']}'")
        if not cat.zones.existeix(a["zona"]):
            raise ErrorValidacio(f"{ctx}: zona desconeguda '{a['zona']}'")
        actors.append(Actor(a["id"], a["nom"], a["tipus"], _ambits(a.get("ambits", []), ctx), a["zona"],
                            " ".join(a.get("descripcio", "").split()), " ".join(a.get("per_als_clients", "").split()),
                            a.get("accio", ""), a.get("url", ""), list(a.get("fonts", [])), a.get("confianca", "mitjana")))
    for t in d.get("trobades", []):
        ctx = f"ecosistema, trobada {t.get('id')}"
        if t["tipus"] not in TIPUS_TROBADA:
            raise ErrorValidacio(f"{ctx}: tipus desconegut '{t['tipus']}'")
        if not cat.zones.existeix(t["zona"]):
            raise ErrorValidacio(f"{ctx}: zona desconeguda '{t['zona']}'")
        if t.get("convocatoria") and t["convocatoria"] not in ids_convocatories:
            raise ErrorValidacio(f"{ctx}: convocatòria desconeguda '{t['convocatoria']}'")
        inici, fi = _data(t.get("inici"), ctx), _data(t.get("fi"), ctx)
        if inici and fi and fi < inici:
            raise ErrorValidacio(f"{ctx}: la data de fi és anterior a la d'inici")
        trobades.append(Trobada(t["id"], t["nom"], t["tipus"], t.get("organitza", ""),
                                _ambits(t.get("ambits", []), ctx), t["zona"], " ".join(t.get("descripcio", "").split()),
                                t.get("lloc", ""), inici, fi, str(t.get("recurrencia", "")), t.get("convocatoria", ""),
                                " ".join(t.get("per_als_clients", "").split()), t.get("url", ""),
                                list(t.get("fonts", [])), t.get("confianca", "mitjana"), t.get("nota", "")))
    for r in d.get("requisits", []):
        requisits.append(Requisit(r["id"], r["nom"], r.get("quan", ""), " ".join(r.get("descripcio", "").split()),
                                  list(r.get("fonts", [])), r.get("confianca", "mitjana")))
    return Ecosistema(actors, trobades, requisits)


# --- Consultes ------------------------------------------------------------------------------------

def trobades_actives(eco: Ecosistema, avui: dt.date, dies: int = 365) -> list[Trobada]:
    """Trobades i programes en curs, propers (dins de `dies`) o sense data; les passades, fora."""
    limit = avui + dt.timedelta(days=dies)
    actives = [t for t in eco.trobades
               if t.estat(avui) in ("en curs", "per confirmar") or (t.estat(avui) == "propera" and t.inici <= limit)]
    ordre = {"en curs": 0, "propera": 1, "per confirmar": 2}
    return sorted(actives, key=lambda t: (ordre[t.estat(avui)], t.inici or dt.date.max, t.nom))


def recordatoris(eco: Ecosistema, avui: dt.date) -> list[str]:
    """Text per al correu del matí: trobades que comencen d'aquí a 21, 7 o 1 dies, o avui."""
    sortida = []
    for t in eco.trobades:
        if t.inici and (dies := (t.inici - avui).days) in DIES_RECORDATORI:
            quan = "avui" if dies == 0 else ("demà" if dies == 1 else f"d'aquí a {dies} dies")
            sortida.append(f"{t.nom} ({t.organitza}): comença {quan}, el {t.inici:%d/%m/%Y}"
                           + (f", a {t.lloc}" if t.lloc else "") + (f" — {t.url}" if t.url else ""))
    return sortida


def per_a(eco: Ecosistema, focus: set[str]) -> tuple[list[Actor], list[Trobada]]:
    """Actors i trobades que comparteixen algun tema amb un perfil (per al screening de clients)."""
    return ([a for a in eco.actors if set(a.ambits) & focus],
            [t for t in eco.trobades if set(t.ambits) & focus])


# --- Informe --------------------------------------------------------------------------------------

def markdown(eco: Ecosistema, avui: dt.date) -> str:
    t = ["# Ecosistema de defensa, ús dual i espai", "",
         f"_Actualitzat el {avui:%d/%m/%Y}. Portes d'entrada al sector per a Stimulo i els clients. "
         "Els ajuts són al radar (`sortida/radar.md`, tema «ús dual» o «defensa»)._", "",
         "## Trobades i programes", ""]
    for x in trobades_actives(eco, avui):
        t.append(f"- **{x.nom}** · {NOMS_TIPUS[x.tipus]} · {x.quan()}" + (f" · {x.lloc}" if x.lloc else ""))
        t.append(f"  {x.descripcio}" + (f" Per als clients: {x.per_als_clients}" if x.per_als_clients else ""))
        if x.nota:
            t.append(f"  ⚠ {x.nota}")
        if x.url:
            t.append(f"  {x.url}")
    t += ["", "## Actors", ""]
    for a in sorted(eco.actors, key=lambda a: (TIPUS_ACTOR.index(a.tipus), a.nom)):
        t.append(f"- **{a.nom}** · {NOMS_TIPUS[a.tipus]}" + (" · ⚠ per verificar" if a.confianca == "baixa" else ""))
        t.append(f"  {a.descripcio}")
        if a.accio:
            t.append(f"  Acció: {a.accio}")
        if a.url:
            t.append(f"  {a.url}")
    t += ["", "## Requisits per entrar al sector", ""]
    for r in eco.requisits:
        t.append(f"- **{r.nom}** — {r.quan} {r.descripcio}" + (" (per verificar)" if r.confianca == "baixa" else ""))
    return "\n".join(t) + "\n"
