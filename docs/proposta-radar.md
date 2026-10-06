# Radar d'ajuts, subvencions i licitacions — Proposta v1

_Stimulo · 06/10/2026 (actualitzada: puntuació només per a Stimulo i avís per correu amb socis de Holded)_

## 1. Què ha de fer el radar

El radar és de Stimulo i ha de fer cinc coses:

1. **Detectar** finançament públic i privat on Stimulo pot entrar: com a beneficiària, com a sòcia
   d'un consorci o com a proveïdora i agent tecnològic extern d'un client.
2. **Anticipar.** Moltes convocatòries anuals tanquen abans que se'n sàpiga res. El radar estima la
   propera edició a partir de l'anterior i avisa amb 60 dies de marge.
3. **Distribuir per zona.** Cada oportunitat indica on ha d'estar establert el beneficiari. Així es pot
   enviar només als clients que hi poden optar.
4. **Ordenar.** Una puntuació d'encaix amb Stimulo separa el que és prioritari del que és soroll.
   Si un client contracta el servei (com podria ser DOGA), se n'activa el perfil i també es puntua per a ell.
5. **Avisar per correu.** Quan surt una línia nova amb potencial, Stimulo rep un correu amb:
   - inici, finalització, import i descripció;
   - per què encaixem;
   - altres consideracions;
   - socis potencials trets de Holded, cadascun amb un esborrany de correu a punt per enviar.

## 2. Punt de partida: el recull 2025

L'Excel _2025 Recull ajuts públics_ és el primer motor de cerca: 29 convocatòries en tres nivells
(Catalunya, Estat, Europa). S'ha importat sencer i cada fila té fitxa al catàleg (`excel_fila`). Si
s'hi afegeixen files, `python -m radar importa-excel` diu quines falten.

En revisar-lo s'han trobat errors i dades caducades que el catàleg ja corregeix:

| Fila | Problema | Correcció |
|---|---|---|
| Columna TRL | Excel va convertir rangs com "3-7" en dates (3 de juliol) | L'importador ho desfà automàticament |
| 18 – AEI | Atribuïda a ENISA | És del Ministeri d'Indústria i Turisme (DG Indústria i PIME) |
| 19 – ENISA | Atribuïda a Red.es / NextGenEU | ENISA (Ministeri d'Indústria), préstec participatiu |
| 21 – Kit Consulting | Atribuït al MINTUR | És de Red.es |
| 22 – EIC Pathfinder | Descripció, import i TRL copiats de l'Accelerator | Recerca en consorci, TRL 1–4, fins a ~3–4 M€ |
| 20 – Kit Digital | Programa ja finalitzat (31/10/2025) | Marcat com a tancat |
| 2, 3, 5 – FEDER, Green, Nuclis | Dates de 2025; no s'ha trobat edició 2026 | Estimació 2027 amb confiança baixa i revisió programada |
| Gairebé totes | Terminis de 2025 | Actualitzats a 2026 quan s'ha pogut verificar |

El catàleg actual té **74 fitxes**: les 29 de l'Excel i 45 de noves. Les noves cobreixen:
- l'Estratègia d'innovació 2026-2030 i PILOT;
- CDTI LIC, Cervera i compra pública precomercial;
- talent (Torres Quevedo, Doctorats Industrials);
- defensa i ús dual (COINCIDENTE, IN+DEF, EDF, EDIP, NATO DIANA);
- espai (ESA BIC Barcelona, Agencia Espacial Española);
- universitats (F2I UB, UPC);
- fundacions i privats (CaixaImpulse, EmprendeXXI, FGCSIC, Fundación Repsol, Cajamar Innova);
- Europa (clústers d'Horizon, Eurostars, EUREKA SMART, EIT);
- licitacions.

## 3. Taxonomia

Cada fitxa de `data/convocatories.yaml` es classifica amb vocabularis tancats perquè es pugui filtrar
i puntuar:

- **Nivell:** local · Catalunya · Estat · Europa · Internacional.
- **Origen:** públic · universitat · fundació pública · fundació privada · corporatiu · mixt.
- **Instrument:**
  - subvenció; préstec; préstec parcialment reemborsable; cupó;
  - premi; capital; acceleració;
  - licitació; compra pública d'innovació; contracte o beca.
- **Focus:**
  - Els tres eixos estratègics: `dual`/`defensa`, `sostenibilitat`/`economia_circular`, `transferencia`/`prova_concepte`.
  - Els sectors de Stimulo: mobilitat, automoció, robòtica, agrotech, dispositius mèdics, fotònica, espai, IA, indústria...
- **Rol de Stimulo:** beneficiari · soci · proveïdor extern · subcontractat · assessor.
- **Confiança:** alta (font oficial o diverses fonts coincidents) · mitjana · baixa (estimació o pendent de verificar).

> En molts dels programes més valuosos Stimulo **no és qui sol·licita**. Hi entra com a agent
> tecnològic extern o proveïdor de prototip. Passa a l'Exploració tecnològica d'ACCIÓ, a Indústria
> del Coneixement Producte, a CaixaImpulse, al F2I de la UB i a l'EIC Accelerator. El radar puntua
> aquest rol indirecte i no descarta una convocatòria només perquè Stimulo no en pugui ser beneficiària.

## 4. Segmentació geogràfica i enviaments a clients

Cada convocatòria declara a `zones` on ha d'estar establert el beneficiari. Les zones segueixen una
jerarquia ISO 3166-2 (`data/zones.yaml`):

```
INT ─ EU ─ ES ─ ES-CT ─ ES-CT-B ─ ES-CT-AMB ─ ES-CT-BCN
                │       ├ ES-CT-GI · ES-CT-L · ES-CT-T
                ├ ES-AN ─ ES-AN-AL · ES-MD · ES-VC · ES-PV · ... (totes les CA)
           PT · FR
```

Un client a Abrera (`ES-CT-B`) és elegible per a convocatòries `ES-CT`, `ES`, `EU` i `INT`, però no
per a les de Barcelona ciutat (`ES-CT-BCN`). Alguns casos reals del catàleg:

| Convocatòria | Zona elegible | A qui s'envia |
|---|---|---|
| INNTERCONECTA STEP 2026 (CDTI, obre a l'octubre) | Només 9 CA: Andalusia, Balears, Canàries, Castella i Lleó, Castella-la Manxa, C. Valenciana, Extremadura, Galícia, Múrcia | Clients d'aquestes comunitats (Catalunya no hi és) |
| Impulsem el que fas (Barcelona Activa) | `ES-CT-BCN` | Només clients amb seu a Barcelona ciutat |
| CaixaImpulse Innovació en Salut | `ES` + `PT` | Grups de recerca i hospitals d'Espanya i Portugal |
| Exploració tecnològica (ACCIÓ) | `ES-CT` | Tots els clients catalans |
| Horizon Europe, EIC, Eurostars | `EU` | Tots (en consorci europeu) |

**Socis per zona.** En l'avís per correu, el radar només proposa com a sol·licitant un contacte
de Holded que sigui de la zona elegible. La zona surt de la província de l'adreça de Holded, de la
classificació privada o, si no n'hi ha, del prefix telefònic. Els socis de consorci (centres de
recerca, hospitals) es proposen pel tema, sense filtre de zona.

**Clients de servei.** Si un client contracta el radar, s'activa el seu perfil (`actiu: true`).
Llavors `sortida/enviaments_per_zona.csv` creua aquest client amb les oportunitats de la seva zona.

## 5. Fonts i cadència de vigilància

Les fonts són a `data/fonts.yaml` (33 fonts). Es vigilen amb tres cadències:

| Cadència | Fonts | Mètode |
|---|---|---|
| **Automàtica** (GitHub Actions, dilluns i dijous) | BDNS/InfoSubvenciones (totes les convocatòries d'Espanya, Generalitat inclosa) · Funding & Tenders de la UE (Horizon, EIC, EDF, cascada) · TED · PLACSP | API: es filtren per paraules clau i codis CPV, s'escriu `sortida/novetats.md` i les novetats van al correu de l'avís |
| **Setmanal manual** | ACCIÓ (llistat i agenda de sessions), CIDO de la Diputació de Barcelona, DOGC, sala de premsa del Govern, CDTI, EIC | Web: el futur scraping detectarà fitxes noves d'ACCIÓ, que de 2027 duran identificador `27xxx` |
| **Mensual** | AGAUR, calendari de l'Agencia Estatal de Investigación, Ministeri d'Indústria, Defensa (ETID), Agencia Espacial Española, EUDIS, DIANA, EIT, universitats (F2I, UPC), fundacions | Web i butlletins (secpho, CaixaResearch) |

Les API automàtiques segueixen el format documentat per cada emissor. Encara no s'han pogut provar
en viu: l'entorn on s'ha construït el radar no tenia accés a aquests dominis. Es validaran en la
primera execució de GitHub Actions. Si una font falla, la resta continua i l'error surt a l'informe.

## 6. Puntuació i alertes

**Encaix (0–100)** amb el perfil actiu de `data/perfils.yaml` (Stimulo):

| Component | Pes | Com es calcula |
|---|---|---|
| Temàtica | 40 | Focus de la convocatòria creuat amb els interessos ponderats (1–3) del perfil |
| Rol | 20 | Beneficiari (1,0) · soci (0,8) · proveïdor extern (0,75) · subcontractat (0,6) |
| Zona | 15 | Elegible (1,0) · fora de zona però amb rol indirecte (0,5) |
| TRL | 10 | Solapament amb el rang de maduresa del perfil |
| Impacte | 15 | Import màxim en escala logarítmica (de 5.000 € a 2,5 M€) |

La prioritat és **A** a partir de 80 punts i **B** a partir de 65. **NE** vol dir que el perfil no és
elegible per zona i no hi té cap rol indirecte. Els pesos i els llindars es poden ajustar a
`data/perfils.yaml > config`.

**Senyals d'alerta** (`sortida/alertes.ics`, subscriptible des de Google Calendar o Outlook):
- 🟡 **preparar:** 60 dies abans de l'obertura, real o estimada. És el moment de tenir la idea, el pressupost i els socis.
- 👀 **vigilar:** 14 dies abans d'una obertura estimada, per seguir el DOGC, el BOE o el portal. També surt en les revisions manuals programades.
- 🟢 **obertura** i 🔴 **tancament**, amb una "darrera revisió" 21 dies abans del tancament.
- 🟠 **tall:** 45 dies abans de cada tall de les convocatòries amb talls periòdics (EIC, Eurostars, EIT).

Les dates estimades porten ≈. Es calculen com l'edició anterior més un any. També es pot fer servir
el mes habitual d'obertura quan només es coneix el tancament.

## 7. Oportunitats destacades (octubre 2026 – març 2027)

**Per a Stimulo:**

| Quan | Oportunitat | Jugada |
|---|---|---|
| **Aquesta setmana** | **PILOT** (Generalitat, 18 M€, consorcis de 2–5 entitats amb almenys una universitat o centre) | Confirmar el termini. Muntar un consorci amb un grup UPC/UB o un centre CERCA i un client industrial (DOGA). Stimulo fa el disseny i la industrialització del prototip o pilot. |
| Set.–des. 2026 (dates per confirmar) | **EDIP BraveTech EU** (≈170 subvencions de fins a 200.000 € per a pimes de defensa, de TRL 4 a TRL 7) | Projecte propi d'ús dual (drons, robòtica, sensors) amb DOGA i Inbrooll com a proveïdors |
| 08–29/10/2026 | **Torres Quevedo** | Contractar un doctor per a la línia deep tech |
| 04/11/2026; talls 2027 el 03/02, 01/04, 01/09 i 03/11 | **EIC Accelerator** (obert al dual-use des del 17/06/2026) | Via clients startup: Stimulo com a proveïdor de producte. El cupó ACCIÓ de programes europeus (12.000 €) pot pagar-ne la preparació si la modalitat continua oberta (fins al 16/11, per verificar). |
| 02/02 · 17/02 · 14/04/2027 | **Horizon CL4 Made in Europe · CL1 Salut · CL5 2Zero** | Soci pime de disseny en consorcis europeus |
| 04/03/2027 | **Eurostars C12** (obre el 17/12/2026) | Stimulo o Inbrooll lideren amb un soci internacional; DOGA com a soci |
| ≈ des. 2026 – feb. 2027 | **CaixaImpulse Innovació en Salut** | Oferir un paquet de prototip a grups i hospitals abans de l'obertura; Inbrooll aporta la ISO 13485 |
| ≈ feb.–mar. 2027 | **Indústria del Coneixement – Producte** (fins a 150.000 €) | Igual: entrar al pressupost dels grups com a proveïdors de prototip |
| Gener 2027 | **F2I UB** (guanyadors) · demo day d'**Industrial Tech UPC** (desembre) | Captar projectes de PoC ja finançats |
| Tot l'any | **CDTI Cervera** (90 %, tram no reemborsable 33 %) | Projecte d'R+D de Stimulo amb UPC-CD6, Eurecat o Leitat |

**Per a Inbrooll:** EIC Accelerator (si porta un producte propi com Clyype), Horizon CL1 Salut,
convocatòries en cascada (50.000–150.000 €), AEI i Eurostars.

**Per a DOGA:** vegeu [briefing-doga.md](briefing-doga.md).

## 8. Eixos estratègics

### 8.1 Tecnologies duals

El 2026 el finançament dual s'ha obert a gairebé tots els nivells:

- **UE:**
  - L'EIC accepta projectes d'ús dual des del 17/06/2026.
  - EDF (programa de treball 2027 previst a final de 2026, ~1.000 M€).
  - EDIP BraveTech i FAST.
  - EUDIS Business Accelerator.
- **OTAN:** DIANA, amb reptes anuals de 100.000 € + 300.000 €.
- **Espanya:**
  - COINCIDENTE (maig–juliol).
  - IN+DEF (EOI).
  - Reserva de 25 M€ del CDTI per a projectes duals.
  - Compres precomercials de Defensa, com el robot terrestre autònom (11,9 M€).
- **Catalunya:**
  - L'Estratègia 2026-2030 prioritza seguretat i defensa.
  - Programa per capacitar 400 empreses del sector.
  - La Cambra de Barcelona compta 812 empreses d'ús dual.

Stimulo hi té un precedent, DRONSTORE II (AEI amb secpho, dron autònom per a un magatzem de l'Exèrcit).
Té també una aliança natural: DOGA hi posaria els motors i actuadors, i Inbrooll l'electrònica.
**Decisió pendent per a la direcció:** definir una política pròpia sobre el límit entre l'ús dual i
la defensa. Afecta la marca i la selecció de projectes.

### 8.2 Sostenibilitat

Els instruments principals són:
- Horizon CL4 Made in Europe: re-fabricació i materials circulars del disseny al mercat.
- CL5 2Zero.
- LIFE (economia circular, ~60 %).
- Innovation Fund.
- Els ajuts verds d'ACCIÓ, si continuen dins l'Estratègia.

L'ecodisseny és un argument diferencial de Stimulo. A més, el principi DNSH ("no causar un perjudici
significatiu") és obligatori en els fons europeus: convé tenir una plantilla d'autoavaluació.

### 8.3 Transferència universitat-empresa

La cadena de valorització té graons clars. Stimulo pot ser present a cadascun:

```
Llavor AGAUR (20 k€) · F2I UB (25 k€) · LLAVOR UPC (10 k€)
   → Producte AGAUR (150 k€) · CaixaImpulse (50/150/500 k€) · Proves de Concepte AEI (300 k€)
      → PILOT (consorci) · CDTI Cervera · Col·laboració Público-Privada AEI · EIC Transition (2,5 M€)
         → spin-off: NEOTEC · Startup Capital · EIC Accelerator
```

**Proposta comercial:** un **"paquet prototip PoC"**, de preu tancat i inferior a 15.000 €
(llindar del contracte menor de serveis), i un **"paquet industrialització"**. Tots dos amb clàusules
de propietat intel·lectual preparades per a fundacions universitàries (FBG, UPC, CSIC) i hospitals.

## 9. Com es gestionen els ajuts

Les fundacions universitàries com la Fundació Bosch i Gimpera (46 M€ gestionats el 2023) separen
la preparació de la sol·licitud (*pre-award*) de la justificació (*post-award*). També estandarditzen
cada tipus de despesa. El manual operatiu per a Stimulo és a [gestio-ajuts.md](gestio-ajuts.md).
Conté: rols, *checklist* per convocatòria, termini intern, *timesheets*, comptador de *minimis*,
dossier d'auditoria, DNSH i propietat intel·lectual.

## 10. Full de ruta

| Versió | Quan | Abast |
|---|---|---|
| **v0.1** | Avui | Catàleg de 74 fitxes, motor de puntuació i alertes, tauler HTML, calendari .ics, enviaments per zona, vigilants automàtics, informe setmanal |
| v0.2 | +2 setmanes | Verificar les fitxes de confiança baixa (§12). Validar els vigilants a GitHub Actions. Carregar els clients amb la seva zona. Subscriure el calendari a l'equip. |
| v0.3 | +1–2 mesos | Scraping d'ACCIÓ, CIDO i DOGC. Concessions del RAISC i la BDNS per detectar empreses que reben ajuts (prospecció). Comptador de *minimis* per client. |
| v1.0 | T1 2027 | Butlletí mensual per zona. Embut de propostes al CRM. Indicadors. |

## 11. Indicadors

- Oportunitats A detectades per mes, i percentatge detectat 30 dies o més abans de l'obertura.
- Propostes presentades (Stimulo, Inbrooll, clients) i taxa d'èxit.
- Euros captats pels clients en projectes on participa Stimulo, i facturació de Stimulo derivada.
- Clients notificats per zona i conversió a reunió.

## 12. Pendent de verificar (per ordre)

1. **PILOT:** bases, import per projecte i termini.
2. **EDIP BraveTech EU:** dates i requisits.
3. **Cupons ACCIÓ:** quines modalitats segueixen obertes fins al 16/11/2026.
4. **Exploració tecnològica:** si una agència de disseny és "proveïdor especialitzat" (bases EMT/2403/2026) i el calendari 2027.
5. **Doctorats Industrials de la Generalitat:** calendari 2026/27.
6. **Nuclis d'R+D, FEDER pimes, Green i Inversions d'alt impacte d'ACCIÓ:** si tenen edició 2026 o han quedat absorbits per l'Estratègia.
7. **INNTERCONECTA STEP:** dates exactes d'octubre.
8. **Cajamar Innova, Fundación Repsol, EIT Manufacturing, Food i InnoEnergy, Interreg, LIFE 2027:** convocatòries vigents.

> Durant la recerca, l'accés directe a la majoria de webs oficials estava bloquejat. Moltes dades
> surten de fragments de cerca que citen la font oficial. Cada fitxa porta el nivell de confiança i
> les URL de verificació.

## Fonts principals

- ACCIÓ, Exploració tecnològica: [fitxa 26043](https://www.accio.gencat.cat/ca/serveis/cercador-ajuts-empresa/ajutsiserveis/26043-projectes-exploracio-tecnologica) · [CIDO](https://cido.diba.cat/subvencions/21935051/subvencions-per-a-projectes-dinnovacio-empresarial-rdi-any-2026-linia-de-projectes-dexploracio-tecnologica-generalitat-de-catalunya-agencia-per-a-la-competitivitat-de-lempresa-accio)
- Govern: [Estratègia d'innovació 2026-2030](https://govern.cat/gov/notes-premsa/849190/govern-aprova-lestrategia-dinnovacio-empresarial-catalunya-que-augmenta-30-percent-ajuts-empreses-aquest-2026) · [primers 17 M€](https://govern.cat/salapremsa/notes-premsa/858792/govern-activa-primers-17-milions-deuros-dajuts-inclosos-lestrategia-dinnovacio-empresarial-catalunya-2026-2030) · [PILOT](https://govern.cat/gov/notes-premsa/870016/el-govern-presenta-pilot-el-nou-programa-per-accelerar-la-innovacio-tecnologica)
- Via Empresa: [18 M€ per a proves de concepte](https://www.viaempresa.cat/innovacio/govern-aporta-18-milions-accelerar-innovacio-tecnologica-proves-concepte_2240865_102.html)
- CDTI: [Cervera 2026](https://www.cdti.es/ayudas/proyectos-de-id-de-transferencia-tecnologica-cervera-0) · [NEOTEC 2026](https://www.ciencia.gob.es/Noticias/2026/abril/MICIU-lanza-convocatoria-NEOTEC-2026.html) · [CPP robot terrestre](https://www.cdti.es/noticias/cdti-innovacion-fondos-feder-licitacion-compra-publica-precomercial-robot-terrestre-autonomo-tecnologia-dual-defensa-civil)
- Ministeri d'Indústria: [AEI](https://www.mintur.gob.es/portalayudas/agrupacionesempresariales) · [BOE-B-2026-17584](https://www.boe.es/boe/dias/2026/05/29/pdfs/BOE-B-2026-17584.pdf) · secpho: [Q LEAF IN VITRO](https://www.secpho.org/casos/qleaf-invitro/)
- SETT: [instruments](https://sett.gob.es/instrumentos/)
- EIC: [obertura al dual-use](https://eic.ec.europa.eu/news/european-innovation-council-opens-defence-and-dual-use-technologies-2026-06-17_en) · [programa de treball 2027](https://www.myriadassociates.ie/resources/news/2026/eic-work-programme-2027/)
- EDIP: [programa de treball](https://defence-industry-space.ec.europa.eu/edip-work-programme-adopted-2026-03-30_en) · NATO DIANA: [reptes](https://www.diana.nato.int/challenges.html)
- UB/FBG: [F2I](https://www.fbg.ub.edu/actualitat/la-universitat-de-barcelona-destinara-mes-de-100-000-euros-per-impulsar-la-transferencia-de-la-recerca-a-traves-dels-f2i/) · [Gestió de projectes](https://www.gestioprojectes.fbg.ub.edu/)
- Fundació "la Caixa": [CaixaImpulse Innovació en Salut](https://caixaresearch.org/es/convocatoria-caixaimpulse-innovacion-salud) · FGCSIC: [COMTE-Innovación](https://fgcsic.es/convocatoria-evento/comte-innovacion-envalor-2/) · [Cajamar Innova](https://cajamarinnova.es/es/)
