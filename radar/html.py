"""Tauler HTML autònom del radar (sortida/radar.html), amb filtres per perfil, zona i estat.

`genera(..., autonom=False)` escriu només el contingut de la pàgina (sense <!doctype>/<head>), que és
el format que espera la publicació com a Artifact.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .dades import Cataleg
from .informe import dades_json

DIR_WEB = Path(__file__).resolve().parent / "web"
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">\n'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500'
         '&family=IBM+Plex+Sans:wght@400;500;600&family=Schibsted+Grotesk:wght@600;800&display=swap">')


def cos_tauler() -> str:
    """Marcatge del tauler, compartit amb l'aplicació web (web/templates/_tauler_cos.html)."""
    return (DIR_WEB / "templates" / "_tauler_cos.html").read_text(encoding="utf-8")


def pagina(dades: dict) -> str:
    """Pàgina autònoma (sense servidor): CSS i JS en línia, dades incrustades."""
    css = (DIR_WEB / "static" / "tauler.css").read_text(encoding="utf-8")
    js = (DIR_WEB / "static" / "tauler.js").read_text(encoding="utf-8")
    dades_js = json.dumps(dades, ensure_ascii=False).replace("</", "<\\/")
    return (f"<title>Radar d'ajuts Stimulo</title>\n{FONTS}\n<style>\n{css}</style>\n<div class=\"pagina\">\n{cos_tauler()}</div>\n"
            f"<script>window.RADAR_DADES = {dades_js};</script>\n<script>\n{js}</script>\n")


def genera(cat: Cataleg, avui: dt.date, dir_sortida: Path, autonom: bool = True, nom: str = "radar.html") -> Path:
    cos = pagina(dades_json(cat, avui))
    if autonom:
        cos = ('<!doctype html>\n<html lang="ca">\n<head>\n<meta charset="utf-8">\n'
               '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
               + cos.replace("</style>\n", "</style>\n</head>\n<body>\n", 1) + "</body>\n</html>\n")
    desti = dir_sortida / nom
    desti.write_text(cos, encoding="utf-8")
    return desti
