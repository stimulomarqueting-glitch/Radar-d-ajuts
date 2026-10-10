"""Tests del screening per a clients (DOGA com a exemple) i de la secció Clients de l'aplicació."""

import datetime as dt
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from radar import dades, screening
from radar.web.app import crea_app
from radar.web.db import BaseDades
from tests.test_web import CONTRASENYA, ORIGEN, ClientFals, config

AVUI = dt.date(2026, 10, 6)


class TestScreening(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = dades.carrega()
        cls.doga = screening.carrega_clients(cls.cat)["doga"]
        cls.sc = screening.screening(cls.cat, cls.doga, AVUI)

    def test_divisions_com_a_perfils(self):
        self.assertEqual([d.id for d in self.doga.divisions], ["motors", "neteja", "components", "postvenda"])
        motors = self.doga.divisio("motors")
        self.assertEqual(motors.perfil.zona, "ES-CT-B")  # heretat del client
        self.assertEqual(motors.perfil.beneficiari_com, ["gran_empresa"])

    def test_cada_divisio_te_linies_elegibles_i_ordenades(self):
        for r in self.sc.resultats:
            self.assertTrue(r.oportunitats, r.divisio.id)
            punts = [o.e.punts for o in r.oportunitats]
            self.assertEqual(punts, sorted(punts, reverse=True))
            for o in r.oportunitats:
                self.assertIn(o.e.prioritat, ("A", "B"))
                self.assertNotIn(o.f.estat, ("tancada", "sense_dades"))

    def test_gran_empresa_no_veu_linies_nomes_per_a_pimes(self):
        ids = {o.c.id for o in self.sc.oportunitats}
        self.assertFalse(ids & {"accio-cupons-estrategia", "accio-green", "accio-feder-innovacio-pimes", "eic-accelerator"})

    def test_idees_segons_els_temes_de_la_linia(self):
        for r in self.sc.resultats:
            for o in r.oportunitats:
                for i in o.idees:
                    self.assertTrue(set(i.focus) & set(o.c.focus))

    def test_avis_d_intensitat_nomes_per_a_ajuts_d_estat(self):
        for o in self.sc.oportunitats:
            intensitat = any("intensitat de la fitxa" in a for a in o.atencio)
            if o.c.nivell == "europa":
                self.assertFalse(intensitat, o.c.id)

    def test_informe_sense_javascript_i_amb_filtre(self):
        h = screening.informe_html(self.sc)
        self.assertNotIn("<script", h)
        self.assertIn('id="f-motors"', h)
        self.assertIn('#f-motors:checked ~ .contingut', h)
        self.assertNotIn("/expedients/nou", h)  # fora de l'aplicació no hi ha enllaços interns
        self.assertIn("/expedients/nou?convocatoria=", screening.informe_html(self.sc, app=True))

    def test_genera_fitxers(self):
        with tempfile.TemporaryDirectory() as d:
            f = screening.genera(self.sc, Path(d))
            self.assertTrue(f["html"].read_text().startswith("<!doctype html>"))
            self.assertIn("## Motors i motorreductors", f["md"].read_text())
            self.assertIn("BEGIN:VCALENDAR", f["ics"].read_text())

    def test_una_sola_divisio(self):
        sc = screening.screening(self.cat, self.doga, AVUI, ["neteja"])
        self.assertEqual([r.divisio.id for r in sc.resultats], ["neteja"])

    def test_context_per_a_l_assistent(self):
        t = screening.context_client(self.doga, self.doga.divisio("neteja"))
        self.assertIn("Sistemes de neteja", t)
        self.assertIn("en nom del client", t)


class TestClientsWeb(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.app = crea_app(config(Path(self.dir.name)), client=ClientFals())
        radar = self.app.state.radar
        radar._socis, radar._socis_hora = [], 1e12
        self.c = TestClient(self.app, base_url="https://testserver", headers=ORIGEN)
        self.c.post("/entrar", data={"usuari": "xavi", "contrasenya": CONTRASENYA})

    def tearDown(self):
        self.c.close()
        self.dir.cleanup()

    def test_pagina_i_informe(self):
        r = self.c.get("/clients")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Motors i motorreductors", r.text)
        r = self.c.get("/clients/doga/informe?divisio=motors")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("script-src", r.headers["content-security-policy"])  # cap script permès
        self.assertIn("client=doga&amp;divisio=motors", r.text)
        r = self.c.get("/clients/doga/informe?descarrega=1")
        self.assertIn("attachment", r.headers["content-disposition"])
        self.assertNotIn("/expedients/nou", r.text)
        self.assertEqual(self.c.get("/clients/inexistent/informe").status_code, 404)

    def test_sollicitud_per_a_una_divisio(self):
        r = self.c.get("/expedients/nou?convocatoria=cdti-lic&client=doga&divisio=motors")
        self.assertEqual(r.status_code, 200)
        self.assertIn('name="client" value="doga"', r.text)
        r = self.c.post("/expedients", data={"convocatoria": "cdti-lic", "client": "doga", "divisio": "motors"},
                        follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        id_ = int(r.headers["location"].rsplit("/", 1)[1])
        e = self.app.state.radar.db.expedient(id_)
        self.assertEqual(e["client"]["divisio"], "motors")
        self.assertTrue(e["titol"].startswith("DOGA · "))
        self.assertIn("<client>", e["context_sistema"])
        self.assertIn("Motors i motorreductors", e["context_sistema"])
        self.assertIn("DOGA", self.c.get("/expedients").text)
        self.assertEqual(self.c.post("/expedients", data={"convocatoria": "cdti-lic", "client": "x"}).status_code, 400)


class TestMigracio(unittest.TestCase):
    def test_afegeix_la_columna_client(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "vella.sqlite3"
            con = sqlite3.connect(path)
            con.execute("CREATE TABLE expedients (id INTEGER PRIMARY KEY AUTOINCREMENT, convocatoria_id TEXT NOT NULL, "
                        "titol TEXT NOT NULL, idea TEXT NOT NULL DEFAULT '', socis TEXT NOT NULL DEFAULT '[]', "
                        "estat TEXT NOT NULL DEFAULT 'en preparació', context_sistema TEXT NOT NULL, creat TEXT NOT NULL, "
                        "actualitzat TEXT NOT NULL)")
            con.execute("INSERT INTO expedients (convocatoria_id, titol, context_sistema, creat, actualitzat) "
                        "VALUES ('x', 'Antic', 'c', '2026-01-01', '2026-01-01')")
            con.commit()
            con.close()
            db = BaseDades(path)
            self.assertIsNone(db.expedients()[0]["client"])


if __name__ == "__main__":
    unittest.main()
