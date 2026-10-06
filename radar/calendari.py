"""Properes finestres de cada convocatòria i senyals d'alerta.

Quan una convocatòria anual ja ha tancat, el radar n'estima la propera edició a partir de
l'última obertura coneguda (mateixa data +1 any) o del mes habitual d'obertura, i genera
pre-alertes perquè el projecte i el consorci estiguin preparats abans que surtin les bases.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from .dades import Convocatoria

# Dies d'antelació de cada senyal (es poden sobreescriure a perfils.yaml > config.alertes)
ALERTES_PER_DEFECTE = {
    "preparar": 60,  # abans de l'obertura (real o estimada): idea, pressupost, socis
    "vigilar": 14,  # abans de l'obertura estimada: vigilar DOGC/BOE/portal
    "tancament": 21,  # abans del tancament: memòria final, signatures, annexos
    "tall": 45,  # abans d'un tall (EIC, Eurostars...): preparar la proposta
}


@dataclass
class Finestra:
    obertura: dt.date | None
    tancament: dt.date | None
    estimada: bool
    estat: str  # oberta / propera / tancada / permanent / sense_dades
    descripcio: str


@dataclass
class Senyal:
    data: dt.date
    tipus: str  # preparar / vigilar / obertura / tancament / tall
    convocatoria: Convocatoria
    estimada: bool
    text: str


def _mes_any(d: dt.date, anys: int) -> dt.date:
    try:
        return d.replace(year=d.year + anys)
    except ValueError:  # 29 de febrer
        return d.replace(year=d.year + anys, day=28)


def propera_finestra(c: Convocatoria, avui: dt.date) -> Finestra:
    cal = c.calendari

    if cal.recurrencia == "continua" or cal.estat == "permanent":
        if cal.tancament and cal.tancament < avui:
            return Finestra(None, cal.tancament, False, "tancada", "Línia tancada")
        return Finestra(None, cal.tancament, False, "permanent", "Oberta tot l'any / per ordre d'arribada")

    sense_dates = not (cal.obertura or cal.tancament or cal.talls)
    if sense_dates and cal.estat == "oberta":
        return Finestra(None, None, False, "oberta", "Oberta (termini a confirmar)")
    if sense_dates and cal.estat == "prevista":
        return Finestra(None, None, True, "propera", "Anunciada: dates pendents")

    if cal.recurrencia == "multiples_talls":
        futurs = [t for t in cal.talls if t >= avui]
        if futurs:
            if cal.obertura and cal.obertura > avui:
                return Finestra(cal.obertura, futurs[0], False, "propera", f"Obre {cal.obertura:%d/%m/%Y}")
            if cal.estat in ("tancada", "prevista") and not cal.obertura:
                # Talls futurs coneguts d'una convocatòria que encara no ha obert
                return Finestra(None, futurs[0], False, "propera", f"Proper tall: {futurs[0]:%d/%m/%Y}")
            return Finestra(cal.obertura, futurs[0], False, "oberta", f"Proper tall: {futurs[0]:%d/%m/%Y}")
        if cal.mes_tancament_habitual:
            estimat = _proxima_data_mes(cal.mes_tancament_habitual, avui)
            return Finestra(None, estimat, True, "propera", "Talls periòdics (dates de l'any vinent pendents)")
        return Finestra(None, None, True, "sense_dades", "Talls periòdics: dates pendents de publicar")

    # Finestra coneguda i encara vigent o futura
    if cal.tancament and cal.tancament >= avui:
        if cal.obertura and cal.obertura > avui:
            return Finestra(cal.obertura, cal.tancament, False, "propera", "Obertura anunciada")
        return Finestra(cal.obertura, cal.tancament, False, "oberta", "Convocatòria oberta")
    if cal.obertura and cal.obertura > avui:
        return Finestra(cal.obertura, None, False, "propera", "Obertura anunciada")

    if cal.recurrencia == "puntual":
        return Finestra(cal.obertura, cal.tancament, False, "tancada", "Convocatòria puntual tancada")

    # Estimació de la propera edició anual
    if cal.recurrencia == "anual":
        obertura = tancament = None
        if cal.obertura or cal.tancament:
            anys = 1
            while True:
                obertura = _mes_any(cal.obertura, anys) if cal.obertura else None
                tancament = _mes_any(cal.tancament, anys) if cal.tancament else None
                referencia = tancament or obertura
                if referencia >= avui:
                    break
                anys += 1
        elif cal.mes_obertura_habitual:
            obertura = _proxima_data_mes(cal.mes_obertura_habitual, avui)
            if cal.mes_tancament_habitual:
                tancament = _proxima_data_mes(cal.mes_tancament_habitual, obertura)
        if tancament and not obertura and cal.mes_obertura_habitual:
            # Només coneixem el tancament: situem l'obertura al mes habitual anterior
            obertura = dt.date(tancament.year, cal.mes_obertura_habitual, 1)
            if obertura > tancament:
                obertura = obertura.replace(year=tancament.year - 1)
        if obertura or tancament:
            if obertura and tancament and obertura <= avui <= tancament:
                # L'estimació cau en una finestra que ja hauria d'estar oberta: cal verificar-ho
                return Finestra(obertura, tancament, True, "oberta", "Possiblement oberta (verificar)")
            return Finestra(obertura, tancament, True, "propera", "Propera edició estimada")

    return Finestra(cal.obertura, cal.tancament, True, "sense_dades", "Sense dates: revisar la font")


def _proxima_data_mes(mes: int, despres_de: dt.date) -> dt.date:
    candidat = dt.date(despres_de.year, mes, 1)
    if candidat < despres_de:
        candidat = dt.date(despres_de.year + 1, mes, 1)
    return candidat


def senyals(c: Convocatoria, avui: dt.date, antelacio: dict | None = None) -> list[Senyal]:
    """Senyals d'alerta futures (data >= avui) per a una convocatòria."""
    ant = {**ALERTES_PER_DEFECTE, **(antelacio or {})}
    f = propera_finestra(c, avui)
    sortida: list[Senyal] = []
    obertura_txt = "obertura estimada" if f.estimada else "obertura confirmada"
    tancament_txt = "tancament estimat" if f.estimada else "tancament confirmat"

    def afegeix(data, tipus, text, estimada=None):
        if data and data >= avui:
            sortida.append(Senyal(data, tipus, c, f.estimada if estimada is None else estimada, text))

    if c.calendari.revisar:
        afegeix(c.calendari.revisar, "vigilar",
                c.calendari.revisar_motiu or "Revisar l'estat de la convocatòria a la font oficial", estimada=False)

    if f.estat in ("permanent", "tancada"):
        return sortida

    if c.calendari.recurrencia == "multiples_talls":
        for t in [t for t in c.calendari.talls if t >= avui][:3]:
            afegeix(t - dt.timedelta(days=ant["tall"]), "tall", f"Preparar proposta per al tall del {t:%d/%m/%Y}")
            afegeix(t, "tancament", f"Tall {c.nom}")
        if not c.calendari.talls and f.tancament:
            afegeix(f.tancament - dt.timedelta(days=ant["tall"]), "tall", "Comprovar calendari de talls de l'any vinent")
        return sortida

    if f.obertura:
        afegeix(f.obertura - dt.timedelta(days=ant["preparar"]), "preparar",
                f"Preparar projecte i socis: {obertura_txt} el {f.obertura:%d/%m/%Y}")
        if f.estimada:
            afegeix(f.obertura - dt.timedelta(days=ant["vigilar"]), "vigilar",
                    "Vigilar la publicació de les bases (DOGC/BOE/portal)")
        afegeix(f.obertura, "obertura", f"{obertura_txt.capitalize()}: {c.nom}")
    if f.tancament:
        afegeix(f.tancament - dt.timedelta(days=ant["tancament"]), "tancament",
                f"Darrera revisió: {tancament_txt} el {f.tancament:%d/%m/%Y}")
        afegeix(f.tancament, "tancament", f"{tancament_txt.capitalize()}: {c.nom}")
    return sortida


def agenda(convocatories: list[Convocatoria], avui: dt.date, dies: int = 365,
           antelacio: dict | None = None) -> list[Senyal]:
    limit = avui + dt.timedelta(days=dies)
    totes = [s for c in convocatories for s in senyals(c, avui, antelacio) if s.data <= limit]
    return sorted(totes, key=lambda s: (s.data, s.convocatoria.nom))
