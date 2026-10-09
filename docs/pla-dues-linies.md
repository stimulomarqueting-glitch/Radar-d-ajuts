# Radar per a finals de 2026 i inicis de 2027: dues línies de treball

Revisió del 09/10/2026. El radar s'organitza en dues línies amb un horitzó de **novembre de 2026 a juny
de 2027**:

1. **Projectes de producte amb clients i consorcis.** El client o el consorci demana l'ajut i Stimulo
   hi fa el desenvolupament de producte, com a proveïdor, subcontractat o soci. És la línia amb **més
   retorn comercial** i va primer a tot arreu.
2. **Creixement i transformació de Stimulo.** Stimulo és la sol·licitant: talent, R+D propi, cupons,
   internacionalització i finançament.

## Què ha canviat al radar

| Abans | Ara |
|---|---|
| Una sola llista ordenada per encaix amb Stimulo | Cada fitxa diu a quina línia pertany (`linies`). El pla ordena els projectes pel **retorn estimat per projecte** |
| Les convocatòries on sol·licita el client quedaven barrejades amb les de Stimulo | La línia de projectes surt primer: al pla, al correu del matí i al filtre del tauler |
| Calendari d'alertes per data | Calendari de feina per línia: prospectar clients, tancar consorci, tancament intern i termini |

**Catàleg (79 fitxes):**
- 47 només de projectes;
- 16 de les dues línies;
- 11 només de creixement;
- 5 fora de les dues línies (inversions productives i d'alt impacte, Indústria del Coneixement –
  Innovadors, SEPIDES i EIC STEP Scale-up).

## On es veu

- **Pla:** `python -m radar pla`.
  - Escriu `sortida/pla-2026-2027.md` i `.html`, sense dades de Holded. S'actualitza amb l'informe
    de cada matí.
  - `--privat` escriu `privat/pla-2026-2027-clients.*`, amb clients i socis de Holded per a cada
    convocatòria.
  - `--des` i `--fins` canvien l'horitzó.
- **Aplicació:** a la pestanya **Pla**, amb clients i socis de Holded i un botó per preparar la
  sol·licitud. Es pot descarregar.
- **Tauler:** el filtre «Línia de treball».
- **Correu del matí:** les línies noves s'agrupen per línia de treball, primer la de projectes, amb
  el retorn estimat per projecte.

## Com es calcula el retorn per projecte

És un ordre de magnitud per prioritzar, no una previsió de vendes:

1. **Mida típica del projecte:** import màxim de l'ajut ÷ intensitat. El mínim és el pressupost mínim
   de la fitxa o, si no n'hi ha, un terç del màxim.
   - Si la fitxa no té import, es fa servir el pressupost mínim (×3 per al màxim).
   - Per als programes europeus en consorci sense import, es pren un projecte típic de 2 a 6 M€.
2. **Part de Stimulo segons el rol:**
   - proveïdor, del 30 al 60 %;
   - subcontractat, del 15 al 40 %;
   - soci de consorci, del 5 al 15 %.
3. **Sostre per projecte:** 300 k€ com a proveïdor o subcontractat, i 500 k€ com a soci.
4. **Nivell:** alt si el punt mitjà és ≥ 75 k€, mitjà si és ≥ 20 k€.

Si una fitxa no encaixa amb aquest càlcul (p. ex. les licitacions), es fixa a mà amb
`retorn_eur: [mínim, màxim]`. Una mateixa convocatòria pot donar diversos projectes amb clients
diferents.

**Per afinar:** les quotes i els sostres són a `radar/pla.py` (`QUOTA_ROL`, `SOSTRE_ROL`). Convé
contrastar-les amb els projectes que Stimulo ja ha fet amb clients subvencionats.

## Calendari de feina

| Línia | Fita | Quan |
|---|---|---|
| Projectes | Prospectar clients i socis, i triar la idea de projecte | 90 dies abans d'obrir (o 75 abans del termini) |
| Projectes | Tancar client, consorci i pressupost | 30 dies abans d'obrir |
| Creixement | Preparar la sol·licitud de Stimulo | 45 dies abans d'obrir (o del termini) |
| Totes dues | Tancament intern de la proposta | 7 dies abans del termini |

El pla separa:
- **Ara mateix:** obertes que tanquen abans de l'1 de novembre.
- **Començar ja:** la feina prèvia ja hauria d'haver començat.
- **Obertes tot l'any:** sense calendari; es poden proposar a cada conversa amb clients.
- **Anunciades, a vigilar:** encara sense dates.

## Primera lectura del pla (09/10/2026)

- **45** convocatòries per generar projectes amb clients, **20** amb retorn alt. Al capdamunt:
  - Horizon Europe Clúster 4 Made in Europe (termini 02/02/2027) i Clúster 1 Salut (17/02/2027);
  - EIC Accelerator (04/11/2026);
  - EDF (EUDIS), Misiones CDTI, CaixaImpulse Innovació en Salut i la LIC del CDTI.
- **13** convocatòries de creixement amb prioritat A o B, com ara:
  - EDIP BraveTech EU;
  - Nuclis d'R+D;
  - COINCIDENTE;
  - Noves oportunitats de negoci;
  - AEI del MINTUR;
  - NATO DIANA;
  - PID i Cervera del CDTI;
  - FEDER innovació pimes.
- **Ara mateix:**
  - EIC STEP Scale Up Defence i EIC Pathfinder (28/10);
  - COMTE-Innovación (≈ 31/10);
  - ACCIÓ Green (≈ 16/10);
  - els dos doctorats industrials (AGAUR ≈ 15/10 i AEI 26/10).
- **Començar ja:** 13 convocatòries de projectes. Les més grans tenen el termini entre novembre i
  febrer: Horizon Europe, EIC Accelerator, CaixaImpulse i Eurostars.

## Recomanacions

1. **Pipeline comercial per a la línia 1.** Per a cada convocatòria amb retorn alt, una llista curta
   de clients candidats i una persona responsable. La versió privada del pla ja proposa clients i
   socis de Holded per a cada convocatòria.
2. **Calibrar el retorn** amb dades reals de projectes anteriors (quota per rol i mida de projecte).
3. **Completar dades que limiten la línia 2:**
   - si Stimulo és microempresa (canvia l'elegibilitat de Noves oportunitats de negoci);
   - la xifra de negoci (solvència a les licitacions).
4. **Revisar el pla un cop al mes.** És el ritme amb què canvien les dates estimades (≈) i se n'anuncien
   de noves.
