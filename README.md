# Radar d'ajuts, subvencions i licitacions — Stimulo

Radar per detectar, anticipar i distribuir per zona geogràfica oportunitats de finançament públic i
privat: des de fons de transferència d'universitats i fundacions fins als grans programes europeus.
Està pensat per a Stimulo (disseny i desenvolupament de producte amb tecnologies profundes),
Inbrooll i els seus clients.

- **Proposta v1:** [docs/proposta-radar.md](docs/proposta-radar.md)
- **Briefing DOGA (reunió de divendres):** [docs/briefing-doga.md](docs/briefing-doga.md)
- **Manual de gestió d'ajuts:** [docs/gestio-ajuts.md](docs/gestio-ajuts.md)
- **Informe actual:** [sortida/radar.md](sortida/radar.md) · tauler: `sortida/radar.html` · calendari: `sortida/alertes.ics`

## Com funciona

```
data/origen/*.xlsx ──importa-excel──▶ data/importat/   (control de files noves)
data/convocatories.yaml  (catàleg curat: 74 fitxes)
data/perfils.yaml        (Stimulo, Inbrooll, clients + paraules clau)      ──▶ radar ──▶ sortida/
data/zones.yaml          (jerarquia geogràfica ISO 3166-2)                       radar.md · radar.html
data/fonts.yaml          (33 fonts vigilades)                                    alertes.ics · enviaments_per_zona.csv
APIs: BDNS · Funding & Tenders UE · TED · PLACSP ──vigila──▶ sortida/novetats.md
```

- **Calendari:**
  - Quan una convocatòria anual ja ha tancat, el radar n'**estima la propera edició**: mateixa data
    de l'any següent, o el mes habitual d'obertura.
  - Les senyals d'alerta són: preparar (−60 dies), vigilar (−14 dies), obertura, darrera revisió
    (−21 dies) i tancament.
  - Les dates estimades porten ≈.
- **Puntuació:** encaix de 0 a 100 per perfil: temàtica 40, rol 20, zona 15, TRL 10, import 15.
  Prioritat A ≥ 80, B ≥ 65.
- **Zones:**
  - Cada convocatòria diu on ha d'estar el beneficiari. Un client és elegible si la seva zona
    pertany a alguna d'aquestes (p. ex. `ES-CT-B` ⊂ `ES-CT` ⊂ `ES` ⊂ `EU`).
  - `enviaments_per_zona.csv` creua clients i oportunitats obertes o properes.

## Ús

```bash
pip install -r requirements.txt
python -m radar valida                          # comprova el catàleg
python -m radar informe                         # genera sortida/
python -m radar alertes --dies 60               # agenda per pantalla
python -m radar perfil doga                     # millors oportunitats per a un perfil
python -m radar importa-excel fitxer.xlsx       # importa el recull i diu quines files no tenen fitxa
python -m radar vigila                          # consulta les API (cal xarxa)
python -m unittest discover -s tests            # tests
```

Totes les ordres accepten `--avui AAAA-MM-DD` per simular una data.

## Mantenir-lo

- **Nova convocatòria:** afegeix un bloc a `data/convocatories.yaml` (copia'n un de semblant).
  `python -m radar valida` avisa de camps o vocabularis incorrectes.
- **Nou client:** afegeix un perfil `tipus: client` a `data/perfils.yaml` amb la seva `zona`.
  Mentre hi hagi dades reals de clients, el repositori ha de ser privat.
- **Calendari a l'equip:** importa `sortida/alertes.ics` a Google Calendar o Outlook. Cada senyal té un avís a les 9 h.
- **Automatització:**
  - `.github/workflows/radar.yml` s'executa cada dilluns: tests, vigilància, informe, commit de
    `sortida/` i un *issue* amb les alertes dels 14 dies següents.
  - També es pot llançar a mà (*Run workflow*).

## Limitacions de la v0.1

- Durant la recerca (octubre 2026), l'accés directe a la majoria de webs oficials estava bloquejat.
  Moltes dades surten de fonts secundàries que les citen. Cada fitxa porta `confianca` i
  `fonts_verificacio`, i la llista del que cal verificar és a la proposta (§12).
- Els vigilants automàtics segueixen els formats documentats de cada API. Encara no s'han provat en
  viu: es validen en la primera execució de GitHub Actions. Si una font falla, la resta continua.
