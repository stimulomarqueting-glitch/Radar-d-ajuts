"""Context de l'assistent per a un expedient: qui és Stimulo, l'ajut, els socis i la manera de treballar.

El text del sistema es construeix UNA vegada en crear l'expedient i es desa a la base de dades: es
manté idèntic durant tota la conversa (memòria cau de l'API i historial només d'afegir). Els canvis
posteriors (documents nous, fitxers, data) arriben com a missatges de sistema dins de la conversa.
"""

from __future__ import annotations

import datetime as dt

import yaml

from .. import calendari
from ..dades import ARREL, Cataleg, Convocatoria

ROL = """Ets l'assistent d'ajuts i subvencions de Stimulo, una agència de Barcelona de disseny i desenvolupament de producte amb tecnologies profundes. Treballes amb la persona que lidera les sol·licituds d'ajuts i l'ajudes a preparar, de cap a peus, la sol·licitud de l'ajut descrit més avall: decidir si val la pena, definir el projecte, triar socis i redactar tota la documentació.

Com treballes:
- Escrius en català, tret que les bases de la convocatòria demanin un altre idioma.
- Ets precís i pràctic: frases curtes, taules quan ajuden, sense farciment.
- No t'inventes requisits, xifres ni dates. Quan necessitis les bases oficials, fes servir la cerca web i cita'n la font. Si alguna dada de la fitxa és «no verificada» o d'una edició anterior, comprova-la abans de donar-la per bona.
- Quan falti informació, marca-la com a [PENDENT: …] i fes preguntes concretes.
- Tens present la manera de gestionar ajuts de Stimulo (pre-award i post-award) i els requisits habituals: règim de minimis, efecte incentivador, intensitats per mida d'empresa, tres ofertes, subcontractació, DNSH i propietat intel·lectual.
- Si l'ajut no encaixa, digues-ho clarament i proposa alternatives del radar."""


def _bloc(titol: str, cos: str) -> str:
    return f"<{titol}>\n{cos.strip()}\n</{titol}>"


def fitxa_convocatoria(c: Convocatoria, avui: dt.date) -> str:
    f = calendari.propera_finestra(c, avui)
    dades = {
        "nom": c.nom, "entitat": c.entitat, "nivell": c.nivell, "instrument": c.instrument, "fons": c.fons,
        "descripcio": c.descripcio, "ajut": c.ajuda_text, "intensitat_maxima_percent": c.intensitat_max,
        "import_maxim_eur": c.import_max_eur, "pressupost_minim_eur": c.pressupost_min_eur,
        "pressupost_total_eur": c.pressupost_total_eur, "durada_maxima_mesos": c.durada_max_mesos,
        "trl": list(c.trl) if c.trl else None, "modalitat": c.modalitat, "beneficiaris": c.beneficiaris,
        "ambit_geografic": c.ambit_geografic, "zones": c.zones, "rol_de_stimulo": c.rols_stimulo,
        "per_que_encaixa": c.encaix_stimulo, "punts_forts": c.punts_forts, "notes": c.notes,
        "finestra": {"estat": f.estat, "obertura": f.obertura.isoformat() if f.obertura else None,
                     "tancament": f.tancament.isoformat() if f.tancament else None,
                     "dates_estimades": f.estimada},
        "url": c.url, "fonts_de_verificacio": c.fonts_verificacio, "confianca_de_la_fitxa": c.confianca,
    }
    dades = {k: v for k, v in dades.items() if v not in (None, "", [], {})}
    return yaml.safe_dump(dades, allow_unicode=True, sort_keys=False, width=110)


def construeix(cat: Cataleg, c: Convocatoria, titol: str, idea: str, socis: list[dict], avui: dt.date,
               client: str = "") -> str:
    """`client`: bloc de context del client (screening.context_client) si la sol·licitud no és de Stimulo."""
    perfil = next(iter(cat.perfils.values()))
    stimulo = (f"{perfil.descripcio}\nUbicació: {cat.zones.nom(perfil.zona)}.\n"
               f"Àmbits prioritaris (pes 1–3): {', '.join(f'{k} ({v})' for k, v in perfil.focus.items())}.")
    try:
        gestio = (ARREL / "docs" / "gestio-ajuts.md").read_text(encoding="utf-8")
    except FileNotFoundError:
        gestio = ""
    socis_txt = "\n".join(
        f"- {s.get('nom')} · {s.get('tipus', '')} · {s.get('relacio', '')} · zona {s.get('zona') or '?'} · "
        f"temes: {', '.join(s.get('focus', []))}" + (f" · contacte: {s['contacte']}" if s.get("contacte") else "")
        + (f" · {s['nota']}" if s.get("nota") else "")
        for s in socis) or "Encara no se n'ha triat cap."
    parts = [
        ROL,
        _bloc("stimulo", stimulo),
        *([_bloc("client", client)] if client else []),
        _bloc("convocatoria", fitxa_convocatoria(c, avui)),
        _bloc("projecte", f"Títol de treball: {titol}\nIdea inicial: {idea or '(per definir amb tu)'}"),
        _bloc("socis_potencials", socis_txt + "\n(Contactes de Stimulo a Holded; dades privades.)"),
        _bloc("guia_gestio_ajuts", gestio),
        f"Data de creació de l'expedient: {avui:%d/%m/%Y}.",
    ]
    return "\n\n".join(parts)


ROL_LICITACIO = """Ets l'assistent de licitacions públiques de Stimulo, una agència de Barcelona de disseny i desenvolupament de producte amb tecnologies profundes. Ajudes la persona que porta les licitacions a decidir si es presenta (go / no-go) i a preparar l'oferta de la licitació descrita més avall: anàlisi dels plecs, memòria tècnica, oferta econòmica i documentació administrativa.

Com treballes:
- Escrius en català, tret que els plecs demanin el castellà.
- Coneixes la Llei 9/2017 de contractes del sector públic i la contractació a Catalunya (PSCP, sobre digital, RELI).
- No t'inventes requisits, xifres ni dates: si no tens els plecs, demana'ls o consulta l'enllaç de l'anunci amb la cerca web.
- Vigiles especialment la solvència que es demana, el pes del preu, la baixa anormal i la cessió de drets de propietat intel·lectual dels dissenys.
- Si la licitació no compensa, digues-ho clarament i explica per què."""


def construeix_licitacio(cat: Cataleg, lic: dict, avaluacio: dict, titol: str, idea: str, avui: dt.date) -> str:
    """Context fix d'un expedient d'oferta per a una licitació (vegeu `construeix`)."""
    perfil = next(iter(cat.perfils.values()))
    stimulo = f"{perfil.descripcio}\nUbicació: {cat.zones.nom(perfil.zona)}."
    dades = {k: v for k, v in lic.items() if v not in (None, "", [])}
    dades["avaluacio_del_radar"] = {k: avaluacio.get(k) for k in ("punts", "recomanacio", "motius", "alertes")}
    try:
        guia = (ARREL / "docs" / "licitacions.md").read_text(encoding="utf-8")
    except FileNotFoundError:
        guia = ""
    parts = [
        ROL_LICITACIO,
        _bloc("stimulo", stimulo),
        _bloc("licitacio", yaml.safe_dump(dades, allow_unicode=True, sort_keys=False, width=110)),
        _bloc("oferta", f"Títol de treball: {titol}\nEnfocament inicial: {idea or '(per definir amb tu)'}"),
        _bloc("guia_licitacions", guia),
        f"Data de creació de l'expedient: {avui:%d/%m/%Y}.",
    ]
    return "\n\n".join(parts)
