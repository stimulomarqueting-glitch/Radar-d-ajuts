"""Tests del seguiment actiu (Cupons ACCIÓ): catàleg, estat, recordatoris, vigilant de pàgina i pla."""

import dataclasses
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from radar import dades, pla, seguiment, vigilancia
from radar.dades import Font

AVUI = dt.date(2026, 10, 10)
CUPONS = {"accio-cupons-programes-europeus", "accio-cupons-proteccio", "accio-cupons-green",
          "accio-cupons-estrategia", "accio-cupons-ia", "accio-cupons-internacionalitzacio"}


class TestCataleg(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = dades.carrega()

    def test_modalitats_dels_cupons(self):
        self.assertIn("cupons-accio", self.cat.programes)
        modalitats = self.cat.del_programa("cupons-accio")
        self.assertEqual({c.id for c in modalitats}, CUPONS)
        for c in modalitats:
            self.assertTrue(c.seguiment, c.id)
            self.assertEqual((c.instrument, c.zones, c.beneficiaris), ("cupo", ["ES-CT"], ["pime"]), c.id)
            self.assertTrue(c.compartir_clients, c.id)
        europeus = self.cat.per_id("accio-cupons-programes-europeus")
        self.assertEqual((europeus.import_max_eur, europeus.calendari.tancament), (12000, dt.date(2026, 11, 16)))
        self.assertEqual(self.cat.programes["cupons-accio"].bdns, "904675")

    def test_programa_desconegut(self):
        with tempfile.TemporaryDirectory() as d:
            for f in dades.DIR_DADES.glob("*.yaml"):
                (Path(d) / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            conv = Path(d) / "convocatories.yaml"
            conv.write_text(conv.read_text(encoding="utf-8").replace("programa: cupons-accio", "programa: cap", 1),
                            encoding="utf-8")
            with self.assertRaises(dades.ErrorValidacio):
                dades.carrega(Path(d))


class TestEstatIRecordatoris(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = dades.carrega()

    def test_noms_curts(self):
        self.assertEqual(seguiment.nom_curt(self.cat.per_id("accio-cupons-programes-europeus")),
                         "programes europeus d'R+D+I")
        self.assertEqual(seguiment.nom_curt(self.cat.per_id("accio-cupons-proteccio")), "protecció de la innovació")
        self.assertEqual(seguiment.nom_curt(self.cat.per_id("eic-accelerator")), "EIC Accelerator (Open i Challenges)")

    def test_per_programa_obertes_primer(self):
        [(programa, modalitats)] = seguiment.per_programa(self.cat, AVUI)
        self.assertEqual(programa.id, "cupons-accio")
        estats = [e.f.estat for _c, e in modalitats]
        self.assertEqual(estats, sorted(estats, key=lambda x: seguiment.ORDRE_ESTAT[x]))
        e = seguiment.estat(self.cat.per_id("accio-cupons-proteccio"), AVUI)
        self.assertEqual((e.etiqueta, e.dies, e.urgent), ("Oberta", 37, False))
        self.assertIn("16/11/2026", e.text)
        self.assertTrue(seguiment.estat(self.cat.per_id("accio-cupons-proteccio"), dt.date(2026, 11, 1)).urgent)

    def test_recordatoris_agrupats_per_programa(self):
        self.assertEqual(seguiment.recordatoris(self.cat, AVUI), [])  # 37 dies: cap fita
        [r] = seguiment.recordatoris(self.cat, dt.date(2026, 11, 9))
        self.assertIn("tanquen d'aquí a 7 dies (16/11/2026)", r)
        self.assertIn("o quan s'exhaureixi el pressupost", r)
        self.assertIn("protecció de la innovació", r)
        self.assertIn("Avisa els clients", r)
        self.assertIn("tanquen avui", seguiment.recordatoris(self.cat, dt.date(2026, 11, 16))[0])
        [obertura] = seguiment.recordatoris(self.cat, dt.date(2027, 4, 15))
        self.assertIn("obren d'aquí a 30 dies (≈ 15/05/2027)", obertura)

    def test_candidats_holded(self):
        S = lambda nom, relacio, tipus, zona: dataclasses.make_dataclass(  # noqa: E731
            "S", ["nom", "relacio", "tipus", "zona"])(nom, relacio, tipus, zona)
        socis = [S("B client", "client", "empresa", "ES-CT-B"), S("A lead", "lead", "startup", "ES-CT"),
                 S("Proveïdor", "supplier", "empresa", "ES-CT-B"), S("Hospital", "lead", "hospital", "ES-CT-B"),
                 S("Madrid", "client", "empresa", "ES-MD")]
        self.assertEqual([s.nom for s in seguiment.candidats_holded(socis)], ["B client", "A lead"])


HTML_1 = """<html><head><script>var termini = "2026";</script><style>p{}</style></head><body>
<nav><a>Convocatòries 2026</a></nav>
<h1>Cupons ACCIÓ a la competitivitat de l'empresa</h1>
<ul><li>Cupons d'estratègia: oberta fins al 16/11/2026 a les 14:00</li>
<li>Cupons de programes europeus: oberta fins al 16/11/2026 a les 14:00</li>
<li>Paràgraf de presentació que no s'ha de comparar</li></ul>
<footer>© 2026 Generalitat</footer></body></html>"""
HTML_2 = HTML_1.replace("Cupons d'estratègia: oberta fins al 16/11/2026 a les 14:00",
                        "Cupons d'estratègia: pressupost exhaurit")


class TestVigilantPagina(unittest.TestCase):
    def test_linies_i_canvis(self):
        linies = vigilancia.pagina_linies(HTML_1)
        self.assertEqual(linies, ["Cupons ACCIÓ a la competitivitat de l'empresa",
                                  "Cupons d'estratègia: oberta fins al 16/11/2026 a les 14:00",
                                  "Cupons de programes europeus: oberta fins al 16/11/2026 a les 14:00"])
        self.assertEqual(vigilancia.pagina_linies(HTML_1, "europeus"),
                         ["Cupons de programes europeus: oberta fins al 16/11/2026 a les 14:00"])
        afegides, tretes = vigilancia.pagina_canvis(linies, vigilancia.pagina_linies(HTML_2))
        self.assertEqual(afegides, ["Cupons d'estratègia: pressupost exhaurit"])
        self.assertEqual(tretes, ["Cupons d'estratègia: oberta fins al 16/11/2026 a les 14:00"])

    def test_primera_revisio_desa_i_la_segona_avisa(self):
        font = Font("accio-cupons", "ACCIÓ – Cupons a la competitivitat de l'empresa", "catalunya",
                    "https://exemple.invalid/cupons", "web", "diaria", vigilant="pagina")
        caiguda = Font("caiguda", "Font caiguda", "catalunya", "https://exemple.invalid/x", "web", "diaria",
                       vigilant="pagina")

        def get(url):
            if url.endswith("/x"):
                raise OSError("sense connexió")
            return pagines.pop(0).encode()

        with tempfile.TemporaryDirectory() as d:
            estat = Path(d) / "pagines.json"
            pagines = [HTML_1, HTML_2, HTML_2]
            with mock.patch.object(vigilancia, "_get", side_effect=get):
                t, errors = vigilancia.pagines([font, caiguda], estat, AVUI)
                self.assertEqual((t, list(errors)), ([], ["pagina.caiguda"]))
                [t], _ = vigilancia.pagines([font], estat, AVUI)
                self.assertIn("pressupost exhaurit", t.titol)
                self.assertIn("ACCIÓ", t.paraules)
                self.assertTrue(t.id.startswith("pagina:accio-cupons:"))
                self.assertEqual(vigilancia.pagines([font], estat, AVUI)[0], [])  # sense canvis
            self.assertIn("accio-cupons", json.loads(estat.read_text(encoding="utf-8")))

    def test_executa_inclou_les_pagines_un_cop(self):
        font = Font("accio-cupons", "ACCIÓ – Cupons", "catalunya", "https://exemple.invalid/c", "web", "diaria",
                    vigilant="pagina")
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(vigilancia, "bdns", return_value=[]), \
                mock.patch.object(vigilancia, "sedia", return_value=[]), \
                mock.patch.object(vigilancia, "_get", side_effect=[HTML_1.encode(), HTML_2.encode(), HTML_2.encode()]):
            vistos = Path(d) / "vistos.json"
            self.assertEqual(vigilancia.executa({}, [], vistos, [font])[0], [])
            [t] = vigilancia.executa({}, [], vistos, [font])[0]
            self.assertEqual(t.font, "Pàgines oficials")
            self.assertTrue((Path(d) / "pagines.json").exists())

    def test_fonts_del_cataleg(self):
        fonts = {f.id: f for f in dades.carrega().fonts if f.vigilant == "pagina"}
        self.assertIn("accio-cupons", fonts)
        self.assertEqual(fonts["accio-llistat"].filtre, "cup[oó]")


class TestPla(unittest.TestCase):
    def test_bloc_de_seguiment(self):
        cat = dades.carrega()
        p = pla.construeix(cat, AVUI, dt.date(2026, 11, 1), dt.date(2027, 6, 30))
        ids_taules = {e.c.id for e in p.projectes + p.creixement + p.ara + p.vigilar}
        self.assertFalse(ids_taules & CUPONS)  # no es repeteixen a les taules
        [(programa, modalitats)] = p.seguiment
        self.assertEqual(len(modalitats), 6)
        self.assertEqual(pla.resum(p)["seguiment_obertes"], 4)
        terminis = [f for f in p.fites() if f.data == dt.date(2026, 11, 16) and f.c.id in CUPONS]
        self.assertEqual(len(terminis), 1)  # una sola fita per al programa
        self.assertIn("protecció de la innovació", terminis[0].titol)
        md = pla.markdown(p)
        self.assertIn("## En seguiment: Cupons ACCIÓ a la competitivitat de l'empresa", md)
        self.assertLess(md.index("En seguiment"), md.index("## 1."))
        self.assertIn("/seguiment", pla.informe_html(p, app=True))
        self.assertNotIn("/seguiment", pla.informe_html(p))


if __name__ == "__main__":
    unittest.main()
