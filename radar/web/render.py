"""Markdown → HTML segur per mostrar les respostes de l'assistent i els documents.

El text pot contenir contingut copiat de webs (cerca de l'assistent), així que no se'n permet cap HTML:
s'escapen `&` i `<` abans de convertir-lo i només es deixen enllaços http(s), mailto, relatius i àncores.
"""

from __future__ import annotations

import re

import markdown as _markdown
from markupsafe import Markup

EXTENSIONS = ["tables", "fenced_code", "sane_lists"]
RE_HREF = re.compile(r'(href|src)="([^"]*)"')
ESQUEMES_PERMESOS = ("http://", "https://", "mailto:", "/", "#")


def _enllac_segur(m: re.Match) -> str:
    atribut, valor = m.group(1), m.group(2)
    if valor.lower().startswith(ESQUEMES_PERMESOS) and not valor.startswith("//"):
        return m.group(0)
    return f'{atribut}="#"'


def markdown_html(text: str) -> Markup:
    escapat = (text or "").replace("&", "&amp;").replace("<", "&lt;")
    sortida = _markdown.markdown(escapat, extensions=EXTENSIONS, output_format="html")
    sortida = RE_HREF.sub(_enllac_segur, sortida)
    sortida = sortida.replace("<a href=\"http", "<a rel=\"noopener noreferrer\" target=\"_blank\" href=\"http")
    return Markup(sortida)
