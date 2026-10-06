# Radar d'ajuts, subvencions i licitacions — Stimulo

Radar de Stimulo (disseny i desenvolupament de producte amb tecnologies profundes) per detectar i
anticipar oportunitats de finançament públic i privat: des de fons de transferència d'universitats
i fundacions fins als grans programes europeus. Quan surt una línia nova amb potencial, envia un
correu amb el resum de l'ajut, per què encaixem i els socis potencials trets de Holded, amb un
esborrany de correu per a cadascun.

També inclou una **aplicació web privada** (per al VPS, amb contrasenya) per preparar cada sol·licitud
amb un assistent de Claude que ja té tot el context de Stimulo, de l'ajut i dels socis.

- **Proposta v1:** [docs/proposta-radar.md](docs/proposta-radar.md)
- **Briefing DOGA:** [docs/briefing-doga.md](docs/briefing-doga.md)
- **Manual de gestió d'ajuts:** [docs/gestio-ajuts.md](docs/gestio-ajuts.md)
- **Instal·lació al VPS:** [docs/desplegament.md](docs/desplegament.md)
- **Informe actual:** [sortida/radar.md](sortida/radar.md) · tauler: `sortida/radar.html` · calendari: `sortida/alertes.ics`

## Com funciona

```
data/origen/*.xlsx ──importa-excel──▶ data/importat/   (control de files noves)
data/convocatories.yaml  (catàleg curat: 74 fitxes)
data/perfils.yaml        (Stimulo; clients de servei desactivats)          ──▶ radar ──▶ sortida/
data/zones.yaml          (jerarquia geogràfica ISO 3166-2)                       radar.md · radar.html · alertes.ics
data/fonts.yaml          (33 fonts vigilades)
APIs: BDNS · Funding & Tenders UE · TED · PLACSP ──vigila──▶ sortida/novetats.md
Holded (només lectura) + classificació privada ──avisa──▶ correu a Stimulo (mai al repositori)
```

- **Puntuació:**
  - Encaix de 0 a 100 amb Stimulo: temàtica 40, rol 20, zona 15, TRL 10, import 15.
  - Prioritat A ≥ 80, B ≥ 65.
  - Si un client contracta el servei (p. ex. DOGA), n'hi ha prou amb posar `actiu: true` al seu
    perfil per puntuar-lo també i generar-ne els enviaments per zona.
- **Calendari:**
  - Quan una convocatòria anual ja ha tancat, el radar n'**estima la propera edició**: mateixa data
    de l'any següent, o el mes habitual d'obertura.
  - Les senyals d'alerta són: preparar (−60 dies), vigilar (−14 dies), obertura, darrera revisió
    (−21 dies) i tancament.
  - Les dates estimades porten ≈.
- **Zones:** cada convocatòria diu on ha d'estar el beneficiari (p. ex. `ES-CT-B` ⊂ `ES-CT` ⊂ `ES` ⊂ `EU`).
  Els socis que haurien de ser els sol·licitants només es proposen si són de la zona elegible.

## Avís per correu

La revisió es fa **cada matí**: al VPS, amb el servei `programador` (a les 07:30, `RADAR_HORA`); mentre
no estigui instal·lat, amb GitHub Actions (05:17 UTC). Si no hi ha res nou, no s'envia cap correu.

**Quan avisa.** Una línia es considera nova amb potencial si compleix tres condicions:
- **Encaix:** és de prioritat A, o de prioritat B amb data límit en els 45 dies següents.
- **Dates:** està oberta, obre en els 60 dies següents o està oberta tot l'any.
- **Novetat:** encara no s'havia avisat aquesta edició.

L'estat es desa a `data/estat/notificades.json`, que només conté identificadors de convocatòries.

**Què hi ha a cada línia:**
- Inici, finalització, import i zona elegible.
- Descripció.
- Per què encaixem.
- Altres consideracions.
- Fins a 3 socis potencials de Holded, amb la persona de contacte i un enllaç «obrir esborrany» amb el correu ja redactat: en català als socis de Catalunya i en castellà a la resta.

El correu també inclou les novetats que els vigilants han trobat a les fonts oficials i, si tens
sol·licituds en preparació a l'aplicació, recordatoris de termini (21, 14, 7, 3 i 1 dies abans del
tancament i el mateix dia).

**Configuració.** Afegeix aquests secrets a GitHub, a *Settings → Secrets and variables → Actions*:

| Secret | Valor |
|---|---|
| `RADAR_DESTINATARI` | Adreça (o adreces separades per comes) que rep l'avís |
| `SMTP_HOST`, `SMTP_PORT` | Servidor de sortida. Google Workspace: `smtp.gmail.com` i `587` |
| `SMTP_USER`, `SMTP_PASSWORD` | Compte que envia. Amb Google, cal una *contrasenya d'aplicació* |
| `SMTP_FROM` (opcional) | Remitent, si és diferent de `SMTP_USER` |
| `HOLDED_API_KEY` | Clau d'API de Holded (Configuració → Desenvolupadors). Només es fa servir per llegir contactes |
| `RADAR_SOCIS_YAML` (opcional) | Classificació privada dels contactes com a socis (tipus, zona, temes). El format és el de `privat/socis.yaml` |

Sense els secrets SMTP no s'envia res. En aquest cas, el flux obre un *issue* amb les alertes, sense
dades de contactes. Per rebre un primer correu complet amb totes les línies vigents: *Actions →
Radar d'ajuts → Run workflow* amb l'opció «Envia… totes les línies».

**Privadesa.** Els contactes de Holded i la classificació de socis no es desen mai al repositori:
només viatgen dins del correu. La carpeta `privat/` està a `.gitignore`. Tot i així, convé que el
repositori sigui **privat**, perquè conté el briefing d'un client.

**Classificar els socis.** El radar decideix el tipus, la zona i els temes de cada contacte amb tres
fonts, per aquest ordre:
1. El fitxer privat.
2. Les etiquetes de Holded amb prefix `radar-`. Per exemple, `radar-robotica`, `radar-salut` o
   `radar-tipus-recerca`, que es poden posar directament a Holded.
3. Heurístiques pel nom de l'organització.

## Aplicació web i assistent de propostes

`python -m radar web` (en local) o `docker compose up -d` (al VPS, vegeu
[docs/desplegament.md](docs/desplegament.md)). Seccions:

- **Tauler:** el mateix que `sortida/radar.html`, amb un botó «Preparar sol·licitud» a cada ajut.
- **Sol·licituds:** cada expedient té un xat amb Claude que coneix Stimulo, la fitxa de l'ajut, la idea
  del projecte, els socis triats de Holded i el manual de gestió d'ajuts. L'assistent pot cercar i
  llegir les bases oficials al web.
  - Botons per redactar cada document: anàlisi d'elegibilitat, fitxa, memòria tècnica, pla de treball,
    pressupost, impacte i DNSH, socis i cartes de compromís, correus als socis, resum executiu i
    checklist.
  - **Preparar-ho tot:** redacta en ordre tots els documents que falten; cada un té en compte els
    anteriors i es pot aturar.
  - Adjunts (bases en PDF, ofertes, CV, imatges), edició manual amb versions i exportació a Word o
    Markdown.
- **Socis:** contactes de Holded agrupats per organització i, per a cada convocatòria, els que hi
  encaixen amb el correu ja redactat.
- **Avisos:** historial de revisions, correus desats i botó «Revisar ara».

**Seguretat.** Un sol usuari amb contrasenya (PBKDF2), segon factor opcional (TOTP), galeta de sessió
signada (HttpOnly, Secure), límit d'intents per IP, CSP estricta i comprovació d'origen a totes les
peticions que modifiquen dades. Sense `RADAR_CONTRASENYA_HASH` i `RADAR_SECRET` no s'hi pot entrar.
Les dades (expedients, converses, fitxers) són a `privat/app/` i no es pugen mai al repositori.

## Ús

```bash
pip install -r requirements.txt
python -m radar valida                          # comprova el catàleg
python -m radar informe                         # genera sortida/
python -m radar alertes --dies 60               # agenda per pantalla
python -m radar avisa                           # vista prèvia de l'avís (privat/avisos/), sense enviar
python -m radar avisa --envia                   # envia l'avís (secrets SMTP_* i RADAR_DESTINATARI)
python -m radar diari                           # revisió del matí: vigila + informe + avís (+ recordatoris)
python -m radar programador                     # servei que fa la revisió cada dia a RADAR_HORA
python -m radar web                             # aplicació web a http://127.0.0.1:8000
python -m radar contrasenya                     # genera les claus d'accés per al fitxer .env
python -m radar perfil doga                     # encaix per a un client de servei (encara que estigui inactiu)
python -m radar importa-excel fitxer.xlsx       # importa el recull i diu quines files no tenen fitxa
python -m radar vigila                          # consulta les API (cal xarxa)
python -m unittest discover -s tests            # tests
```

Totes les ordres accepten `--avui AAAA-MM-DD` per simular una data.

## Mantenir-lo

- **Nova convocatòria:**
  - Afegeix un bloc a `data/convocatories.yaml` (copia'n un de semblant).
  - Els camps `encaix_stimulo`, `punts_forts` i `socis_cal` milloren el correu.
  - `python -m radar valida` avisa de camps o vocabularis incorrectes.
- **Calendari a l'equip:** importa `sortida/alertes.ics` a Google Calendar o Outlook. Cada senyal té un avís a les 9 h.
- **Automatització:** `.github/workflows/radar.yml` s'executa cada matí i fa aquests passos:
  1. Tests.
  2. Vigilància de fonts.
  3. Informe.
  4. Avís per correu.
  5. Commit de `sortida/` i `data/estat/`.

  Quan el VPS ja fa la revisió, crea la variable de repositori `RADAR_PROGRAMADOR=vps` (*Settings →
  Secrets and variables → Actions → Variables*): GitHub Actions deixa de vigilar i d'enviar correus
  per no duplicar-los, i només actualitza l'informe quan canvia el catàleg.

## Limitacions de la v0.1

- Durant la recerca (octubre 2026), l'accés directe a la majoria de webs oficials estava bloquejat.
  Moltes dades surten de fonts secundàries que les citen. Cada fitxa porta `confianca` i
  `fonts_verificacio`, i la llista del que cal verificar és a la proposta (§12).
- Els vigilants automàtics i l'API de Holded segueixen els formats documentats per cada servei.
  Encara no s'han provat en viu: es validen en la primera execució de GitHub Actions. Si una font
  falla, la resta continua.
