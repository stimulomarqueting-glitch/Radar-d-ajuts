# Radar d'ajuts, subvencions i licitacions — Stimulo

Radar de Stimulo (disseny i desenvolupament de producte amb tecnologies profundes) per detectar i
anticipar oportunitats de finançament públic i privat: des de fons de transferència d'universitats
i fundacions fins als grans programes europeus. Quan surt una línia nova amb potencial, envia un
correu amb el resum de l'ajut, per què encaixem i els socis potencials trets de Holded, amb un
esborrany de correu per a cadascun.

- **Proposta v1:** [docs/proposta-radar.md](docs/proposta-radar.md)
- **Briefing DOGA:** [docs/briefing-doga.md](docs/briefing-doga.md)
- **Manual de gestió d'ajuts:** [docs/gestio-ajuts.md](docs/gestio-ajuts.md)
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

`python -m radar avisa --envia` s'executa dilluns i dijous a GitHub Actions.

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

El correu també inclou les novetats que els vigilants han trobat a les fonts oficials.

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

## Ús

```bash
pip install -r requirements.txt
python -m radar valida                          # comprova el catàleg
python -m radar informe                         # genera sortida/
python -m radar alertes --dies 60               # agenda per pantalla
python -m radar avisa                           # vista prèvia de l'avís (privat/avisos/), sense enviar
python -m radar avisa --envia                   # envia l'avís (secrets SMTP_* i RADAR_DESTINATARI)
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
- **Automatització:** `.github/workflows/radar.yml` fa aquests passos:
  1. Tests.
  2. Vigilància de fonts.
  3. Informe.
  4. Avís per correu.
  5. Commit de `sortida/` i `data/estat/`.

## Limitacions de la v0.1

- Durant la recerca (octubre 2026), l'accés directe a la majoria de webs oficials estava bloquejat.
  Moltes dades surten de fonts secundàries que les citen. Cada fitxa porta `confianca` i
  `fonts_verificacio`, i la llista del que cal verificar és a la proposta (§12).
- Els vigilants automàtics i l'API de Holded segueixen els formats documentats per cada servei.
  Encara no s'han provat en viu: es validen en la primera execució de GitHub Actions. Si una font
  falla, la resta continua.
