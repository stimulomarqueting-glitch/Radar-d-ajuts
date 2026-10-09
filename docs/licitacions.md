# Licitacions: valoració i funcionament

Valoració de 06/10/2026. La primera versió de la finestra **Licitacions** ja és a l'aplicació.

## En resum

Té sentit tenir una finestra apart de la dels ajuts, perquè el cicle és un altre:
- hi ha molts més anuncis;
- s'hi ha de respondre en dies;
- la informació que decideix és als plecs de cada licitació, no en unes bases estables.

La part fàcil d'automatitzar és detectar-les i fer-ne un primer filtre amb les dades oficials. La part
complexa és decidir. Aquí el radar ajuda de tres maneres:
- ordena la feina;
- converteix els plecs en una llista de comprovacions;
- deixa la decisió escrita per compartir-la.

## Per què és més complex que els ajuts

| | Ajuts | Licitacions |
|---|---|---|
| Volum | 76 línies al catàleg; poques novetats per setmana | Només a la PSCP, el primer semestre de 2026: 2.048 òrgans, 374.839 anuncis i 14.496 licitacions amb presentació electrònica |
| Temps per respondre | Mesos; convocatòries previsibles | Habitualment entre 10 i 35 dies des de l'anunci, segons el procediment |
| On és la informació per decidir | A les bases, estables d'un any a l'altre | Als plecs (PCAP i PPT), diferents per a cada licitació |
| Què decideix | Encaix, elegibilitat i calendari | Solvència, pes del preu, cessió de propietat intel·lectual, equip mínim, terminis i penalitats |
| Competència | Avaluació per mèrits | Preu i baixes; se sap qui guanya només amb les adjudicacions |
| Qui decideix | Direcció | Direcció, finances (solvència, garanties) i producció (capacitat) |

## Fonts oficials i què se'n pot automatitzar

| Font | Què hi ha | Automatització |
|---|---|---|
| [PSCP](https://contractaciopublica.cat/ca/inici) (Plataforma de Serveis de Contractació Pública) | Tots els òrgans de Catalunya: anuncis, plecs, sobre digital | **Sí**, amb les [dades obertes de la PSCP](https://analisi.transparenciacatalunya.cat/Economia/Contractaci-p-blica-a-Catalunya-publicacions-a-la-/ybgg-dgi6) (conjunt `ybgg-dgi6`, API Socrata): òrgan, fase, import, terminis, CPV i enllaç |
| PLACSP (Plataforma de Contratación del Sector Público) | Estat, i les plataformes autonòmiques per agregació | **Sí**, amb la sindicació ATOM (CODICE) |
| TED (Diari Oficial de la UE) | Contractes que superen els llindars europeus | **Sí**, amb l'API v3 |
| [Contractació pública de la Generalitat](https://web.gencat.cat/ca/generalitat/accio-govern/contractacio-publica) | Guies, models, RELI (Registre Electrònic d'Empreses Licitadores) | No calen dades: és referència per preparar-se |
| Plecs (PCAP, PPT, annexos) | Solvència, criteris, preu, PI, equip | **Semiautomàtic**: es baixen de l'anunci i l'assistent els llegeix |

Els contractes menors (fins a 15.000 € en serveis) no es liciten amb anunci previ: s'hi arriba amb
relació directa amb l'òrgan, i a les dades només hi apareixen un cop adjudicats.

## Què fa la finestra (versió 1)

1. **Cerca cada matí** a la PSCP, la PLACSP i TED.
   - Filtra per CPV de disseny, enginyeria i R+D, i per paraules clau.
   - Treu duplicats: el mateix expedient pot arribar per la PSCP i per l'agregació de la PLACSP.
2. **Semàfor orientatiu**, de 0 a 100. Només fa servir les dades de l'anunci.
   - **Pesos:** tema 45, temps per preparar l'oferta 20, import 20, zona 10, procediment 5.
   - 🟢 **Analitzar**, 🟡 **Vigilar**.
   - 🔴 **Termini massa just:** menys de 5 dies.
   - ⚪ **Informació:** adjudicacions i formalitzacions; serveixen per saber qui guanya i a quin preu.
   - **Alertes:** termini just, import alt (solvència o UTE), import per confirmar.
3. **Seguiment de la decisió:** nova → en anàlisi → go / no-go → presentada → guanyada / perduda.
   Cada licitació hi guarda el responsable, el motiu i les notes. La cerca diària no esborra mai
   aquesta informació.
4. **Fitxa de decisió.** Recull les dades de l'anunci i la data límit interna (el termini menys 3 dies).
   També inclou 12 comprovacions als plecs:
   - solvència econòmica i tècnica;
   - criteris i pes del preu;
   - propietat intel·lectual;
   - equip;
   - terminis i penalitats;
   - garanties;
   - subcontractació i UTE;
   - lots;
   - preguntes;
   - documentació.

   Es pot descarregar en Word i el resum es copia amb un clic.
5. **Oferta amb l'assistent.** Obre un expedient amb el context de la licitació i quatre documents
   propis:
   - anàlisi dels plecs i go / no-go;
   - memòria tècnica;
   - oferta econòmica i escenaris de puntuació;
   - documentació administrativa i calendari intern.
6. **Correu del matí:**
   - una secció per a les licitacions noves 🟢 i 🟡;
   - recordatoris de termini (7, 3 i 1 dies abans, i el mateix dia) de les que estan en anàlisi o amb
     decisió go.
7. **Alta manual:** per a licitacions que arriben per una altra via.

`python -m radar licitacions` fa la mateixa cerca des de la línia d'ordres i escriu
`sortida/licitacions.md`.

## Compartir informació per decidir: complexitat i opcions

| Nivell | Què permet | Complexitat | Estat |
|---|---|---|---|
| 1. Fitxa i resum | Enviar la fitxa en Word o el resum a l'equip o a un soci. La decisió queda escrita a l'app | Baixa | **Fet** |
| 2. Equip dins de l'app | Comptes per persona, rols (consulta / decisió), comentaris per licitació i historial de qui decideix què | Mitjana: cal autenticació per usuari, permisos i registre | Proposat |
| 3. Socis externs (UTE, clients) | Enllaç de només lectura, amb caducitat, a una fitxa concreta | Mitjana; cal no compartir mai l'oferta econòmica ni dades internes | Proposat |
| 4. Intel·ligència de preus | Adjudicacions anteriors per CPV i òrgan: qui guanya, amb quina baixa, quants licitadors | Mitjana-alta: el conjunt de la PSCP té prop de 2 milions de files. És el que més ajuda a decidir el preu | Proposat |
| 5. Plecs automàtics | Baixar els plecs de l'anunci i passar-los a l'assistent sense intervenció | Mitjana-alta: cada plataforma els publica diferent i poden canviar | Proposat |

**Recomanació:** si decidiu dues persones, n'hi ha prou amb el nivell 1. Si n'hi participen més o s'hi
afegeixen socis externs, el pas següent és el nivell 2. El nivell 4 és el que més millora les
decisions, i convé fer-lo abans del 5.

## Com decidim (go / no-go)

Criteris proposats, per discutir i ajustar:

- **Encaix:** el contracte és de disseny, desenvolupament de producte, prototip o R+D, i podem aportar-hi referències.
- **Temps:** com a mínim 10 dies per preparar l'oferta. La data límit interna és el termini menys 3 dies.
- **Solvència:** complim la xifra de negoci i els treballs similars que es demanen. Si no, cal UTE o
  descartar-la.
- **Preu:** si el preu pesa més del 60 % o la fórmula premia baixes extremes, poc marge per guanyar
  amb qualitat.
- **Propietat intel·lectual:** la cessió de drets dels dissenys és acceptable o negociable, i no ens
  impedeix reutilitzar el nostre know-how.
- **Capacitat:** hi ha equip disponible a les dates d'execució.
- **Rendibilitat:** el marge estimat compensa les hores de preparació.

Una licitació va a **go** quan es compleixen tots els criteris i hi ha un responsable. Si en falla
algun, va a **no-go** amb el motiu escrit: així, amb el temps, sabrem per què en deixem passar.

## Límits que cal tenir presents

- **Fonts provades en viu:** GitHub Actions les ha consultat del 7 al 9 d'octubre de 2026 i les tres
  funcionen (PSCP, PLACSP i TED), igual que el BDNS. A la PSCP, les columnes del conjunt de dades
  es resolen automàticament.
- **Calibratge (9 d'octubre):** la primera revisió va deixar passar 88 anuncis «amb encaix»,
  massa genèrics. Ara:
  - els CPV són exactes o famílies estretes;
  - el verd demana un CPV de disseny i una paraula clau (o dues paraules clau);
  - s'exclouen obres, direccions d'obra, manteniment, PRL i semblants.

  Amb la mateixa mostra, de 26 anuncis nous en queden 2. Cal revisar-ho al cap d'unes setmanes,
  per si ara se n'escapa algun de bo.
- **El canal d'agregació de la PLACSP està desactivat** (`placsp_agregades_url` buit) fins a
  confirmar-ne l'adreça.
- **El semàfor és orientatiu:** la decisió es pren sempre amb els plecs.
- **Configuració pendent:** a `data/perfils.yaml > config.licitacions` cal posar la xifra de negoci de
  Stimulo (`xifra_negoci_anual`) perquè avisi de la solvència econòmica. Al mateix lloc s'ajusten els
  CPV, les paraules clau, les exclusions i l'interval d'import.
