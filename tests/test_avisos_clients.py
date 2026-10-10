"""Tests dels avisos per compartir amb clients i del vigilant d'ACCIÓ al BDNS."""

import datetime as dt
import unittest

from radar import avisos, calendari, dades, screening, vigilancia

AVUI = dt.date(2026, 10, 10)


class TestAvisosPerAClients(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = dades.carrega()
        cls.cfg = {**avisos.CONFIG_PER_DEFECTE, **cls.cat.config.get("avisos", {})}
        cls.clients = list(screening.carrega_clients(cls.cat).values())

    def test_linia_marcada_entra_encara_que_no_sigui_prioritaria(self):
        linies = {l.c.id: l for l in avisos.candidates(self.cat, AVUI, self.cfg)}
        self.assertTrue(linies["accio-cupons-proteccio"].per_clients)
        self.assertFalse(linies["eic-accelerator"].per_clients)

    def test_clients_de_servei(self):
        sense = {l.c.id for l in avisos.candidates(self.cat, AVUI, self.cfg)}
        amb = {l.c.id: l for l in avisos.candidates(self.cat, AVUI, self.cfg, self.clients)}
        noves = set(amb) - sense
        self.assertTrue(noves)  # línies que només entren pels clients de servei (DOGA)
        for id_ in noves:
            self.assertTrue(any(x.startswith("DOGA") for x in amb[id_].clients_servei))

    def test_noves_oportunitats_de_negoci(self):
        c = self.cat.per_id("accio-noves-oportunitats-negoci")
        self.assertTrue(c.compartir_clients)
        self.assertIn("gran_empresa", c.beneficiaris)
        f = calendari.propera_finestra(c, AVUI)
        self.assertEqual((f.estat, f.obertura, f.estimada), ("propera", dt.date(2027, 6, 15), True))
        ids = {l.c.id for l in avisos.candidates(self.cat, dt.date(2027, 4, 20), self.cfg)}
        self.assertIn("accio-noves-oportunitats-negoci", ids)  # avís ≈ 60 dies abans de l'obertura

    def test_correu(self):
        linies = [l for l in avisos.candidates(self.cat, AVUI, self.cfg, self.clients) if l.per_clients][:2]
        assumpte, text, cos = avisos.compon(linies, AVUI, self.cfg)
        self.assertIn("per compartir amb clients", assumpte)
        self.assertIn("PER COMPARTIR AMB CLIENTS", text)
        self.assertIn("Per compartir amb clients.", cos)


class TestVigilantAccio(unittest.TestCase):
    def test_convocatories_d_accio_sense_paraules_clau(self):
        payload = {"content": [
            {"numeroConvocatoria": 912188, "descripcion": "Subvencions per a projectes de noves oportunitats de negoci",
             "nivel1": "CATALUÑA", "nivel2": "DEPARTAMENT D'EMPRESA I TREBALL",
             "nivel3": "AGÈNCIA PER LA COMPETITIVITAT DE L'EMPRESA (ACCIÓ)"},
            {"numeroConvocatoria": 1, "descripcion": "Ayudas al comercio local", "nivel1": "ESTADO", "nivel2": "X"},
        ]}
        [t] = vigilancia.bdns_parse(payload, ["prototipo"])
        self.assertEqual(t.paraules, ["ACCIÓ"])
        self.assertTrue(t.url.endswith("/912188"))


if __name__ == "__main__":
    unittest.main()
