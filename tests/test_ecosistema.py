"""Tests de l'ecosistema de defensa, ús dual i espai (actors, trobades, requisits)."""

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from radar import dades, diari, ecosistema, screening
from radar.dades import ErrorValidacio
from radar.web.app import crea_app
from tests.test_web import CONTRASENYA, ORIGEN, ClientFals, config

AVUI = dt.date(2026, 10, 6)


class TestEcosistema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = dades.carrega()
        cls.eco = ecosistema.carrega(cls.cat)

    def test_carrega(self):
        ids = {a.id for a in self.eco.actors}
        self.assertTrue({"indra", "gutmar", "aeros", "white-cirrus"} <= ids)
        self.assertTrue(any(r.id == "pecal-aqap" for r in self.eco.requisits))

    def test_trobades_actives_sense_passades(self):
        actives = ecosistema.trobades_actives(self.eco, AVUI)
        ids = [t.id for t in actives]
        self.assertIn("feindef-2027", ids)
        self.assertNotIn("ap-institute-programa-defensa", ids)  # edició de febrer de 2026, ja passada
        self.assertEqual(actives[0].estat(AVUI), "en curs")

    def test_recordatoris(self):
        self.assertTrue(any("FEINDEF" in r and "21 dies" in r for r in ecosistema.recordatoris(self.eco, dt.date(2027, 4, 27))))
        self.assertTrue(any("demà" in r for r in ecosistema.recordatoris(self.eco, dt.date(2027, 5, 17))))
        self.assertEqual(ecosistema.recordatoris(self.eco, dt.date(2027, 5, 1)), [])

    def test_validacio(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "eco.yaml"
            p.write_text("trobades:\n  - {id: x, nom: X, tipus: fira, zona: ES, ambits: [inventat]}\n")
            with self.assertRaises(ErrorValidacio):
                ecosistema.carrega(self.cat, p)
            p.write_text("trobades:\n  - {id: x, nom: X, tipus: fira, zona: ES, convocatoria: no-existeix}\n")
            with self.assertRaises(ErrorValidacio):
                ecosistema.carrega(self.cat, p)

    def test_markdown(self):
        md = ecosistema.markdown(self.eco, AVUI)
        self.assertIn("## Requisits per entrar al sector", md)
        self.assertIn("GUTMAR", md)

    def test_noves_linies_de_defensa(self):
        c = self.cat.per_id("eic-step-defence-scaleup")
        self.assertEqual(c.calendari.tancament, dt.date(2026, 10, 28))
        self.assertIn("defensa", c.focus)


class TestSectorAlScreening(unittest.TestCase):
    def test_seccio_per_a_divisions_amb_temes_de_defensa(self):
        cat = dades.carrega()
        doga = screening.carrega_clients(cat)["doga"]
        sc = screening.screening(cat, doga, AVUI)
        self.assertIsNotNone(sc.sector)
        self.assertEqual([d.id for d in sc.sector["divisions"]], ["motors"])
        for x in sc.sector["linies"]:
            self.assertTrue(set(x["c"].focus) & ecosistema.AMBITS_SECTOR)
            self.assertIsNotNone(x["e"].rol)
        self.assertNotIn("eic-step-defence-scaleup", {x["c"].id for x in sc.sector["linies"]})  # només pimes
        h = screening.informe_html(sc)
        self.assertIn('class="seccio sector" data-divisio="motors"', h)
        self.assertIsNone(screening.screening(cat, doga, AVUI, ["postvenda"]).sector)

    def test_recordatoris_al_correu_del_mati(self):
        r = diari.prepara_avis(dt.date(2027, 4, 27), envia=False, actualitza_estat=False,
                               fitxer_contactes=str(Path(tempfile.gettempdir()) / "no-existeix.json"))
        self.assertGreaterEqual(r.recordatoris, 1)
        if r.copia:
            for ext in (".html", ".txt"):
                r.copia.with_suffix(ext).unlink(missing_ok=True)


class TestPaginaWeb(unittest.TestCase):
    def test_pagina_defensa_i_espai(self):
        with tempfile.TemporaryDirectory() as d:
            app = crea_app(config(Path(d)), client=ClientFals())
            with TestClient(app, base_url="https://testserver", headers=ORIGEN) as c:
                c.post("/entrar", data={"usuari": "xavi", "contrasenya": CONTRASENYA})
                r = c.get("/ecosistema")
                self.assertEqual(r.status_code, 200)
                self.assertIn("EIC STEP Scale Up Defence 2026", r.text)
                self.assertIn("PECAL", r.text)


if __name__ == "__main__":
    unittest.main()
