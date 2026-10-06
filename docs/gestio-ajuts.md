# Gestió d'ajuts: manual operatiu per a Stimulo

Com gestionen els ajuts les organitzacions que ho fan a escala, i què en pot aplicar Stimulo. La
referència principal és la Fundació Bosch i Gimpera (FBG), que gestiona els projectes de la
Universitat de Barcelona: 46 M€ el 2023 i més de 800 projectes el 2022. Té un portal d'autoservei
per a investigadors ([gestioprojectes.fbg.ub.edu](https://www.gestioprojectes.fbg.ub.edu/)). També
s'hi inclouen les pràctiques que exigeixen la Llei General de Subvencions i Horizon Europe.

## 1. Com s'organitzen

| Pràctica FBG / universitats | Versió per a Stimulo |
|---|---|
| Finestreta única *pre-award*: assessora la part formal, administrativa i pressupostària de cada sol·licitud | Un responsable d'ajuts que revisa cada oportunitat A del radar en 48 h: hi anem o no hi anem |
| Equips separats per a contractes amb empreses i per a justificació | Una persona prepara la proposta i una altra porta la justificació. Així s'evita que la qui va prometre sigui la qui justifica. |
| Portal amb un procediment per a cada tipus de despesa (serveis professionals, despesa digital, viatges...) | Fitxa d'una pàgina per partida elegible: què es pot imputar, quina evidència cal i qui l'aprova |
| "Comissió de gestió" (*overhead*) sobre cada projecte | Calcular el cost real de gestionar l'ajut i incloure'l al preu del servei quan Stimulo és proveïdor |
| Termini intern previ a l'oficial (OTRI) | Al radar, el **tancament intern = tancament oficial − 7 dies** per a signatures i annexos (la senyal "darrera revisió" salta 21 dies abans) |

## 2. Abans de presentar (*pre-award*)

**Checklist per convocatòria:**

1. **Elegibilitat.**
   - Tipus d'entitat (pime, gran empresa, startup, organisme de recerca).
   - Zona d'establiment.
   - Antiguitat.
   - Estar al corrent amb Hisenda i la Seguretat Social.
2. **Règim d'ajut.**
   - *Minimis*: màxim 300.000 € per "empresa única" en 3 exercicis (Reglament UE 2023/2831). Cal sumar
     tots els ajuts de *minimis* del grup. **El radar ha de portar un comptador per client.**
   - Si l'ajut va pel Reglament general d'exempció per categories (RGEC), cal comprovar l'**efecte
     incentivador**: el projecte no pot començar abans de la sol·licitud.
3. **Intensitat segons mida.** Recerca industrial 50 %, desenvolupament experimental 25 % per a
   gran empresa. Hi ha +10/+20 punts per a mitjana i petita, i +15 punts per col·laboració efectiva.
4. **Rol de Stimulo.**
   - Beneficiari, soci, proveïdor o subcontractat.
   - Si és subcontractat: la Llei General de Subvencions exigeix contracte escrit i autorització
     prèvia quan la subcontractació supera el 20 % de l'ajut i els 60.000 €.
5. **Pressupost.**
   - Personal (cost/hora = cost anual ÷ 1.720 h a Horizon Europe).
   - Col·laboracions externes, materials, amortitzacions.
   - Costos indirectes: 25 % a tant alçat a Horizon Europe, sense comptar la subcontractació.
6. **Tres ofertes** quan una despesa supera el llindar del contracte menor (15.000 € en serveis i subministraments).
7. **DNSH** (no causar un perjudici significatiu) i **declaració d'absència de conflicte d'interessos (DACI)** als fons europeus.
8. **Propietat intel·lectual.**
   - Als PoC universitaris i de "la Caixa", la PI és de la institució.
   - Stimulo signa la cessió de drets i un NDA, sobre una plantilla pròpia.
9. **Cartes de suport** o d'intenció de clients (obligatòries a l'EIC Transition 2027).
10. **Calendari intern:** esborrany a T−21 dies, signatures a T−7, presentació a T−2.

## 3. Execució i justificació (*post-award*)

- **Dossier d'auditoria des del primer dia:** resolució, pressupost aprovat, contractes, factures,
  justificants de pagament, nòmines, *timesheets*, entregables i proves de publicitat.
- **Timesheets reals per projecte**, no percentatges mensuals estimats. És la primera cosa que mira
  una auditoria. Sense, cal aportar evidències alternatives, que pesen menys.
- **Codificació comptable per projecte** (centre de cost) perquè cada despesa sigui traçable.
- **Publicitat:** logotips del finançador (FEDER, NextGenerationEU, Generalitat) en entregables, web i prototips.
- **Modificacions:** demanar autorització abans de canviar el pressupost o el calendari, mai després.
- **Compte justificatiu** amb informe d'auditor quan la convocatòria ho prevegui. ACCIÓ, per exemple,
  paga l'auditoria al 100 % fins a 1.500 € a l'Exploració tecnològica.
- **Conservació:** 5 anys després del pagament final a Horizon Europe; 4 anys de prescripció a la
  Llei General de Subvencions.

## 4. Quan Stimulo és el proveïdor d'un client beneficiari

Aquest és el cas més freqüent. Passa, per exemple, quan DOGA fa una Exploració tecnològica amb
Stimulo com a agent extern.

- Pressupost i factura amb **conceptes que coincideixin amb les partides de la convocatòria**
  (prototipatge, proves, validació).
- **Entregables datats i verificables** (informe de validació, plànols, fotografies del prototip, actes).
  Són l'evidència que el client presentarà.
- **Hores dedicades** per perfil, per si l'auditor demana justificar-les.
- **Clàusula de cessió de resultats** i confidencialitat a mida de les bases.
- Evitar vinculació societària amb el beneficiari: molts ajuts limiten la contractació amb entitats vinculades.

## 5. Eines

- **Radar:**
  - `sortida/alertes.ics` per al calendari de l'equip.
  - `sortida/enviaments_per_zona.csv` per als clients.
  - *Issue* setmanal a GitHub amb les novetats.
- **CRM:** cada proposta com a oportunitat en un embut específic ("Ajuts"). Fases: detectada → qualificada → en redacció → presentada → resolta (concedida o denegada) → en justificació → tancada.
- **Plantilles:**
  - Fitxa de projecte d'una pàgina.
  - Pressupost tipus.
  - Clàusula de PI.
  - Autoavaluació DNSH.
  - Model de *timesheet*.
