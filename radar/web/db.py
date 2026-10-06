"""Base de dades local (SQLite) dels expedients de sol·licitud: converses, documents i fitxers."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS expedients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    convocatoria_id TEXT NOT NULL,
    titol TEXT NOT NULL,
    idea TEXT NOT NULL DEFAULT '',
    socis TEXT NOT NULL DEFAULT '[]',          -- JSON: socis triats
    estat TEXT NOT NULL DEFAULT 'en preparació', -- en preparació / presentat / concedit / denegat / arxivat
    client TEXT NOT NULL DEFAULT '',           -- JSON {id, nom, divisio, divisio_nom} si és per a un client
    context_sistema TEXT NOT NULL,             -- instantània del context (fixa durant tota la conversa)
    creat TEXT NOT NULL,
    actualitzat TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS missatges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expedient_id INTEGER NOT NULL REFERENCES expedients(id) ON DELETE CASCADE,
    rol TEXT NOT NULL,                         -- user / assistant / system
    contingut TEXT NOT NULL,                   -- JSON exactament com es va enviar o rebre de l'API
    visible TEXT NOT NULL DEFAULT '',          -- text per mostrar a la interfície
    accio TEXT NOT NULL DEFAULT '',            -- plantilla de document que ha originat el torn
    creat TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expedient_id INTEGER NOT NULL REFERENCES expedients(id) ON DELETE CASCADE,
    tipus TEXT NOT NULL,
    titol TEXT NOT NULL,
    contingut TEXT NOT NULL,
    versio INTEGER NOT NULL,
    origen TEXT NOT NULL DEFAULT 'assistent',  -- assistent / edició manual
    creat TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fitxers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expedient_id INTEGER NOT NULL REFERENCES expedients(id) ON DELETE CASCADE,
    nom TEXT NOT NULL,
    ruta TEXT NOT NULL,
    mime TEXT NOT NULL,
    mida INTEGER NOT NULL,
    enviat INTEGER NOT NULL DEFAULT 0,         -- 1 quan ja s'ha passat a l'assistent
    creat TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS esdeveniments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipus TEXT NOT NULL,
    detall TEXT NOT NULL,
    creat TEXT NOT NULL
);
"""


def ara() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class BaseDades:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self.connexio() as c:
            c.executescript(ESQUEMA)
            columnes = {f["name"] for f in c.execute("PRAGMA table_info(expedients)")}
            if "client" not in columnes:  # bases creades abans dels clients de servei
                c.execute("ALTER TABLE expedients ADD COLUMN client TEXT NOT NULL DEFAULT ''")

    @contextmanager
    def connexio(self):
        with self._lock:
            c = sqlite3.connect(self.path)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys = ON")
            try:
                yield c
                c.commit()
            finally:
                c.close()

    # --- expedients
    def crea_expedient(self, convocatoria_id: str, titol: str, idea: str, socis: list[dict], context: str,
                       client: dict | None = None) -> int:
        with self.connexio() as c:
            cur = c.execute(
                "INSERT INTO expedients (convocatoria_id, titol, idea, socis, context_sistema, client, creat, actualitzat) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (convocatoria_id, titol, idea, json.dumps(socis, ensure_ascii=False), context,
                 json.dumps(client, ensure_ascii=False) if client else "", ara(), ara()))
            return cur.lastrowid

    @staticmethod
    def _fila(fila) -> dict:
        d = dict(fila)
        d["socis"] = json.loads(d["socis"])
        d["client"] = json.loads(d["client"]) if d.get("client") else None
        return d

    def expedient(self, id_: int) -> dict | None:
        with self.connexio() as c:
            fila = c.execute("SELECT * FROM expedients WHERE id = ?", (id_,)).fetchone()
        return self._fila(fila) if fila else None

    def expedients(self) -> list[dict]:
        with self.connexio() as c:
            files = c.execute("SELECT * FROM expedients ORDER BY actualitzat DESC").fetchall()
        return [self._fila(f) for f in files]

    def actualitza_expedient(self, id_: int, **camps) -> None:
        permesos = {"titol", "idea", "estat"}
        camps = {k: v for k, v in camps.items() if k in permesos}
        if not camps:
            return
        sets = ", ".join(f"{k} = ?" for k in camps)
        with self.connexio() as c:
            c.execute(f"UPDATE expedients SET {sets}, actualitzat = ? WHERE id = ?", (*camps.values(), ara(), id_))

    def actualitza_context(self, id_: int, context: str) -> None:
        """Només abans del primer missatge: després el context és fix (vegeu ia.actualitzacio_context)."""
        with self.connexio() as c:
            if c.execute("SELECT COUNT(*) FROM missatges WHERE expedient_id = ?", (id_,)).fetchone()[0]:
                raise ValueError("La conversa ja ha començat: el context no es pot canviar.")
            c.execute("UPDATE expedients SET context_sistema = ?, actualitzat = ? WHERE id = ?", (context, ara(), id_))

    def toca(self, id_: int) -> None:
        with self.connexio() as c:
            c.execute("UPDATE expedients SET actualitzat = ? WHERE id = ?", (ara(), id_))

    # --- missatges (només s'hi afegeix: l'historial no es reescriu mai)
    def afegeix_missatge(self, expedient_id: int, rol: str, contingut, visible: str = "", accio: str = "") -> int:
        with self.connexio() as c:
            cur = c.execute(
                "INSERT INTO missatges (expedient_id, rol, contingut, visible, accio, creat) VALUES (?, ?, ?, ?, ?, ?)",
                (expedient_id, rol, json.dumps(contingut, ensure_ascii=False), visible, accio, ara()))
            return cur.lastrowid

    def esborra_missatges(self, ids: list[int]) -> None:
        """Només per desfer un torn que no ha arribat a tenir resposta (no s'ha enviat mai a l'API)."""
        if ids:
            with self.connexio() as c:
                c.execute(f"DELETE FROM missatges WHERE id IN ({','.join('?' * len(ids))})", ids)

    def missatges(self, expedient_id: int) -> list[dict]:
        with self.connexio() as c:
            files = c.execute("SELECT * FROM missatges WHERE expedient_id = ? ORDER BY id", (expedient_id,)).fetchall()
        sortida = []
        for f in files:
            d = dict(f)
            d["contingut"] = json.loads(d["contingut"])
            sortida.append(d)
        return sortida

    # --- documents (cada desament és una versió nova)
    def desa_document(self, expedient_id: int, tipus: str, titol: str, contingut: str, origen: str = "assistent") -> int:
        with self.connexio() as c:
            versio = (c.execute("SELECT MAX(versio) FROM documents WHERE expedient_id = ? AND tipus = ?",
                                (expedient_id, tipus)).fetchone()[0] or 0) + 1
            cur = c.execute(
                "INSERT INTO documents (expedient_id, tipus, titol, contingut, versio, origen, creat) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)", (expedient_id, tipus, titol, contingut, versio, origen, ara()))
            c.execute("UPDATE expedients SET actualitzat = ? WHERE id = ?", (ara(), expedient_id))
            return cur.lastrowid

    def documents_actuals(self, expedient_id: int) -> list[dict]:
        with self.connexio() as c:
            files = c.execute(
                "SELECT d.* FROM documents d JOIN (SELECT tipus, MAX(versio) v FROM documents WHERE expedient_id = ? "
                "GROUP BY tipus) u ON d.tipus = u.tipus AND d.versio = u.v WHERE d.expedient_id = ? ORDER BY d.id",
                (expedient_id, expedient_id)).fetchall()
        return [dict(f) for f in files]

    def document(self, expedient_id: int, tipus: str, versio: int | None = None) -> dict | None:
        with self.connexio() as c:
            if versio:
                fila = c.execute("SELECT * FROM documents WHERE expedient_id = ? AND tipus = ? AND versio = ?",
                                 (expedient_id, tipus, versio)).fetchone()
            else:
                fila = c.execute("SELECT * FROM documents WHERE expedient_id = ? AND tipus = ? ORDER BY versio DESC "
                                 "LIMIT 1", (expedient_id, tipus)).fetchone()
        return dict(fila) if fila else None

    def versions(self, expedient_id: int, tipus: str) -> list[dict]:
        with self.connexio() as c:
            files = c.execute("SELECT id, versio, origen, creat FROM documents WHERE expedient_id = ? AND tipus = ? "
                              "ORDER BY versio DESC", (expedient_id, tipus)).fetchall()
        return [dict(f) for f in files]

    # --- fitxers
    def afegeix_fitxer(self, expedient_id: int, nom: str, ruta: str, mime: str, mida: int) -> int:
        with self.connexio() as c:
            cur = c.execute("INSERT INTO fitxers (expedient_id, nom, ruta, mime, mida, creat) VALUES (?, ?, ?, ?, ?, ?)",
                            (expedient_id, nom, ruta, mime, mida, ara()))
            return cur.lastrowid

    def fitxers(self, expedient_id: int, pendents: bool = False) -> list[dict]:
        sql = "SELECT * FROM fitxers WHERE expedient_id = ?" + (" AND enviat = 0" if pendents else "") + " ORDER BY id"
        with self.connexio() as c:
            return [dict(f) for f in c.execute(sql, (expedient_id,)).fetchall()]

    def marca_fitxers_pendents(self, ids: list[int]) -> None:
        if ids:
            with self.connexio() as c:
                c.execute(f"UPDATE fitxers SET enviat = 0 WHERE id IN ({','.join('?' * len(ids))})", ids)

    def marca_fitxers_enviats(self, ids: list[int]) -> None:
        if not ids:
            return
        with self.connexio() as c:
            c.execute(f"UPDATE fitxers SET enviat = 1 WHERE id IN ({','.join('?' * len(ids))})", ids)

    def fitxer(self, expedient_id: int, id_: int) -> dict | None:
        with self.connexio() as c:
            fila = c.execute("SELECT * FROM fitxers WHERE expedient_id = ? AND id = ?", (expedient_id, id_)).fetchone()
        return dict(fila) if fila else None

    def esborra_fitxer(self, expedient_id: int, id_: int) -> None:
        with self.connexio() as c:
            c.execute("DELETE FROM fitxers WHERE expedient_id = ? AND id = ?", (expedient_id, id_))

    # --- registre
    def registra(self, tipus: str, detall: str) -> None:
        with self.connexio() as c:
            c.execute("INSERT INTO esdeveniments (tipus, detall, creat) VALUES (?, ?, ?)", (tipus, detall, ara()))

    def esdeveniments(self, limit: int = 50) -> list[dict]:
        with self.connexio() as c:
            return [dict(f) for f in c.execute("SELECT * FROM esdeveniments ORDER BY id DESC LIMIT ?", (limit,))]
