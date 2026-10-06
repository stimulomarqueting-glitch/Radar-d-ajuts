"""Radar d'ajuts, subvencions i licitacions de Stimulo.

Mòduls:
- dades: càrrega i validació del catàleg (data/*.yaml)
- zones: jerarquia geogràfica i elegibilitat per zona
- calendari: properes finestres (reals o estimades) i alertes
- puntuacio: encaix de cada convocatòria amb un perfil (Stimulo i clients de servei)
- informe: sortides (Markdown, CSV d'enviaments per zona, calendari .ics, HTML)
- excel: importador del recull d'ajuts en Excel (primer motor de cerca)
- vigilancia: vigilants de fonts obertes d'ajuts (BDNS, Funding & Tenders UE)
- licitacions: licitacions (PSCP, PLACSP, TED), semàfor go/no-go i fitxa de decisió
"""

__version__ = "0.1.0"
