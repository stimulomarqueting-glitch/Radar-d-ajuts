"""Tests del radar. Executa: python -m unittest discover -s tests"""

import datetime as dt
import unittest
from pathlib import Path

from radar import calendari, dades, excel, ics, vigilancia
from radar.dades import Calendari, Convocatoria, Perfil
from radar.puntuacio import puntua
from radar.zones import Zones

ARREL = Path(__file__).resolve().parent.parent
AVUI = dt.date(2026, 10, 6)

ZONES = Zones({
    "INT": {"nom": "Internacional", "pare": None},
    "EU": {"nom": "UE", "pare": "INT"},
    "ES": {"nom": "Espanya", "pare": "EU"},
    "ES-CT": {"nom": "Catalunya", "pare": "ES"},
    "ES-CT-B": {"nom": "Barcelona", "pare": "ES-CT"},
    "ES-AN": {"nom": "Andalusia", "pare": "ES"},
})


def conv(**kw) -> Convocatoria:
    base = dict(id="x", nom="X", entitat="E", nivell="catalunya", origen="public", instrument="subvencio",
                descripcio="", zones=["ES-CT"], ambit_geografic="", beneficiaris=["pime", "gran_empresa"],
                focus=["prova_concepte"], rols_stimulo=["proveidor_extern"], calendari=Calendari())
    base.update(kw)
    return Convocatoria(**base)


def perfil(**kw) -> Perfil:
    base = dict(id="p", nom="P", tipus="client", zona="ES-CT-B", beneficiari_com=["gran_empresa"],
                rols=["beneficiari", "soci"], focus={"prova_concepte": 3, "industria": 3}, trl=(4, 9))
    base.update(kw)
    return Perfil(**base)


class TestZones(unittest.TestCase):
    def test_elegibilitat_jerarquica(self):
        self.assertTrue(ZONES.es_elegible("ES-CT-B", ["ES-CT"]))
        self.assertTrue(ZONES.es_elegible("ES-CT-B", ["EU"]))
        self.assertFalse(ZONES.es_elegible("ES-AN", ["ES-CT"]))
        self.assertFalse(ZONES.es_elegible("ES-CT", ["ES-CT-B"]))  # una zona més àmplia no hi cap

    def test_cicle_detectat(self):
        z = Zones({"A": {"pare": "B"}, "B": {"pare": "A"}})
        with self.assertRaises(ValueError):
            z.avantpassats("A")


class TestCalendari(unittest.TestCase):
    def test_anual_tancada_estima_propera_edicio(self):
        # Cas DOGA: Exploració tecnològica 2026 va tancar el 21/09/2026
        c = conv(calendari=Calendari(recurrencia="anual", estat="tancada",
                                     obertura=dt.date(2026, 7, 29), tancament=dt.date(2026, 9, 21)))
        f = calendari.propera_finestra(c, AVUI)
        self.assertEqual(f.estat, "propera")
        self.assertTrue(f.estimada)
        self.assertEqual(f.obertura, dt.date(2027, 7, 29))
        self.assertEqual(f.tancament, dt.date(2027, 9, 21))
        tipus = [(s.tipus, s.data) for s in calendari.senyals(c, AVUI)]
        self.assertIn(("preparar", dt.date(2027, 5, 30)), tipus)  # 60 dies abans
        self.assertIn(("vigilar", dt.date(2027, 7, 15)), tipus)  # 14 dies abans
        self.assertIn(("tancament", dt.date(2027, 9, 21)), tipus)

    def test_finestra_oberta_confirmada(self):
        c = conv(calendari=Calendari(recurrencia="anual", obertura=dt.date(2026, 9, 30),
                                     tancament=dt.date(2026, 10, 26)))
        f = calendari.propera_finestra(c, AVUI)
        self.assertEqual((f.estat, f.estimada), ("oberta", False))

    def test_estimacio_salta_anys(self):
        c = conv(calendari=Calendari(recurrencia="anual", obertura=dt.date(2024, 5, 7),
                                     tancament=dt.date(2024, 6, 12)))
        f = calendari.propera_finestra(c, AVUI)
        self.assertEqual(f.obertura, dt.date(2027, 5, 7))

    def test_nomes_tancament_i_mes_obertura(self):
        c = conv(calendari=Calendari(recurrencia="anual", tancament=dt.date(2025, 7, 22), mes_obertura_habitual=5))
        f = calendari.propera_finestra(c, AVUI)
        self.assertEqual((f.obertura, f.tancament), (dt.date(2027, 5, 1), dt.date(2027, 7, 22)))

    def test_multiples_talls(self):
        c = conv(calendari=Calendari(recurrencia="multiples_talls",
                                     talls=[dt.date(2026, 9, 2), dt.date(2026, 11, 4), dt.date(2027, 2, 3)]))
        f = calendari.propera_finestra(c, AVUI)
        self.assertEqual((f.estat, f.tancament), ("oberta", dt.date(2026, 11, 4)))

    def test_talls_amb_obertura_futura_es_propera(self):
        c = conv(calendari=Calendari(recurrencia="multiples_talls", obertura=dt.date(2026, 12, 17),
                                     talls=[dt.date(2027, 3, 4)]))
        self.assertEqual(calendari.propera_finestra(c, AVUI).estat, "propera")

    def test_permanent_sense_alertes_de_dates(self):
        c = conv(calendari=Calendari(recurrencia="continua", estat="permanent"))
        self.assertEqual(calendari.propera_finestra(c, AVUI).estat, "permanent")
        self.assertEqual(calendari.senyals(c, AVUI), [])

    def test_anunciada_sense_dates_i_revisio(self):
        c = conv(calendari=Calendari(recurrencia="puntual", estat="prevista", revisar=dt.date(2026, 10, 8)))
        self.assertEqual(calendari.propera_finestra(c, AVUI).estat, "propera")
        self.assertEqual([s.tipus for s in calendari.senyals(c, AVUI)], ["vigilar"])


class TestPuntuacio(unittest.TestCase):
    def test_client_gran_empresa_beneficiari(self):
        e = puntua(conv(), perfil(), ZONES)
        self.assertEqual(e.rol, "beneficiari")
        self.assertTrue(e.elegible)

    def test_fora_de_zona_sense_rol_indirecte(self):
        e = puntua(conv(zones=["ES-AN"]), perfil(), ZONES)
        self.assertEqual(e.prioritat, "NE")

    def test_agencia_entra_com_a_proveidor_fora_de_zona(self):
        agencia = perfil(tipus="agencia", beneficiari_com=["pime"], rols=["beneficiari", "proveidor_extern"])
        e = puntua(conv(zones=["ES-AN"]), agencia, ZONES)
        self.assertEqual(e.rol, "proveidor_extern")
        self.assertNotEqual(e.prioritat, "NE")

    def test_agencia_pime_no_es_beneficiaria_si_la_fitxa_no_ho_preveu(self):
        agencia = perfil(tipus="agencia", beneficiari_com=["pime"], rols=["beneficiari", "proveidor_extern"])
        e = puntua(conv(beneficiaris=["pime", "startup"], rols_stimulo=["proveidor_extern"]), agencia, ZONES)
        self.assertEqual(e.rol, "proveidor_extern")

    def test_rang_puntuacio(self):
        e = puntua(conv(import_max_eur=30000, trl=(3, 6)), perfil(), ZONES)
        self.assertTrue(0 <= e.punts <= 100)


class TestExcel(unittest.TestCase):
    def test_repara_trl_convertit_en_data(self):
        self.assertEqual(excel.repara_trl(dt.datetime(2026, 7, 3)), "3–7")
        self.assertEqual(excel.trl_rang("3–7"), [3, 7])
        self.assertEqual(excel.trl_rang("8 o més"), [8, 9])
        self.assertIsNone(excel.trl_rang("Variable"))

    def test_dates_terminis(self):
        self.assertEqual(excel.dates("Convo 2025: 10/05/2025 – 21/07/2025"), ["2025-05-10", "2025-07-21"])

    def test_importa_excel_original(self):
        files = excel.llegeix(ARREL / "data" / "origen" / "2025_Recull_ajuts_publics.xlsx")
        self.assertEqual(len(files), 29)
        self.assertEqual({f["nivell"] for f in files}, {"catalunya", "estat", "europa"})
        pendents = excel.compara(files, ARREL / "data" / "convocatories.yaml")
        self.assertEqual(pendents, [], "Totes les files de l'Excel han de tenir fitxa al catàleg")


class TestCataleg(unittest.TestCase):
    def test_cataleg_valid(self):
        cat = dades.carrega()
        self.assertGreater(len(cat.convocatories), 50)
        self.assertIn("doga", cat.perfils)

    def test_ics_valid(self):
        cat = dades.carrega()
        agenda = calendari.agenda(cat.convocatories, AVUI, 120)
        text = ics.genera(agenda, dt.datetime(2026, 10, 6, 6, 0))
        self.assertTrue(text.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertEqual(text.count("BEGIN:VEVENT"), len(agenda))
        for linia in text.split("\r\n"):
            self.assertLessEqual(len(linia.encode("utf-8")), 75)


class TestVigilancia(unittest.TestCase):
    PARAULES = ["prueba de concepto", "robótica", "dual use"]

    def test_coincidencies_sense_accents(self):
        self.assertEqual(vigilancia.coincidencies("Ayudas a la ROBOTICA colaborativa", self.PARAULES), ["robótica"])

    def test_bdns_parse(self):
        payload = {"content": [
            {"numeroConvocatoria": 900001, "descripcion": "Ayudas para pruebas de concepto en robótica",
             "nivel1": "AUTONOMICA", "nivel2": "CATALUÑA", "nivel3": "ACCIÓ", "fechaRecepcion": "2026-10-05"},
            {"numeroConvocatoria": 900002, "descripcion": "Subvenciones a fiestas mayores", "nivel1": "LOCAL"},
        ]}
        t = vigilancia.bdns_parse(payload, self.PARAULES)
        self.assertEqual(len(t), 1)
        self.assertEqual(t[0].id, "bdns-900001")

    def test_sedia_parse(self):
        payload = {"results": [{"metadata": {"identifier": ["HORIZON-EIC-2027-X"], "title": ["Dual use robotics"],
                                             "status": ["31094502"], "deadlineDate": ["2027-02-03T17:00:00"]}}]}
        t = vigilancia.sedia_parse(payload, self.PARAULES)
        self.assertEqual(t[0].termini, "2027-02-03 (propera)")

    def test_placsp_parse(self):
        xml = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>urn:1</id>
          <title>Servicio de prueba de concepto de robótica asistencial</title>
          <summary>Importe: 100000 EUR</summary><updated>2026-10-05T10:00:00Z</updated>
          <link href="https://contrataciondelestado.es/x"/>
          <ItemClassificationCode xmlns="urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2">73100000</ItemClassificationCode>
          </entry></feed>""".encode("utf-8")
        t = vigilancia.placsp_parse(xml, self.PARAULES, ["73100"])
        self.assertEqual(len(t), 1)
        self.assertIn("CPV", t[0].paraules)


if __name__ == "__main__":
    unittest.main()
