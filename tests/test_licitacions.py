"""Tests de les licitacions: lectura de fonts (dades de mostra), avaluació, fitxa i finestra de l'aplicació."""

import datetime as dt
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock
from urllib.parse import quote

from fastapi.testclient import TestClient

from radar import avisos, dades, diari, licitacions as L
from radar.web.app import crea_app
from radar.web.db import BaseDades
from tests.test_web import CONTRASENYA, ORIGEN, ClientFals, config

AVUI = dt.date(2026, 10, 6)
CFG = {**L.CONFIG_PER_DEFECTE, "cpv": ["71320000", "73000000", "79930000"],
       "paraules_clau": ["disseny industrial", "prototip"], "exclou": ["obres"]}

CODICE = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:cac="urn:dgpe:names:draft:codice:schema:xsd:CommonAggregateComponents-2"
      xmlns:cbc="urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2"
      xmlns:cac-place-ext="urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonAggregateComponents-2"
      xmlns:cbc-place-ext="urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonBasicComponents-2">
  <entry>
    <id>https://contrataciondelestado.es/sindicacion/licitacion/123</id>
    <title>Servicio de dise\xc3\xb1o industrial de mobiliario urbano</title>
    <link href="https://contrataciondelestado.es/wps/poc?uri=deeplink:detalle_licitacion&amp;idEvl=abc"/>
    <updated>2026-10-05T10:00:00+02:00</updated>
    <cac-place-ext:ContractFolderStatus>
      <cbc:ContractFolderID>EXP-2026/45</cbc:ContractFolderID>
      <cbc-place-ext:ContractFolderStatusCode>PUB</cbc-place-ext:ContractFolderStatusCode>
      <cac-place-ext:LocatedContractingParty><cac:Party><cac:PartyName><cbc:Name>Ajuntament de Terrassa</cbc:Name></cac:PartyName></cac:Party></cac-place-ext:LocatedContractingParty>
      <cac:ProcurementProject>
        <cbc:Name>Servicio de dise\xc3\xb1o industrial de mobiliario urbano</cbc:Name>
        <cbc:TypeCode>2</cbc:TypeCode>
        <cac:BudgetAmount>
          <cbc:EstimatedOverallContractAmount currencyID="EUR">90000</cbc:EstimatedOverallContractAmount>
          <cbc:TaxExclusiveAmount currencyID="EUR">60000</cbc:TaxExclusiveAmount>
        </cac:BudgetAmount>
        <cac:RequiredCommodityClassification><cbc:ItemClassificationCode>71320000</cbc:ItemClassificationCode></cac:RequiredCommodityClassification>
        <cac:RealizedLocation><cbc:CountrySubentityCode>ES511</cbc:CountrySubentityCode></cac:RealizedLocation>
      </cac:ProcurementProject>
      <cac:TenderingProcess>
        <cbc:ProcedureCode>Abierto simplificado</cbc:ProcedureCode>
        <cac:TenderSubmissionDeadlinePeriod><cbc:EndDate>2026-10-30</cbc:EndDate></cac:TenderSubmissionDeadlinePeriod>
      </cac:TenderingProcess>
    </cac-place-ext:ContractFolderStatus>
  </entry>
</feed>"""

COLUMNES = ["id_intern", "codi_expedient", "nom_organ", "denominacio", "tipus_contracte", "procediment",
            "fase_publicacio", "pressupost_licitacio_sense", "valor_estimat_contracte", "data_publicacio_anunci",
            "termini_presentacio_ofertes", "codi_cpv", "enllac_publicacio", "lloc_execucio"]


def lic(**kw) -> L.Licitacio:
    base = dict(id="pscp:1", font="PSCP", titol="Servei de disseny industrial i prototip", organ="Ajuntament",
                cpv=["71320000"], import_eur=60000.0, termini=AVUI + dt.timedelta(days=25),
                procediment="Obert simplificat", fase="Anunci de licitació")
    base.update(kw)
    return L.Licitacio(**base)


class TestFonts(unittest.TestCase):
    def test_placsp_codice(self):
        [l] = L.placsp_parse(CODICE)
        self.assertEqual(l.expedient, "EXP-2026/45")
        self.assertEqual(l.organ, "Ajuntament de Terrassa")
        self.assertEqual(l.import_eur, 60000.0)
        self.assertEqual(l.valor_estimat, 90000.0)
        self.assertEqual(l.termini, dt.date(2026, 10, 30))
        self.assertEqual(l.cpv, ["71320000"])
        self.assertEqual(l.lloc, "ES511")
        self.assertIn("idEvl=abc", l.url)

    def test_pscp_columnes_i_files(self):
        mapa = L.resol_columnes(COLUMNES)
        self.assertEqual(mapa["titol"], "denominacio")
        self.assertEqual(mapa["import"], "pressupost_licitacio_sense")
        self.assertEqual(mapa["termini"], "termini_presentacio_ofertes")
        files = [{"id_intern": "99", "codi_expedient": "X-1", "nom_organ": "Consorci", "denominacio": "Disseny industrial",
                  "pressupost_licitacio_sense": "45.000,50", "data_publicacio_anunci": "2026-10-01T00:00:00.000",
                  "termini_presentacio_ofertes": "2026-10-20T14:00:00.000", "codi_cpv": "79930000-2",
                  "enllac_publicacio": {"url": "https://contractaciopublica.cat/ca/detall-publicacio/1"}}]
        [l] = L.pscp_parse(files, mapa)
        self.assertEqual((l.id, l.import_eur, l.termini, l.cpv), ("pscp:99", 45000.5, dt.date(2026, 10, 20), ["79930000"]))
        self.assertTrue(l.url.startswith("https://contractaciopublica.cat"))

    def test_deduplica_prefereix_pscp(self):
        a = lic(id="placsp:x", font="PLACSP-agregades", expedient="EXP 1", organ="Ajuntament de Vic")
        b = lic(id="pscp:x", font="PSCP", expedient="exp 1", organ="Ajuntament de Vic")
        self.assertEqual([x.font for x in L.deduplica([a, b])], ["PSCP"])

    def test_una_font_caiguda_no_atura_la_resta(self):
        with mock.patch.object(L, "pscp", side_effect=RuntimeError("caiguda")), \
                mock.patch.object(L, "_get", return_value=CODICE), \
                mock.patch.object(L, "ted", return_value=[]):
            totes, errors = L.cerca(CFG, AVUI, ["71320000"], ["ESP"])
        self.assertEqual(len(totes), 1)
        self.assertIn("pscp", errors)


class TestAvaluacio(unittest.TestCase):
    def test_verd_per_a_disseny_amb_temps(self):
        a = L.avalua(lic(), CFG, AVUI)
        self.assertEqual((a.semafor, a.recomanacio), ("verd", "Analitzar"))
        self.assertTrue(a.encaix)

    def test_termini_massa_just(self):
        a = L.avalua(lic(termini=AVUI + dt.timedelta(days=3)), CFG, AVUI)
        self.assertEqual(a.semafor, "vermell")

    def test_adjudicacio_es_informacio(self):
        a = L.avalua(lic(fase="Adjudicació"), CFG, AVUI)
        self.assertEqual(a.recomanacio, "Informació")

    def test_exclusions_i_sense_tema(self):
        self.assertEqual(L.avalua(lic(titol="Obres de reforma i disseny"), CFG, AVUI).recomanacio, "Descartar")
        a = L.avalua(lic(titol="Subministrament de paper", cpv=["30197630"]), CFG, AVUI)
        self.assertFalse(a.encaix)

    def test_solvencia(self):
        a = L.avalua(lic(import_eur=400000.0), {**CFG, "xifra_negoci_anual": 300000}, AVUI)
        self.assertTrue(any("Solvència" in x for x in a.alertes))

    def test_rellevants_ordenades(self):
        parells = L.rellevants([lic(id="a", termini=AVUI + dt.timedelta(days=8)), lic(id="b"),
                                lic(id="c", titol="Paper", cpv=["30197630"])], CFG, AVUI)
        self.assertEqual([l.id for l, _ in parells], ["b", "a"])

    def test_fitxa_de_decisio(self):
        f = L.fitxa_decisio(lic(), L.avalua(lic(), CFG, AVUI), {"estat": "go", "responsable": "Xavi"})
        self.assertIn("Propietat intel·lectual", f)
        self.assertIn("**Go / No-go:** go", f)
        self.assertIn("Data límit interna", f)


class TestCalibratgeAmbDadesReals(unittest.TestCase):
    """Falsos positius de les primeres revisions reals (octubre de 2026) i un cas bo."""

    @classmethod
    def setUpClass(cls):
        cls.cfg = L.config(dades.carrega())

    def test_falsos_positius_descartats(self):
        casos = [("Revisió de Plans d'Autoprotecció en centres propis (PAU)", ["71317200"]),
                 ("Servicios y suministros para la organización de eventos corporativos", ["79952000", "79931000"]),
                 ("Servicio de mejora del conocimiento de las poblaciones marinas", ["73112000"]),
                 ("Redacción de Proyecto y Dirección de Obra de urbanización", ["71240000", "71317210"])]
        for titol, cpv in casos:
            a = L.avalua(lic(titol=titol, cpv=cpv), self.cfg, AVUI)
            self.assertFalse(a.encaix and a.recomanacio != "Descartar", titol)

    def test_disseny_de_producte_en_verd(self):
        a = L.avalua(lic(titol="Servei de disseny industrial del nou mobiliari de biblioteca", cpv=["79930000"]),
                     self.cfg, AVUI)
        self.assertEqual(a.semafor, "verd")

    def test_nomes_cpv_sense_paraula_clau_es_groc(self):
        a = L.avalua(lic(titol="Servei d'enginyeria de detall", cpv=["71320000"]), self.cfg, AVUI)
        self.assertEqual(a.semafor, "groc")


class TestExecucioIRecordatoris(unittest.TestCase):
    def test_executa_desa_informe_noves_i_bd(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            db = BaseDades(d / "r.sqlite3")
            cat = dades.carrega()
            with mock.patch.object(L, "cerca", return_value=([lic()], {})):
                r = L.executa(cat, AVUI, d / "sortida", d / "vistes.json", db)
                self.assertEqual(len(r["noves"]), 1)
                db.actualitza_licitacio("pscp:1", estat="go", responsable="Xavi")
                r2 = L.executa(cat, AVUI, d / "sortida", d / "vistes.json", db)
            self.assertEqual(r2["noves"], [])  # ja vista
            fila = db.licitacio("pscp:1")
            self.assertEqual((fila["estat"], fila["responsable"]), ("go", "Xavi"))  # la cerca no esborra la decisió
            self.assertIn("disseny industrial", (d / "sortida" / "licitacions.md").read_text())
            self.assertEqual(L.llegeix_noves(d / "sortida" / "licitacions-noves.json"), [])
            # Recordatori de termini per a les licitacions amb decisió go
            dies = (dt.date.fromisoformat(fila["dades"]["termini"]) - dt.timedelta(days=3))
            self.assertTrue(diari.recordatoris_licitacions(dies, d / "r.sqlite3"))

    def test_seccio_al_correu(self):
        l, a = lic(), L.avalua(lic(), CFG, AVUI)
        assumpte, text, cos = avisos.compon([], AVUI, licitacions=[(l, a)])
        self.assertIn("licitació nova", assumpte)
        self.assertIn("LICITACIONS NOVES", text)
        self.assertIn("Licitacions noves amb encaix", cos)


class TestFinestra(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.app = crea_app(config(Path(self.dir.name)), client=ClientFals())
        self.c = TestClient(self.app, base_url="https://testserver", headers=ORIGEN)
        self.c.post("/entrar", data={"usuari": "xavi", "contrasenya": CONTRASENYA})
        l = lic(id="pscp:EXP/1", termini=dt.date.today() + dt.timedelta(days=20))
        self.app.state.radar.db.desa_licitacio(l.a_dict(), L.avalua(l, CFG, dt.date.today()).a_dict())

    def tearDown(self):
        self.c.close()
        self.dir.cleanup()

    def test_llista_i_filtres(self):
        r = self.c.get("/licitacions")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Servei de disseny industrial", r.text)
        self.assertNotIn("Servei de disseny industrial", self.c.get("/licitacions?semafor=gris").text)
        self.assertIn("Servei de disseny industrial", self.c.get("/licitacions?estat=actives&q=prototip").text)

    def test_detall_decisio_i_fitxa(self):
        url = "/licitacio?id=" + quote("pscp:EXP/1", safe="")
        self.assertIn("Fitxa de decisió", self.c.get(url).text)
        self.c.post(url, data={"estat": "no-go", "motiu": "Preu 80 %", "responsable": "Xavi"})
        fila = self.app.state.radar.db.licitacio("pscp:EXP/1")
        self.assertEqual((fila["estat"], fila["motiu"]), ("no-go", "Preu 80 %"))
        r = self.c.get("/licitacio/fitxa.docx?id=" + quote("pscp:EXP/1", safe=""))
        self.assertIn("word/document.xml", zipfile.ZipFile(io.BytesIO(r.content)).namelist())

    def test_alta_manual(self):
        r = self.c.post("/licitacions/nova", data={"titol": "Prototip de senyalètica", "termini": "2099-01-01",
                                                   "import_eur": "30000", "cpv": "79930000"}, follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        manual = [x for x in self.app.state.radar.db.licitacions() if x["font"] == "manual"]
        self.assertEqual(manual[0]["estat"], "en anàlisi")
        self.assertEqual(self.c.post("/licitacions/nova", data={"titol": "x", "url": "javascript:alert(1)"}).status_code, 400)

    def test_oferta_amb_l_assistent(self):
        r = self.c.post("/licitacio/expedient?id=" + quote("pscp:EXP/1", safe=""), follow_redirects=False)
        id_exp = int(r.headers["location"].rsplit("/", 1)[1])
        e = self.app.state.radar.db.expedient(id_exp)
        self.assertIn("<licitacio>", e["context_sistema"])
        pagina = self.c.get(f"/expedients/{id_exp}").text
        self.assertIn('data-accio="plecs"', pagina)
        self.assertNotIn('data-accio="memoria"', pagina)  # plantilles d'ajuts, fora
        # La segona vegada obre el mateix expedient
        r2 = self.c.post("/licitacio/expedient?id=" + quote("pscp:EXP/1", safe=""), follow_redirects=False)
        self.assertEqual(r2.headers["location"], f"/expedients/{id_exp}")
        self.assertIn("Licitació", self.c.get("/expedients").text)


if __name__ == "__main__":
    unittest.main()
