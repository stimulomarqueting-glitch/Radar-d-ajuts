"""Accés d'un sol usuari: contrasenya (PBKDF2-SHA256), segon factor TOTP opcional i sessió signada.

    python -m radar contrasenya        # genera RADAR_CONTRASENYA_HASH (i opcionalment un secret TOTP)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct
import threading
import time

ITERACIONS = 600_000
NOM_COOKIE = "radar_sessio"


# --- Contrasenya ---------------------------------------------------------------------------------

def hash_contrasenya(contrasenya: str, iteracions: int = ITERACIONS) -> str:
    sal = secrets.token_bytes(16)
    clau = hashlib.pbkdf2_hmac("sha256", contrasenya.encode("utf-8"), sal, iteracions)
    return f"pbkdf2_sha256${iteracions}${base64.b64encode(sal).decode()}${base64.b64encode(clau).decode()}"


def verifica_contrasenya(contrasenya: str, emmagatzemat: str) -> bool:
    try:
        algoritme, iteracions, sal_b64, clau_b64 = emmagatzemat.split("$")
        if algoritme != "pbkdf2_sha256":
            return False
        clau = hashlib.pbkdf2_hmac("sha256", contrasenya.encode("utf-8"), base64.b64decode(sal_b64), int(iteracions))
        return hmac.compare_digest(clau, base64.b64decode(clau_b64))
    except (ValueError, TypeError):
        return False


# --- TOTP (RFC 6238), compatible amb Google Authenticator, 1Password, Authy... --------------------

def nou_secret_totp() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def codi_totp(secret: str, instant: float | None = None, pas: int = 30) -> str:
    clau = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    comptador = int((instant if instant is not None else time.time()) // pas)
    digest = hmac.new(clau, struct.pack(">Q", comptador), hashlib.sha1).digest()
    desplacament = digest[-1] & 0x0F
    valor = struct.unpack(">I", digest[desplacament:desplacament + 4])[0] & 0x7FFFFFFF
    return f"{valor % 1_000_000:06d}"


def verifica_totp(secret: str, codi: str, instant: float | None = None) -> bool:
    codi = (codi or "").strip().replace(" ", "")
    if not codi.isdigit():
        return False
    ara = instant if instant is not None else time.time()
    return any(hmac.compare_digest(codi_totp(secret, ara + d * 30), codi) for d in (-1, 0, 1))


def uri_totp(secret: str, usuari: str) -> str:
    return f"otpauth://totp/Radar%20d%27ajuts:{usuari}?secret={secret}&issuer=Radar%20d%27ajuts%20Stimulo"


# --- Sessió signada ------------------------------------------------------------------------------

def _signa(secret: str, dades: str) -> str:
    return base64.urlsafe_b64encode(hmac.new(secret.encode(), dades.encode(), hashlib.sha256).digest()).decode().rstrip("=")


def crea_sessio(secret: str, usuari: str, hores: int) -> str:
    caducitat = int(time.time()) + hores * 3600
    dades = f"{usuari}|{caducitat}|{secrets.token_urlsafe(8)}"
    return f"{dades}|{_signa(secret, dades)}"


def valida_sessio(secret: str, token: str | None) -> str | None:
    """Retorna l'usuari si el token és vàlid i no ha caducat."""
    if not token or not secret or token.count("|") != 3:
        return None
    dades, signatura = token.rsplit("|", 1)
    if not hmac.compare_digest(_signa(secret, dades), signatura):
        return None
    usuari, caducitat, _ = dades.split("|")
    if int(caducitat) < time.time():
        return None
    return usuari


# --- Limitació d'intents d'accés -------------------------------------------------------------------

class LimitIntents:
    """Bloqueja una IP després de `maxim` intents fallits en `finestra` segons."""

    def __init__(self, maxim: int = 5, finestra: int = 900):
        self.maxim, self.finestra = maxim, finestra
        self._intents: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def bloquejat(self, ip: str) -> bool:
        with self._lock:
            ara = time.time()
            recents = [t for t in self._intents.get(ip, []) if ara - t < self.finestra]
            self._intents[ip] = recents
            return len(recents) >= self.maxim

    def falla(self, ip: str) -> None:
        with self._lock:
            self._intents.setdefault(ip, []).append(time.time())

    def reinicia(self, ip: str) -> None:
        with self._lock:
            self._intents.pop(ip, None)


def main() -> int:
    """Assistent per generar les claus d'accés (variables per al fitxer .env)."""
    import getpass

    contrasenya = getpass.getpass("Contrasenya nova (mínim 12 caràcters): ")
    if len(contrasenya) < 12:
        print("Massa curta: fes servir com a mínim 12 caràcters.")
        return 1
    if getpass.getpass("Repeteix-la: ") != contrasenya:
        print("No coincideixen.")
        return 1
    print("\nAfegeix aquestes línies al fitxer .env:\n")
    print(f"RADAR_CONTRASENYA_HASH='{hash_contrasenya(contrasenya)}'")
    print(f"RADAR_SECRET='{secrets.token_urlsafe(48)}'")
    if input("\nVols activar el segon factor (codi de 6 xifres al mòbil)? [s/N] ").strip().lower() in ("s", "si", "sí", "y"):
        totp = nou_secret_totp()
        print(f"RADAR_TOTP_SECRET='{totp}'")
        print(f"\nAfegeix-lo a l'app d'autenticació amb aquesta clau: {totp}")
        print(f"o amb aquest enllaç: {uri_totp(totp, os.environ.get('RADAR_USUARI', 'xavi'))}")
    return 0
