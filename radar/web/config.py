"""Configuració de l'aplicació a partir de variables d'entorn (fitxer .env al VPS)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from ..dades import ARREL


def _bool(nom: str, defecte: bool) -> bool:
    valor = os.environ.get(nom)
    if valor is None or valor == "":
        return defecte
    return valor.strip().lower() in ("1", "true", "si", "sí", "yes", "on")


@dataclass
class Config:
    usuari: str = field(default_factory=lambda: os.environ.get("RADAR_USUARI", "xavi"))
    contrasenya_hash: str = field(default_factory=lambda: os.environ.get("RADAR_CONTRASENYA_HASH", ""))
    totp_secret: str = field(default_factory=lambda: os.environ.get("RADAR_TOTP_SECRET", ""))
    secret: str = field(default_factory=lambda: os.environ.get("RADAR_SECRET", ""))
    cookie_segura: bool = field(default_factory=lambda: _bool("RADAR_COOKIE_SEGURA", True))
    hores_sessio: int = field(default_factory=lambda: int(os.environ.get("RADAR_HORES_SESSIO") or 12))
    dir_dades_app: Path = field(default_factory=lambda: Path(os.environ.get("RADAR_DIR_APP") or ARREL / "privat" / "app"))
    model: str = field(default_factory=lambda: os.environ.get("RADAR_MODEL") or "claude-opus-5-5")
    esforc: str = field(default_factory=lambda: os.environ.get("RADAR_ESFORC") or "high")
    fallbacks: bool = field(default_factory=lambda: _bool("RADAR_FALLBACKS", True))
    cerca_web: bool = field(default_factory=lambda: _bool("RADAR_CERCA_WEB", True))
    mida_max_fitxer_mb: int = field(default_factory=lambda: int(os.environ.get("RADAR_MIDA_MAX_MB") or 25))

    @property
    def db(self) -> Path:
        return self.dir_dades_app / "radar.sqlite3"

    @property
    def dir_fitxers(self) -> Path:
        return self.dir_dades_app / "fitxers"

    def problemes(self) -> list[str]:
        """Configuració insegura o incompleta (es mostra a la pàgina de configuració)."""
        p = []
        if not self.contrasenya_hash:
            p.append("Falta RADAR_CONTRASENYA_HASH: genera-la amb `python -m radar contrasenya`.")
        if len(self.secret) < 32:
            p.append("RADAR_SECRET ha de tenir com a mínim 32 caràcters aleatoris.")
        if not os.environ.get("ANTHROPIC_API_KEY"):
            p.append("Falta ANTHROPIC_API_KEY: l'assistent de propostes no funcionarà.")
        return p
