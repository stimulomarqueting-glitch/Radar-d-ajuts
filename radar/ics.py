"""Exportació de les senyals d'alerta a un calendari iCalendar (.ics) amb avisos."""

from __future__ import annotations

import datetime as dt

from .calendari import Senyal

ICONES = {"preparar": "🟡", "vigilar": "👀", "obertura": "🟢", "tancament": "🔴", "tall": "🟠"}


def _escapa(text: str) -> str:
    return (
        text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")
    )


def _plega(linia: str) -> str:
    """Plega línies a 75 octets (RFC 5545 §3.1)."""
    bytes_ = linia.encode("utf-8")
    if len(bytes_) <= 75:
        return linia
    trossos, actual, mida = [], "", 0
    for ch in linia:
        b = len(ch.encode("utf-8"))
        limit = 75 if not trossos else 74
        if mida + b > limit:
            trossos.append(actual)
            actual, mida = ch, b
        else:
            actual += ch
            mida += b
    trossos.append(actual)
    return "\r\n ".join(trossos)


def genera(senyals: list[Senyal], generat: dt.datetime, nom_calendari: str = "Radar d'ajuts Stimulo") -> str:
    marca = generat.strftime("%Y%m%dT%H%M%SZ")
    linies = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Stimulo//Radar d'ajuts//CA",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escapa(nom_calendari)}",
        "X-WR-TIMEZONE:Europe/Madrid",
    ]
    for s in senyals:
        c = s.convocatoria
        estat = "ESTIMADA" if s.estimada else "CONFIRMADA"
        resum = f"{ICONES.get(s.tipus, '•')} {c.entitat} · {c.nom} — {s.tipus}" + (" (estimada)" if s.estimada else "")
        descripcio = "\n".join(
            filter(
                None,
                [
                    s.text,
                    f"Data {estat.lower()}." + (" Verificar a la font oficial." if s.estimada else ""),
                    f"Àmbit: {c.ambit_geografic}" if c.ambit_geografic else "",
                    f"Ajut: {c.ajuda_text}" if c.ajuda_text else "",
                    f"Fitxa: {c.url}" if c.url else "",
                ],
            )
        )
        linies += [
            "BEGIN:VEVENT",
            f"UID:{c.id}-{s.tipus}-{s.data:%Y%m%d}@radar-ajuts.stimulo",
            f"DTSTAMP:{marca}",
            f"DTSTART;VALUE=DATE:{s.data:%Y%m%d}",
            f"DTEND;VALUE=DATE:{s.data + dt.timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{_escapa(resum)}",
            f"DESCRIPTION:{_escapa(descripcio)}",
            f"CATEGORIES:{_escapa(c.nivell)},{_escapa(s.tipus)}",
            "TRANSP:TRANSPARENT",
        ]
        if c.url:
            linies.append(f"URL:{c.url}")
        linies += [
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{_escapa(resum)}",
            "TRIGGER;RELATED=START:PT9H",
            "END:VALARM",
            "END:VEVENT",
        ]
    linies.append("END:VCALENDAR")
    return "\r\n".join(_plega(linia) for linia in linies) + "\r\n"
