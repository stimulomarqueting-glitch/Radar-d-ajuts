# Servei de screening d'ajuts per a clients

Com aplicar el radar de Stimulo a un client (per exemple DOGA) i a cadascuna de les seves divisions,
i què se li entrega.

## Què rep el client

| Entregable | Format | Per a què |
|---|---|---|
| **Informe de screening** | Pàgina web (HTML) que s'obre sense instal·lar res; també es pot imprimir en PDF | Resum per divisió, matriu línies × divisions, fitxa de cada oportunitat i calendari de 12 mesos |
| **Calendari d'alertes** | Fitxer `.ics` (Google Calendar, Outlook) | Les dates de preparar, obertura i tancament de cada línia seleccionada |
| **Radar continu** (opcional) | Correu quan surt una línia nova amb encaix | Que cap convocatòria passi sense que la divisió ho sàpiga |
| **Sol·licituds** (opcional) | Memòria, pla de treball, pressupost, cartes… en Word | Stimulo les prepara a l'aplicació amb l'assistent, amb el context del client i la divisió |

Per a cada oportunitat l'informe diu: què finança, l'ajut, la finestra (amb ≈ si és estimada), el paper
del client (sol·licitant o soci), el paper de Stimulo, la idea de projecte de la divisió que hi encaixa i
el que cal tenir en compte (consorci, intensitat per a gran empresa, *minimis*, préstec).

**Entrar al sector de defensa i ús dual.** Si alguna divisió té temes d'ús dual, defensa o espai,
l'informe hi afegeix una secció amb:
- els ajuts d'aquests temes on el client pot participar;
- les properes trobades i programes per entrar al sector;
- amb qui parlar (contractistes principals, enginyeries, clústers);
- els requisits que demanaran els compradors.

Les dades són a `data/ecosistema.yaml`.

## Com es fa

1. **Perfil per divisió** (reunió d'1 hora + fitxa). Per a cada divisió: productes, mercats, TRL
   habitual, temes prioritaris (1–3) i 2–4 idees de projecte del full de ruta. Del client: ubicació
   (zona d'elegibilitat), mida (pime, midcap o gran empresa) i ajuts de *minimis* rebuts.
2. **Radar.** Es puntua cada divisió contra tot el catàleg (74 línies i 34 fonts vigilades) amb la
   mateixa fórmula que per a Stimulo: temes 40, rol 20, zona 15, TRL 10, import 15.
3. **Filtre d'elegibilitat.** Només queden les línies on el client pot ser sol·licitant o soci per zona,
   mida i tipus d'entitat, i que obren o tanquen en els propers 12 mesos. Una gran empresa no veu les
   línies només per a pimes.
4. **Revisió experta (Stimulo).** Validar la llista curta, ajustar idees i decidir què s'ofereix.
5. **Entrega i seguiment.** Informe + calendari; si el client ho contracta, avís continu i
   preparació de sol·licituds.

## Com s'afegeix un client

1. Copia `data/clients/doga.yaml` amb l'id del client nou i omple les divisions.
   - Si hi ha dades confidencials (pressupostos, full de ruta, ajuts rebuts), desa el fitxer a
     `privat/clients/<id>.yaml`: no es puja mai al repositori i té prioritat sobre `data/clients/`.
2. `python -m radar valida` comprova zones, temes i rols.
3. `python -m radar screening <id>` genera a `privat/clients/<id>/`:
   - l'informe HTML;
   - el Markdown;
   - el JSON;
   - el calendari `.ics`.

   Opcions:
   - `--divisio motors` limita l'informe a una divisió (es pot repetir);
   - `--maxim 5` limita les línies per divisió.
4. A l'aplicació, a **Clients**:
   - l'informe es pot ensenyar en pantalla o descarregar;
   - cada oportunitat té un botó **Preparar sol·licitud**. Obre un expedient amb el context del
     client i de la divisió, i l'assistent hi redacta en nom del client.

## Exemple: DOGA

L'informe de demostració fa servir quatre divisions deduïdes de fonts públiques (web, fires i
directoris). Cal validar-les amb DOGA:

| Divisió | Abast |
|---|---|
| Motors i motorreductors | DC d'escombretes i brushless fins a 72 V, BRL100 |
| Sistemes de neteja i visibilitat | Eixugaparabrises, rentadors i dipòsits |
| Components de vehicle | Elevavidres, retrovisors i estampació |
| Recanvis i postvenda | DOGA Parts |

Resultat a 06/10/2026:
- 12 línies elegibles, 6 de prioritat A.
- **Motors:** Horizon Europe CL4 (termini 02/02/2027) amb «motors sense terres rares», i CDTI LIC
  oberta tot l'any.
- **Neteja:** CL4 i CL5 2Zero, i la línia d'automoció d'ACCIÓ (≈ estiu 2027) amb «neteja de sensors
  LiDAR».
- **Components:** CL4 i CDTI LIC amb «peces més lleugeres i reciclades».
- **Postvenda:** CDTI LIC i EUREKA SMART (26/01/2027). Les línies d'internacionalització del
  catàleg (Cupons d'ACCIÓ, Eurostars com a líder) són per a pimes i no hi surten. Si DOGA vol
  prioritzar la postvenda, cal afegir al catàleg instruments d'internacionalització per a gran
  empresa.

### Per a la conversa de divendres

- **Ensenyar l'informe:**
  - filtre per divisió;
  - matriu de línies × divisions;
  - una fitxa oberta (per exemple, Horizon CL4 per a Motors);
  - el calendari.
- **Validar:**
  - les divisions i qui en porta cadascuna;
  - les idees de projecte;
  - les preguntes de l'informe (ajuts de *minimis*, mida del grup, pressupost d'R+D 2027).
- **Proposar:** el screening validat, el radar continu per divisió i la preparació de 1–2
  sol·licituds. La primera pot ser CDTI LIC o PID (oberta) o Horizon CL4 si hi ha consorci abans de
  febrer.
