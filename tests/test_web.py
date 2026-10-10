"""Tests de l'aplicació web: accés, seguretat, expedients, xat (amb un client d'IA fals) i exportació.

Cap crida real a l'API: el client d'Anthropic se substitueix per un de fals que reprodueix el flux.
"""

import datetime as dt
import io
import json
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from radar import dades, diari
from radar.socis import Soci
from radar.web import auth, ia
from radar.web.app import crea_app, mime_real
from radar.web.config import Config
from radar.web.db import BaseDades
from radar.web.render import markdown_html

CONTRASENYA = "una-contrasenya-llarga"
CONVOCATORIA = "accio-exploracio-tecnologica"
ORIGEN = {"origin": "https://testserver"}


class FlussFals:
    def __init__(self, text: str, stop_reason: str = "end_turn"):
        self.text, self.stop_reason = text, stop_reason

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def __aiter__(self):
        return self._events()

    async def _events(self):
        yield SimpleNamespace(type="content_block_start", content_block=SimpleNamespace(type="server_tool_use",
                                                                                       name="web_search"))
        yield SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(type="thinking_delta", thinking="Reviso."))
        for tros in (self.text[:10], self.text[10:]):
            yield SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(type="text_delta", text=tros))

    async def get_final_message(self):
        contingut = [{"type": "thinking", "thinking": "Reviso.", "signature": "sig"},
                     {"type": "text", "text": self.text}]
        return SimpleNamespace(stop_reason=self.stop_reason, to_dict=lambda mode="json": {"content": contingut})


class ClientFals:
    def __init__(self, respostes=None, error=None):
        self.peticions, self.respostes, self.error = [], list(respostes or []), error
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **peticio):
        self.peticions.append(json.loads(json.dumps(peticio)))
        if self.error:
            raise self.error
        return FlussFals(self.respostes.pop(0) if self.respostes else "## Document\n\nText de prova.")


def config(tmp: Path, **extra) -> Config:
    valors = dict(usuari="xavi", contrasenya_hash=auth.hash_contrasenya(CONTRASENYA, iteracions=1000),
                  totp_secret="", secret="s" * 48, cookie_segura=True, hores_sessio=2, dir_dades_app=tmp,
                  model="claude-opus-5-5", esforc="high", fallbacks=True, cerca_web=True, mida_max_fitxer_mb=1)
    valors.update(extra)
    return Config(**valors)


SOCI = Soci(clau="exemple", nom="Motors Exemple SA", tipus="empresa", relacio="client", zona="ES-CT-B",
            focus=["deep_tech", "prova_concepte", "industria", "robotica", "mobilitat"],
            persones=[{"nom": "Anna Puig", "email": "anna@motors-exemple.example", "carrec": ""}])


class BaseWeb(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.dir.name)
        self.ia = ClientFals()
        self.app = crea_app(config(self.tmp), client=self.ia)
        radar = self.app.state.radar
        radar._socis, radar._socis_hora, radar._socis_motiu = [SOCI], time.time(), ""
        self.c = TestClient(self.app, base_url="https://testserver", headers=ORIGEN)

    def tearDown(self):
        self.c.close()
        self.dir.cleanup()

    def entra(self, **extra):
        return self.c.post("/entrar", data={"usuari": "xavi", "contrasenya": CONTRASENYA, "seguent": "/", **extra},
                           follow_redirects=False)

    def crea_expedient(self) -> int:
        self.entra()
        r = self.c.post("/expedients", data={"convocatoria": CONVOCATORIA, "titol": "Prototip de prova",
                                             "idea": "Un sensor", "socis": ["exemple"]}, follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        return int(r.headers["location"].rsplit("/", 1)[1])

    def xat(self, id_: int, **cos) -> list[dict]:
        r = self.c.post(f"/expedients/{id_}/xat", json=cos)
        self.assertEqual(r.status_code, 200, r.text)
        return [json.loads(l[6:]) for l in r.text.split("\n\n") if l.startswith("data: ")]


class TestAcces(BaseWeb):
    def test_sense_sessio_redirigeix_a_entrar(self):
        r = self.c.get("/expedients", follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertTrue(r.headers["location"].startswith("/entrar?seguent=%2Fexpedients"))
        self.assertEqual(self.c.post("/expedients", data={}).status_code, 401)
        self.assertEqual(self.c.get("/salut").text, "ok")

    def test_entrar_i_sortir(self):
        r = self.entra()
        self.assertEqual(r.status_code, 303)
        galeta = r.headers["set-cookie"].lower()
        for atribut in ("httponly", "secure", "samesite=lax"):
            self.assertIn(atribut, galeta)
        r = self.c.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn('id="radar-dades"', r.text)
        self.assertIn("default-src 'self'", r.headers["content-security-policy"])
        self.assertEqual(r.headers["x-frame-options"], "DENY")
        self.c.post("/sortir")
        self.assertEqual(self.c.get("/", follow_redirects=False).status_code, 303)

    def test_contrasenya_incorrecta_i_limit_d_intents(self):
        for _ in range(5):
            self.assertEqual(self.entra(contrasenya="no").status_code, 401)
        self.assertEqual(self.entra().status_code, 429)  # bloquejat encara que ara sigui correcta

    def test_galeta_manipulada(self):
        self.c.cookies.set(auth.NOM_COOKIE, auth.crea_sessio("x" * 48, "xavi", 2))
        self.assertEqual(self.c.get("/", follow_redirects=False).status_code, 303)

    def test_redireccio_oberta(self):
        r = self.entra(seguent="//dolent.example/")
        self.assertEqual(r.headers["location"], "/")

    def test_peticio_d_un_altre_origen(self):
        self.entra()
        r = self.c.post("/expedients", data={"convocatoria": CONVOCATORIA}, headers={"origin": "https://dolent.example"})
        self.assertEqual(r.status_code, 403)

    def test_sense_configurar_no_es_pot_entrar(self):
        app = crea_app(config(self.tmp / "b", contrasenya_hash="", secret=""), client=self.ia)
        with TestClient(app, base_url="https://testserver", headers=ORIGEN) as c:
            r = c.post("/entrar", data={"usuari": "xavi", "contrasenya": ""})
            self.assertEqual(r.status_code, 503)

    def test_segon_factor(self):
        secret = auth.nou_secret_totp()
        app = crea_app(config(self.tmp / "t", totp_secret=secret), client=self.ia)
        with TestClient(app, base_url="https://testserver", headers=ORIGEN) as c:
            dades_ = {"usuari": "xavi", "contrasenya": CONTRASENYA}
            self.assertEqual(c.post("/entrar", data={**dades_, "codi": "000000"}).status_code, 401)
            r = c.post("/entrar", data={**dades_, "codi": auth.codi_totp(secret)}, follow_redirects=False)
            self.assertEqual(r.status_code, 303)


class TestExpedients(BaseWeb):
    def test_tauler_enllaca_a_preparar(self):
        self.entra()
        self.assertIn("/static/tauler.js", self.c.get("/").text)
        r = self.c.get(f"/expedients/nou?convocatoria={CONVOCATORIA}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Motors Exemple SA", r.text)

    def test_crea_expedient_amb_context(self):
        id_ = self.crea_expedient()
        e = self.app.state.radar.db.expedient(id_)
        self.assertEqual(e["convocatoria_id"], CONVOCATORIA)
        self.assertIn("<convocatoria>", e["context_sistema"])
        self.assertIn("Motors Exemple SA", e["context_sistema"])
        self.assertEqual(self.c.get(f"/expedients/{id_}").status_code, 200)
        self.assertIn("Prototip de prova", self.c.get("/expedients").text)

    def test_xat_desa_document_i_historial(self):
        id_ = self.crea_expedient()
        events = self.xat(id_, accio="fitxa", text="curt")
        tipus = [e["tipus"] for e in events]
        self.assertEqual(tipus[0], "eina")
        self.assertIn("pensament", tipus)
        self.assertEqual(tipus[-2:], ["document", "fi"])
        doc = self.app.state.radar.db.document(id_, "fitxa")
        self.assertEqual(doc["versio"], 1)
        self.xat(id_, text="Fes-lo més curt")
        primera, segona = self.ia.peticions
        self.assertEqual(primera["model"], "claude-opus-5-5")
        self.assertEqual(primera["thinking"], {"type": "adaptive", "display": "summarized"})
        self.assertEqual(primera["system"], segona["system"])  # context fix: memòria cau
        # L'historial s'envia tal com es va rebre (blocs de pensament inclosos) i la primera part no canvia
        self.assertEqual(segona["messages"][:len(primera["messages"])], primera["messages"])
        self.assertEqual(segona["messages"][len(primera["messages"])]["content"][0]["type"], "thinking")
        self.assertIn("Indicacions addicionals: curt", json.dumps(primera["messages"][0], ensure_ascii=False))
        pagina = self.c.get(f"/expedients/{id_}").text
        self.assertIn("<h2>Document</h2>", pagina)  # Markdown renderitzat

    def test_error_de_l_api_desfa_el_torn(self):
        id_ = self.crea_expedient()
        self.ia.error = RuntimeError("caigut")
        events = self.xat(id_, text="Hola")
        self.assertEqual(events[-1]["tipus"], "error")
        self.assertEqual(self.app.state.radar.db.missatges(id_), [])
        self.assertNotIn(id_, self.app.state.radar.ocupats)

    def test_sense_clau_de_l_api(self):
        app = crea_app(config(self.tmp / "c"), client=None)
        with TestClient(app, base_url="https://testserver", headers=ORIGEN) as c:
            c.post("/entrar", data={"usuari": "xavi", "contrasenya": CONTRASENYA})
            r = c.post("/expedients", data={"convocatoria": CONVOCATORIA}, follow_redirects=False)
            id_ = int(r.headers["location"].rsplit("/", 1)[1])
            import os
            from unittest import mock
            with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
                self.assertEqual(c.post(f"/expedients/{id_}/xat", json={"text": "hola"}).status_code, 503)

    def test_fitxers_i_edicio_manual(self):
        id_ = self.crea_expedient()
        r = self.c.post(f"/expedients/{id_}/fitxers", files={"fitxer": ("bases.md", b"# Bases\nRequisit 1", "text/plain")},
                        follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        r = self.c.post(f"/expedients/{id_}/fitxers", files={"fitxer": ("prog.exe", b"MZ\x00\x00", "application/pdf")})
        self.assertEqual(r.status_code, 415)
        r = self.c.post(f"/expedients/{id_}/fitxers", files={"fitxer": ("gran.txt", b"a" * (1024 * 1024 + 1), "text/plain")})
        self.assertEqual(r.status_code, 413)
        self.xat(id_, accio="memoria")
        enviat = json.dumps(self.ia.peticions[-1]["messages"][0]["content"], ensure_ascii=False)
        self.assertIn("Requisit 1", enviat)
        self.assertTrue(self.app.state.radar.db.fitxers(id_)[0]["enviat"])
        # Edició manual: versió nova i avís a l'assistent al torn següent
        r = self.c.post(f"/expedients/{id_}/documents/memoria", data={"contingut": "Memòria revisada a mà"},
                        follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertEqual(self.app.state.radar.db.document(id_, "memoria")["origen"], "edició manual")
        self.assertIn("Memòria revisada a mà", self.c.get(f"/expedients/{id_}/documents/memoria").text)
        self.xat(id_, text="Revisa-la")
        darrers = self.ia.peticions[-1]["messages"]
        self.assertEqual(darrers[-1]["role"], "system")
        self.assertIn("Memòria revisada a mà", darrers[-1]["content"])

    def test_exporta(self):
        id_ = self.crea_expedient()
        self.xat(id_, accio="fitxa")
        r = self.c.get(f"/expedients/{id_}/exporta.docx")
        self.assertEqual(r.status_code, 200)
        self.assertIn("prototip-de-prova.docx", r.headers["content-disposition"])
        self.assertIn("word/document.xml", zipfile.ZipFile(io.BytesIO(r.content)).namelist())
        r = self.c.get(f"/expedients/{id_}/exporta.zip")
        self.assertEqual(zipfile.ZipFile(io.BytesIO(r.content)).namelist(), ["fitxa-v1.md"])

    def test_estat_i_idea(self):
        id_ = self.crea_expedient()
        self.c.post(f"/expedients/{id_}", data={"estat": "presentat", "idea": "Idea nova"})
        e = self.app.state.radar.db.expedient(id_)
        self.assertEqual((e["estat"], e["idea"]), ("presentat", "Idea nova"))
        self.assertIn("Idea nova", e["context_sistema"])  # encara sense conversa: es refà el context

    def test_socis_avisos_i_configuracio(self):
        self.entra()
        r = self.c.get(f"/socis?convocatoria={CONVOCATORIA}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("mailto:anna%40motors-exemple.example", r.text)
        self.assertEqual(self.c.get("/avisos").status_code, 200)
        self.assertEqual(self.c.get("/avisos/..%2Fsecret.html").status_code, 404)
        r = self.c.get("/configuracio")
        self.assertIn("claude-opus-5-5", r.text)
        self.assertNotIn(CONTRASENYA, r.text)


class TestPlaWeb(BaseWeb):
    def test_pla_amb_socis_i_sense_scripts(self):
        self.assertEqual(self.c.get("/pla", follow_redirects=False).status_code, 303)
        self.entra()
        r = self.c.get("/pla?des=2026-11-01&fins=2027-06-30")
        self.assertEqual(r.status_code, 200)
        self.assertIn("default-src 'none'", r.headers["content-security-policy"])
        self.assertIn("Projectes de producte amb clients i consorcis", r.text)
        self.assertIn("Clients i socis (Holded)", r.text)
        self.assertIn("Motors Exemple SA", r.text)
        self.assertIn("/expedients/nou?convocatoria=", r.text)
        self.assertNotIn("<script", r.text)
        self.assertIn('href="/pla"', self.c.get("/").text)
        baixada = self.c.get("/pla?descarrega=1")
        self.assertIn("attachment", baixada.headers["content-disposition"])
        self.assertNotIn("/expedients/nou", baixada.text)
        self.assertEqual(self.c.get("/pla?des=2027-07-01&fins=2027-01-01").status_code, 400)
        self.assertEqual(self.c.get("/pla?des=ahir").status_code, 400)


class TestSeguimentWeb(BaseWeb):
    def test_pagina_de_seguiment(self):
        self.assertEqual(self.c.get("/seguiment", follow_redirects=False).status_code, 303)
        self.entra()
        r = self.c.get("/seguiment")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Cupons ACCIÓ a la competitivitat de l&#39;empresa", r.text)
        self.assertIn("protecció de la innovació", r.text)
        self.assertIn("/expedients/nou?convocatoria=accio-cupons-proteccio", r.text)
        self.assertIn("Motors Exemple SA", r.text)  # client de Holded a Catalunya
        self.assertIn('href="/seguiment" aria-current="page"', r.text)
        self.assertIn("default-src 'self'", r.headers["content-security-policy"])


class TestUtilitats(unittest.TestCase):
    def test_markdown_segur(self):
        h = markdown_html("# Títol\n\n<script>alert(1)</script> [x](javascript:alert(1)) [y](https://a.example)")
        self.assertIn("<h1>Títol</h1>", h)
        self.assertNotIn("<script>", h)
        self.assertNotIn("javascript:", h)
        self.assertIn('href="https://a.example"', h)

    def test_tipus_de_fitxer_pels_bytes(self):
        self.assertEqual(mime_real(b"%PDF-1.7", "a.pdf", "text/plain"), "application/pdf")
        self.assertEqual(mime_real(b"\x89PNG\r\n\x1a\n", "a.jpg", "image/jpeg"), "image/png")
        self.assertIsNone(mime_real(b"MZ\x00", "a.pdf", "application/pdf"))
        self.assertEqual(mime_real(b"hola", "notes.md", None), "text/markdown")

    def test_contrasenya_i_sessio(self):
        h = auth.hash_contrasenya("correcta", iteracions=1000)
        self.assertTrue(auth.verifica_contrasenya("correcta", h))
        self.assertFalse(auth.verifica_contrasenya("incorrecta", h))
        token = auth.crea_sessio("k" * 40, "xavi", 1)
        self.assertEqual(auth.valida_sessio("k" * 40, token), "xavi")
        self.assertIsNone(auth.valida_sessio("k" * 40, token.replace("xavi", "admin")))
        self.assertIsNone(auth.valida_sessio("k" * 40, auth.crea_sessio("k" * 40, "xavi", -1)))

    def test_totp_rfc6238(self):
        secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # "12345678901234567890"
        self.assertEqual(auth.codi_totp(secret, 59), "287082")
        self.assertEqual(auth.codi_totp(secret, 1111111109), "081804")
        self.assertTrue(auth.verifica_totp(secret, "287082", 59 + 30))
        self.assertFalse(auth.verifica_totp(secret, "287082", 59 + 120))

    def test_peticio_a_l_api(self):
        cfg = config(Path("/tmp"))
        p = ia._peticio(cfg, "sistema", [{"role": "user", "content": "hola"}])
        self.assertEqual(p["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertEqual({t["type"] for t in p["tools"]}, {"web_search_20260209", "web_fetch_20260209"})
        self.assertEqual(p["fallbacks"], "default")
        self.assertNotIn("budget_tokens", json.dumps(p))

    def test_recordatoris_de_terminis(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "r.sqlite3"
            db = BaseDades(path)
            db.crea_expedient(CONVOCATORIA, "Expedient de prova", "", [], "context")
            cat = dades.carrega()
            tancament = cat.per_id(CONVOCATORIA).calendari.tancament
            r = diari.recordatoris_expedients(cat, tancament - dt.timedelta(days=7), path)
            self.assertEqual(len(r), 1)
            self.assertIn("d'aquí a 7 dies", r[0])
            self.assertEqual(diari.recordatoris_expedients(cat, tancament - dt.timedelta(days=8), path), [])

    def test_dates_de_revisio_al_correu_del_mati(self):
        cat = dades.carrega()
        r = diari.senyals_manuals(cat, dt.date(2026, 11, 16))
        self.assertTrue(any("Indústria del Coneixement – Producte" in x and "OTRI" in x for x in r))
        self.assertEqual(diari.senyals_manuals(cat, dt.date(2026, 11, 17)), [])


if __name__ == "__main__":
    unittest.main()
