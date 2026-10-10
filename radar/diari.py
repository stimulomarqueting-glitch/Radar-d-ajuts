"""Revisió de cada matí: vigilància de fonts, informe, avís per correu i recordatoris (expedients i dates de revisió).

    python -m radar diari                 # una revisió ara (envia el correu si hi ha novetats)
    python -m radar programador           # servei: una revisió cada dia a RADAR_HORA (07:30, Europe/Madrid)
"""

from __future__ import annotations

import datetime as dt
import json
import os
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

from . import avisos, calendari, dades, holded, informe, licitacions, socis, vigilancia

ARREL = dades.ARREL
DIES_RECORDATORI = (21, 14, 7, 3, 1, 0)


@dataclass
class ResultatAvis:
    assumpte: str = ""
    linies: int = 0
    novetats: int = 0
    recordatoris: int = 0
    licitacions: int = 0
    enviat: bool = False
    copia: Path | None = None
    missatge: str = ""
    errors: dict = field(default_factory=dict)


def contactes_holded(fitxer: str | None = None) -> tuple[list, str]:
    """Contactes de Holded: fitxer indicat, API (HOLDED_API_KEY) o exportació privada."""
    try:
        if fitxer:
            return holded.des_de_fitxer(Path(fitxer)), ""
        if os.environ.get("HOLDED_API_KEY"):
            return holded.des_de_api(), ""
        local = ARREL / "privat" / "holded_contactes.json"
        if local.exists():
            return holded.des_de_fitxer(local), ""
        return [], "Sense socis suggerits: no hi ha accés als contactes de Holded (configura HOLDED_API_KEY)."
    except Exception as e:  # sense contactes l'avís continua sent útil
        return [], f"Sense socis suggerits: error llegint Holded ({type(e).__name__})."


def recordatoris_expedients(cat: dades.Cataleg, avui: dt.date, path_db: Path | None) -> list[str]:
    """Recordatoris de terminis dels expedients en preparació (21, 14, 7, 3, 1 i 0 dies)."""
    if not path_db or not Path(path_db).exists():
        return []
    from .web.db import BaseDades

    sortida = []
    for e in BaseDades(Path(path_db)).expedients():
        if e["estat"] != "en preparació":
            continue
        try:
            c = cat.per_id(e["convocatoria_id"])
        except KeyError:
            continue
        f = calendari.propera_finestra(c, avui)
        if f.estat == "oberta" and f.tancament:
            dies = (f.tancament - avui).days
            if dies in DIES_RECORDATORI:
                quan = "avui" if dies == 0 else f"d'aquí a {dies} dies"
                sortida.append(f"«{e['titol']}» ({c.nom}): la convocatòria tanca {quan}, el {f.tancament:%d/%m/%Y}"
                               + (" (data estimada)." if f.estimada else "."))
        elif f.estat == "propera" and f.obertura:
            dies = (f.obertura - avui).days
            if dies in (14, 7, 1, 0):
                sortida.append(f"«{e['titol']}» ({c.nom}): la convocatòria obre "
                               f"{'avui' if dies == 0 else f'd’aquí a {dies} dies'}, el {f.obertura:%d/%m/%Y}.")
    return sortida


def senyals_manuals(cat: dades.Cataleg, avui: dt.date) -> list[str]:
    """Dates de revisió posades a mà al catàleg (`calendari.revisar`) que toquen avui."""
    return [f"{c.nom} ({c.entitat}): {c.calendari.revisar_motiu or 'revisar l’estat a la font oficial'}"
            + (f" — {c.url}" if c.url else "")
            for c in cat.convocatories if c.calendari.revisar == avui]


def recordatoris_licitacions(avui: dt.date, path_db: Path | None) -> list[str]:
    """Terminis de les licitacions en anàlisi o amb decisió «go» (7, 3, 1 i 0 dies abans)."""
    if not path_db or not Path(path_db).exists():
        return []
    from .web.db import BaseDades

    sortida = []
    for r in BaseDades(Path(path_db)).licitacions():
        if r["estat"] not in licitacions.ESTATS_ACTIUS or not r["dades"].get("termini"):
            continue
        termini = dt.date.fromisoformat(r["dades"]["termini"])
        dies = (termini - avui).days
        if dies in licitacions.DIES_RECORDATORI:
            quan = "avui" if dies == 0 else f"d'aquí a {dies} dies"
            sortida.append(f"Licitació «{r['dades']['titol'][:90]}» ({r['estat']}): el termini d'ofertes acaba {quan}, "
                           f"el {termini:%d/%m/%Y}.")
    return sortida


def prepara_avis(avui: dt.date, envia: bool = False, tot: bool = False, maxim: int | None = None,
                 novetats: list[dict] | None = None, fitxer_contactes: str | None = None,
                 path_db: Path | None = None, actualitza_estat: bool = True,
                 noves_licitacions: list | None = None) -> ResultatAvis:
    cat = dades.carrega()
    cfg = {**avisos.CONFIG_PER_DEFECTE, **cat.config.get("avisos", {})}
    fitxer_estat = ARREL / "data" / "estat" / "notificades.json"
    estat = avisos.llegeix_estat(fitxer_estat)
    from . import screening

    try:
        clients_servei = [cl for cl in screening.carrega_clients(cat).values() if cl.avisos]
    except Exception:  # un fitxer de client mal format no ha d'aturar l'avís
        clients_servei = []
    candidates = avisos.candidates(cat, avui, cfg, clients_servei)
    noves = candidates if tot else avisos.noves(candidates, estat)
    maxim = maxim or cfg["maxim_linies"]
    principals, resum = avisos.reparteix(noves, maxim)
    novetats = novetats or []
    from . import ecosistema, seguiment

    recordatoris = (seguiment.recordatoris(cat, avui) + senyals_manuals(cat, avui)
                    + ecosistema.recordatoris(ecosistema.carrega(cat), avui)
                    + recordatoris_expedients(cat, avui, path_db) + recordatoris_licitacions(avui, path_db))
    lics = [(l, a) for l, a in (noves_licitacions or []) if a.semafor in ("verd", "groc")][:8]
    r = ResultatAvis(linies=len(noves), novetats=len(novetats), recordatoris=len(recordatoris))
    r.licitacions = len(lics)
    if not principals and not novetats and not recordatoris and not lics:
        r.missatge = "Cap novetat: no s'envia cap correu."
        return r
    contactes, motiu = contactes_holded(fitxer_contactes)
    llista_socis = socis.construeix(contactes) if contactes else []
    avisos.afegeix_socis(principals, llista_socis, cat, cfg["maxim_socis"], cfg.get("maxim_socis_clients"))
    r.assumpte, text, cos_html = avisos.compon(principals, avui, cfg, resum, novetats,
                                               motiu if principals else "", recordatoris, lics)
    r.copia = avisos.desa_copia(ARREL / "privat" / "avisos", avui, r.assumpte, text, cos_html)
    if not envia:
        r.missatge = "Vista prèvia: no s'ha enviat."
        return r
    if not avisos.smtp_configurat():
        r.missatge = "No s'ha enviat: falten SMTP_HOST, SMTP_USER, SMTP_PASSWORD o RADAR_DESTINATARI."
        return r
    avisos.envia(r.assumpte, text, cos_html, cfg["remitent_nom"])
    r.enviat = True
    if actualitza_estat:
        avisos.desa_estat(fitxer_estat, estat, principals + resum, avui)
    r.missatge = "Enviat."
    return r


def executa_diari(avui: dt.date | None = None, envia: bool = True, path_db: Path | None = None) -> ResultatAvis:
    """Vigilància + informe + avís. Cada pas falla de manera aïllada."""
    avui = avui or dt.date.today()
    errors: dict[str, str] = {}
    novetats: list[dict] = []
    try:
        cat = dades.carrega()
        paraules = sorted({k for p in cat.perfils.values() for k in p.paraules_clau})
        noves, errors_vigilancia = vigilancia.executa(cat.config.get("vigilancia", {}), paraules,
                                                      ARREL / "data" / "estat" / "vistos.json",
                                                      [f for f in cat.fonts if f.vigilant == "pagina"])
        errors.update({f"vigilancia.{k}": v for k, v in errors_vigilancia.items()})
        sortida = ARREL / "sortida"
        sortida.mkdir(exist_ok=True)
        (sortida / "novetats.md").write_text(vigilancia.informe_novetats(noves, errors_vigilancia, avui), encoding="utf-8")
        (sortida / "novetats.json").write_text(vigilancia.a_json(noves), encoding="utf-8")
        novetats = json.loads(vigilancia.a_json(noves))
    except Exception as e:
        errors["vigilancia"] = f"{type(e).__name__}: {e}"
    noves_lics = []
    try:
        cat = dades.carrega()
        db = None
        if path_db:
            from .web.db import BaseDades

            db = BaseDades(Path(path_db))
        res = licitacions.executa(cat, avui, ARREL / "sortida", ARREL / "data" / "estat" / "licitacions-vistes.json", db)
        noves_lics = res["noves"]
        errors.update({f"licitacions.{k}": v for k, v in res["errors"].items()})
    except Exception as e:
        errors["licitacions"] = f"{type(e).__name__}: {e}"
    try:
        cat = dades.carrega()
        informe.genera_tot(cat, avui, ARREL / "sortida")
        from . import html

        html.genera(cat, avui, ARREL / "sortida")
    except Exception as e:
        errors["informe"] = f"{type(e).__name__}: {e}"
    try:
        r = prepara_avis(avui, envia=envia, novetats=novetats, path_db=path_db, noves_licitacions=noves_lics)
    except Exception as e:
        r = ResultatAvis(missatge=f"Error preparant l'avís: {type(e).__name__}: {e}")
        errors["avis"] = traceback.format_exc(limit=3)
    r.errors = errors
    return r


def _proxima_execucio(ara: dt.datetime, hora: str) -> dt.datetime:
    h, m = (int(x) for x in hora.split(":"))
    objectiu = ara.replace(hour=h, minute=m, second=0, microsecond=0)
    return objectiu if objectiu > ara else objectiu + dt.timedelta(days=1)


def programador(hora: str | None = None, zona: str | None = None, path_db: Path | None = None) -> None:
    """Bucle del servei: espera fins a l'hora indicada i executa la revisió, cada dia."""
    hora = hora or os.environ.get("RADAR_HORA", "07:30")
    tz = ZoneInfo(zona or os.environ.get("RADAR_ZONA_HORARIA", "Europe/Madrid"))
    print(f"Programador actiu: revisió diària a les {hora} ({tz.key}).", flush=True)
    while True:
        ara = dt.datetime.now(tz)
        seguent = _proxima_execucio(ara, hora)
        time.sleep(max(1, (seguent - ara).total_seconds()))
        r = executa_diari(dt.datetime.now(tz).date(), envia=True, path_db=path_db)
        print(f"[{dt.datetime.now(tz):%Y-%m-%d %H:%M}] {r.assumpte or 'sense correu'} · {r.missatge} · "
              f"errors: {', '.join(r.errors) or 'cap'}", flush=True)
        if path_db and Path(path_db).exists():
            from .web.db import BaseDades

            BaseDades(Path(path_db)).registra("revisio_diaria", json.dumps(
                {"assumpte": r.assumpte, "missatge": r.missatge, "linies": r.linies, "novetats": r.novetats,
                 "recordatoris": r.recordatoris, "licitacions": r.licitacions,
                 "errors": {k: str(v)[:300] for k, v in r.errors.items()}},
                ensure_ascii=False))
