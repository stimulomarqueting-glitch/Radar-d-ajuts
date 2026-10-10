"""Tests dels socis de Holded i de l'avís per correu. Contactes ficticis (cap dada real)."""

import datetime as dt
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from radar import avisos, dades, holded, socis
from radar.dades import Calendari, Convocatoria
from radar.zones import Zones

AVUI = dt.date(2026, 10, 6)
ZONES = Zones({
    "INT": {"nom": "Internacional", "pare": None}, "EU": {"nom": "UE", "pare": "INT"},
    "ES": {"nom": "Espanya", "pare": "EU"}, "ES-CT": {"nom": "Catalunya", "pare": "ES"},
    "ES-CT-B": {"nom": "Barcelona", "pare": "ES-CT"}, "ES-AN": {"nom": "Andalusia", "pare": "ES"},
    "ES-MD": {"nom": "Madrid", "pare": "ES"},
})

CONTACTES = [
    # Empresa amb adreça de facturació + persona del mateix domini (format del connector)
    {"id": "1", "nom": "MOTORS EXEMPLE, SA", "nomComercial": None, "tipus": "client",
     "email": "facturas@motors-exemple.es", "telefon": "931234567", "nif": "A00000000"},
    {"id": "2", "nom": "Anna Puig Serra", "nomComercial": None, "tipus": "client",
     "email": "anna.puig@motors-exemple.es", "telefon": None, "nif": ""},
    # Centre de recerca (format de l'API de Holded)
    {"id": "3", "name": "FUNDACIO INSTITUT DE RECERCA EXEMPLE", "tradeName": "IRE", "type": "lead",
     "email": "transfer@ire.example.org", "code": "G00000000", "billAddress": {"province": "Barcelona"},
     "tags": ["radar-salut", "radar-dispositius_medics"],
     "contactPersons": [{"name": "Joan Mas", "email": "joan.mas@ire.example.org", "job": "Transferència"}]},
    # Lead individual de formulari web: s'ha d'ignorar
    {"id": "4", "nom": "name", "nomComercial": None, "tipus": "lead", "email": "algu@gmail.com",
     "telefon": "+34600000000", "nif": "999"},
    # Empresa andalusa
    {"id": "5", "nom": "AGRO SUR EXEMPLE SL", "nomComercial": None, "tipus": "lead",
     "email": "sur@agrosur.example.es", "telefon": "955000000", "nif": "B00000000"},
    # Inversor
    {"id": "6", "nom": "CAPITAL EXEMPLE VENTURES SL", "nomComercial": None, "tipus": "lead",
     "email": "deals@capitalexemple.example", "telefon": "915000000", "nif": "B11111111"},
]
CLASSIFICACIO = [
    {"domini": "motors-exemple.es", "nom_visible": "Motors Exemple", "tipus": "empresa", "zona": "ES-CT-B",
     "focus": ["automocio", "industria", "prova_concepte"]},
    {"nom": "AGRO SUR", "tipus": "empresa", "focus": ["agrotech", "prova_concepte"]},
]


def conv(**kw) -> Convocatoria:
    base = dict(id="x", nom="Prova", entitat="ACCIÓ", nivell="catalunya", origen="public", instrument="subvencio",
                descripcio="Proves de concepte industrials.", zones=["ES-CT"], ambit_geografic="Empreses a Catalunya",
                beneficiaris=["pime", "gran_empresa"], focus=["prova_concepte", "industria"],
                rols_stimulo=["proveidor_extern", "beneficiari"],
                calendari=Calendari(recurrencia="anual", obertura=dt.date(2026, 9, 30), tancament=dt.date(2026, 11, 20)),
                url="https://exemple.cat", ajuda_text="75 %, màxim 30.000 €", import_max_eur=30000, intensitat_max=75)
    base.update(kw)
    return Convocatoria(**base)


def llista_socis():
    return socis.construeix([holded.normalitza(c) for c in CONTACTES], CLASSIFICACIO)


class TestHolded(unittest.TestCase):
    def test_normalitza_dos_formats(self):
        a = holded.normalitza(CONTACTES[0])
        b = holded.normalitza(CONTACTES[2])
        self.assertEqual((a.nom, a.tipus, a.domini), ("MOTORS EXEMPLE, SA", "client", "motors-exemple.es"))
        self.assertEqual((b.nom_comercial, b.provincia, b.tags[0]), ("IRE", "Barcelona", "radar-salut"))
        self.assertEqual(b.persones[0]["email"], "joan.mas@ire.example.org")

    def test_zona(self):
        self.assertEqual(holded.zona(holded.normalitza(CONTACTES[2])), "ES-CT-B")  # per província
        self.assertEqual(holded.zona(holded.normalitza(CONTACTES[4])), "ES-AN")  # per prefix 955
        estranger = holded.normalitza({"id": "9", "nom": "X SRL", "nif": "IT02964080424"})
        self.assertEqual(holded.zona(estranger), "IT")


class TestSocis(unittest.TestCase):
    def test_agrupa_i_tria_persona(self):
        ss = {s.nom: s for s in llista_socis()}
        self.assertNotIn("name", ss)  # lead individual ignorat
        motors = ss["Motors Exemple"]
        self.assertEqual(motors.destinatari["email"], "anna.puig@motors-exemple.es")
        self.assertIn("facturas@motors-exemple.es", motors.emails_generics)
        self.assertEqual(ss["IRE"].tipus, "recerca")
        self.assertIn("dispositius_medics", ss["IRE"].focus)  # etiquetes radar- de Holded
        self.assertEqual(ss["CAPITAL EXEMPLE VENTURES SL"].tipus, "inversor")

    def test_generics_i_noms(self):
        self.assertTrue(socis._es_generic("motorsexemple@motorsexemple.es"))
        self.assertTrue(socis._es_generic("facturas.proveedores@motors-exemple.es"))
        self.assertFalse(socis._es_generic("anna.puig@motors-exemple.es"))
        self.assertEqual(socis.nom_des_del_correu("anna.puig@exemple.com"), "Anna")

    def test_exclou(self):
        ss = socis.construeix([holded.normalitza(c) for c in CONTACTES],
                              CLASSIFICACIO + [{"domini": "capitalexemple.example", "exclou": True}])
        self.assertNotIn("CAPITAL EXEMPLE VENTURES SL", {s.nom for s in ss})

    def test_proposa_empresa_elegible_per_zona(self):
        propostes = socis.proposa(conv(), llista_socis(), ZONES)
        noms = [p.soci.nom for p in propostes]
        self.assertIn("Motors Exemple", noms)
        self.assertNotIn("AGRO SUR EXEMPLE SL", noms)  # Andalusia no és elegible a ACCIÓ
        self.assertTrue(propostes[0].rol.startswith("sol·licitant"))

    def test_proposa_recerca_quan_el_beneficiari_es_un_centre(self):
        c = conv(beneficiaris=["universitat", "centre_recerca", "hospital"], zones=["ES"],
                 focus=["salut", "dispositius_medics", "transferencia"], rols_stimulo=["proveidor_extern"])
        propostes = socis.proposa(c, llista_socis(), ZONES)
        self.assertEqual(propostes[0].soci.nom, "IRE")


class TestAvisos(unittest.TestCase):
    def setUp(self):
        self.cat = dades.carrega()

    def test_nomes_linies_noves(self):
        linies = avisos.candidates(self.cat, AVUI, self.cat.config.get("avisos"))
        self.assertTrue(linies)
        # Prioritat A o B, o bé línies per compartir amb clients (p. ex. els Cupons ACCIÓ)
        self.assertTrue(all(l.e.prioritat in ("A", "B") or l.c.compartir_clients for l in linies))
        estat = {linies[0].clau: "2026-10-01"}
        self.assertNotIn(linies[0].clau, [l.clau for l in avisos.noves(linies, estat)])

    def test_clau_per_edicio(self):
        c = self.cat.per_id("accio-exploracio-tecnologica")
        f = avisos.calendari.propera_finestra(c, AVUI)
        self.assertEqual(avisos.clau_edicio(c, f, AVUI), "accio-exploracio-tecnologica|2027")

    def test_correu_amb_els_camps_demanats(self):
        c = conv()
        f = avisos.calendari.propera_finestra(c, AVUI)
        e = avisos.puntua(c, self.cat.perfils["stimulo"], self.cat.zones)
        l = avisos.Linia(c, f, e, "x|2026", "Oberta ara")
        l.propostes = socis.proposa(c, llista_socis(), ZONES)
        assumpte, text, cos_html = avisos.compon([l], AVUI)
        for camp in ("Inici", "Finalització", "Ajut", "Descripció", "Per què encaixem", "Socis potencials",
                     "ESBORRANYS DE CORREU"):
            self.assertIn(camp, text)
        self.assertIn("Motors Exemple", text)
        self.assertIn("mailto:anna.puig%40motors-exemple.es", cos_html)
        self.assertIn("1 línia nova", assumpte)

    def test_esborrany_en_catala_i_castella(self):
        c = conv(zones=["ES"])
        f = avisos.calendari.propera_finestra(c, AVUI)
        l = avisos.Linia(c, f, None, "x", "Oberta ara")
        ss = {s.nom: s for s in llista_socis()}
        ca = avisos.esborrany(l, socis.Proposta(ss["Motors Exemple"], 5, "sol·licitant (Stimulo com a proveïdor)", []), "Xavi")
        es = avisos.esborrany(l, socis.Proposta(ss["AGRO SUR EXEMPLE SL"], 5, "soci de consorci", []), "Xavi")
        self.assertTrue(ca["cos"].startswith("Hola Anna,"))
        self.assertEqual((ca["idioma"], es["idioma"]), ("ca", "es"))
        self.assertIn("Te escribo", es["cos"])

    def test_estat_i_enviament(self):
        with tempfile.TemporaryDirectory() as tmp:
            fitxer = Path(tmp) / "notificades.json"
            c = conv()
            l = avisos.Linia(c, avisos.calendari.propera_finestra(c, AVUI), None, "x|2026", "")
            avisos.desa_estat(fitxer, {}, [l], AVUI)
            self.assertEqual(avisos.llegeix_estat(fitxer), {"x|2026": "2026-10-06"})
        entorn = {"SMTP_HOST": "smtp.exemple", "SMTP_USER": "radar@exemple", "SMTP_PASSWORD": "x",
                  "RADAR_DESTINATARI": "xavi@exemple, altre@exemple"}
        with mock.patch.dict(os.environ, entorn), mock.patch("smtplib.SMTP") as smtp:
            self.assertTrue(avisos.smtp_configurat())
            dest = avisos.envia("Assumpte", "text", "<p>html</p>")
            enviat = smtp.return_value.__enter__.return_value.send_message.call_args[0][0]
        self.assertEqual(dest, ["xavi@exemple", "altre@exemple"])
        self.assertEqual(enviat["To"], "xavi@exemple, altre@exemple")


if __name__ == "__main__":
    unittest.main()
