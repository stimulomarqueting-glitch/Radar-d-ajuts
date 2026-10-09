"""Tests de les dues línies de treball (projectes amb clients i creixement de Stimulo) i del pla per horitzó."""

import dataclasses
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from radar import avisos, dades, pla
from radar.dades import Calendari

AVUI = dt.date(2026, 10, 9)
INICI, FI = dt.date(2026, 11, 1), dt.date(2027, 6, 30)


class TestLinies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = dades.carrega()

    def test_totes_les_fitxes_declaren_linies_valides(self):
        for c in self.cat.convocatories:
            self.assertTrue(set(c.linies) <= set(dades.LINIES), c.id)
        projectes = sum("projectes" in c.linies for c in self.cat.convocatories)
        creixement = sum("creixement" in c.linies for c in self.cat.convocatories)
        self.assertGreater(projectes, creixement)  # la línia amb més retorn és la més poblada

    def test_linies_per_defecte(self):
        self.assertEqual(dades.linies_per_defecte({"rols_stimulo": ["proveidor_extern"]}), ["projectes"])
        self.assertEqual(dades.linies_per_defecte({"rols_stimulo": ["beneficiari"], "beneficiaris": ["pime"]}),
                         ["creixement"])
        self.assertEqual(dades.linies_per_defecte({"rols_stimulo": ["beneficiari", "soci"], "beneficiaris": ["pime"]}),
                         ["projectes", "creixement"])
        self.assertEqual(dades.linies_per_defecte({"instrument": "licitacio"}), ["projectes"])
        self.assertEqual(dades.linies_per_defecte({"rols_stimulo": ["beneficiari"], "beneficiaris": ["gran_empresa"]}),
                         [])

    def test_exemples_del_cataleg(self):
        self.assertEqual(self.cat.per_id("eic-accelerator").linies, ["projectes"])
        self.assertIn("creixement", self.cat.per_id("accio-cupons").linies)
        self.assertIn("projectes", self.cat.per_id("accio-noves-oportunitats-negoci").linies)


class TestRetorn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = dades.carrega()

    def conv(self, **canvis):
        return dataclasses.replace(self.cat.per_id("accio-nuclis-rd"), retorn_eur=None, **canvis)

    def test_quota_segons_el_rol(self):
        r = pla.retorn(self.conv(rols_stimulo=["proveidor_extern"], import_max_eur=60_000, intensitat_max=60,
                                 pressupost_min_eur=None))
        # projecte de 33 k€ a 100 k€; proveïdor 30–60 %
        self.assertEqual((r.rol, round(r.minim), round(r.maxim)), ("proveidor_extern", 10_000, 60_000))
        self.assertEqual(r.nivell, "mitjà")

    def test_sostre_i_minim_no_supera_el_maxim(self):
        r = pla.retorn(self.conv(rols_stimulo=["proveidor_extern"], import_max_eur=2_500_000, intensitat_max=70,
                                 pressupost_min_eur=None))
        self.assertEqual(r.maxim, pla.SOSTRE_ROL["proveidor_extern"])
        self.assertIn("màxim", r.suposit)
        r = pla.retorn(self.conv(rols_stimulo=["proveidor_extern"], import_max_eur=40_000, intensitat_max=30,
                                 pressupost_min_eur=200_000))
        self.assertLessEqual(r.minim, r.maxim)

    def test_casos_sense_import(self):
        europeu = pla.retorn(self.conv(rols_stimulo=["soci"], import_max_eur=None, pressupost_min_eur=None,
                                       nivell="europa", beneficiaris=["consorci", "pime"]))
        self.assertIn("consorci típic", europeu.suposit)
        self.assertIsNone(pla.retorn(self.conv(rols_stimulo=["beneficiari"])))
        fixat = pla.retorn(self.cat.per_id("licitacions-disseny-rd"))
        self.assertEqual((fixat.minim, fixat.maxim, fixat.suposit), (15_000, 150_000, "fixat a la fitxa"))


class TestHoritzo(unittest.TestCase):
    def test_temporada_de_novembre_a_juny(self):
        self.assertEqual(pla.horitzo(AVUI), (INICI, FI))
        self.assertEqual(pla.horitzo(dt.date(2026, 12, 3)), (dt.date(2026, 12, 3), FI))
        self.assertEqual(pla.horitzo(dt.date(2027, 3, 1)), (dt.date(2027, 3, 1), FI))
        self.assertEqual(pla.horitzo(dt.date(2027, 7, 1)), (dt.date(2027, 11, 1), dt.date(2028, 6, 30)))


class TestPla(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = dades.carrega()
        base = cls.cat.per_id("accio-nuclis-rd")
        cal = lambda **k: Calendari(recurrencia="puntual", **k)  # noqa: E731
        sintetiques = [
            # Les dues línies, oberta i tanca dins de l'horitzó
            dataclasses.replace(base, id="t-dues", nom="Prova dues línies", linies=["projectes", "creixement"],
                                calendari=cal(estat="oberta", tancament=dt.date(2026, 12, 10))),
            # Tanca abans de començar l'horitzó: «ara mateix»
            dataclasses.replace(base, id="t-abans", nom="Prova abans", linies=["projectes"],
                                calendari=cal(estat="oberta", tancament=dt.date(2026, 10, 25))),
            # Anunciada sense dates, a les dues línies: una sola entrada a vigilar
            dataclasses.replace(base, id="t-anunciada", nom="Prova anunciada", linies=["projectes", "creixement"],
                                calendari=cal(estat="prevista")),
            # Obre després de l'horitzó però la prospecció hi cau dins (90 dies abans)
            dataclasses.replace(base, id="t-juliol", nom="Prova juliol", linies=["projectes", "creixement"],
                                calendari=cal(estat="prevista", obertura=dt.date(2027, 8, 15),
                                              tancament=dt.date(2027, 9, 30))),
            # Sense línia: fora del pla
            dataclasses.replace(base, id="t-cap", nom="Prova sense línia", linies=[],
                                calendari=cal(estat="oberta", tancament=dt.date(2027, 1, 20))),
        ]
        cls.cat_prova = dataclasses.replace(cls.cat, convocatories=cls.cat.convocatories + sintetiques)
        cls.pla = pla.construeix(cls.cat_prova, AVUI, INICI, FI)

    def ids(self, entrades):
        return [e.c.id for e in entrades]

    def test_seccions(self):
        p = self.pla
        self.assertIn("t-dues", self.ids(p.projectes))
        self.assertIn("t-abans", self.ids(p.ara))
        self.assertNotIn("t-abans", self.ids(p.projectes))
        self.assertEqual(self.ids(p.vigilar).count("t-anunciada"), 1)
        self.assertIn("t-juliol", self.ids(p.projectes))  # prospecció a partir del 17/05/2027
        self.assertNotIn("t-juliol", self.ids(p.creixement))  # preparar (45 dies) cau fora de l'horitzó
        totes = p.projectes + p.creixement + p.vigilar + p.ara
        self.assertNotIn("t-cap", self.ids(totes))

    def test_projectes_per_retorn_i_creixement_nomes_a_b(self):
        mitjos = [e.retorn.mig if e.retorn else 0 for e in self.pla.projectes]
        self.assertEqual(mitjos, sorted(mitjos, reverse=True))
        self.assertTrue(all(e.e.prioritat in ("A", "B") for e in self.pla.creixement))

    def test_fites_sense_repetir_i_permanents_sense_calendari(self):
        fites = [f for f in self.pla.fites() if f.c.id == "t-dues"]
        terminis = [f for f in fites if f.tipus == "termini"]
        self.assertEqual(len(terminis), 1)  # dues línies, un sol termini
        self.assertEqual({f.linia for f in fites if f.tipus in ("prospectar", "preparar")}, {"projectes", "creixement"})
        for e in self.pla.permanents():
            self.assertEqual(e.f.estat, "permanent")
            self.assertEqual(e.fites, [])
        self.assertTrue(all(f.data >= AVUI for f in self.pla.fites()))

    def test_comencar_ja(self):
        ja = self.ids(self.pla.comencar_ja())
        self.assertIn("t-dues", ja)  # tanca el 10/12: calia prospectar des del 26/09
        self.assertNotIn("t-abans", ja)  # ja surt a «ara mateix»
        self.assertNotIn("t-juliol", ja)
        self.assertEqual(len(ja), len(set(ja)))
        for _mes, fites in pla.mesos(self.pla):
            self.assertFalse(any(f.ja for f in fites))

    def test_sortides(self):
        md = pla.markdown(self.pla)
        self.assertIn("## 1. Projectes de producte amb clients i consorcis", md)
        self.assertLess(md.index("## 1."), md.index("## 2."))
        cos = pla.informe_html(self.pla)
        self.assertNotIn("<script", cos)
        self.assertNotIn("/expedients/nou", cos)
        self.assertIn("/expedients/nou?convocatoria=", pla.informe_html(self.pla, app=True))
        with tempfile.TemporaryDirectory() as d:
            fitxers = pla.genera(self.pla, Path(d))
            self.assertEqual(fitxers["html"].name, "pla-2026-2027.html")
            self.assertTrue(fitxers["html"].read_text(encoding="utf-8").startswith("<!doctype html>"))
            self.assertEqual(pla.genera(self.pla, Path(d), privat=True)["md"].name, "pla-2026-2027-clients.md")

    def test_cataleg_real(self):
        p = pla.construeix(self.cat, AVUI, INICI, FI)
        r = pla.resum(p)
        self.assertGreater(r["projectes"], r["creixement"])
        self.assertGreater(r["alt"], 0)
        ids = self.ids(p.projectes)
        self.assertIn("he-cl4-made-in-europe-2027", ids)
        self.assertIn("eic-step-defence-scaleup", self.ids(p.ara))  # tanca el 28/10/2026


class TestCorreuPerLinies(unittest.TestCase):
    def test_projectes_primer_i_capcaleres(self):
        cat = dades.carrega()
        cfg = {**avisos.CONFIG_PER_DEFECTE, **cat.config.get("avisos", {})}
        linies = avisos.candidates(cat, AVUI, cfg)
        ordre = [{"projectes": 0, "creixement": 1, "": 2}[l.linia] for l in linies]
        self.assertEqual(ordre, sorted(ordre))
        mostra = [l for l in linies if l.linia == "projectes"][:2] + [l for l in linies if l.linia == "creixement"][:1]
        _assumpte, text, cos = avisos.compon(mostra, AVUI, cfg)
        self.assertLess(text.index("LÍNIA 1"), text.index("LÍNIA 2"))
        self.assertIn("Línia 1 · Projectes amb clients i consorcis", cos)
        if any(l.retorn for l in mostra):
            self.assertIn("retorn per projecte", text)

    def test_reserva_per_a_creixement(self):
        cat = dades.carrega()
        cfg = {**avisos.CONFIG_PER_DEFECTE, **cat.config.get("avisos", {})}
        linies = avisos.candidates(cat, AVUI, cfg)
        principals, resum = avisos.reparteix(linies, 8)
        self.assertEqual(len(principals), 8)
        self.assertEqual(len(principals) + len(resum), len(linies))
        self.assertEqual([l.linia for l in principals].count("creixement"), 2)
        self.assertEqual(principals[0].linia, "projectes")
        ordre = [linies.index(l) for l in principals]
        self.assertEqual(ordre, sorted(ordre))
        self.assertEqual(avisos.reparteix(linies[:3], 8), (linies[:3], []))


if __name__ == "__main__":
    unittest.main()
