"""Documents que l'assistent pot redactar per a cada expedient de sol·licitud.

Cada plantilla és una instrucció que s'envia com un torn de la conversa: així l'assistent té
present tot el que s'ha parlat abans. La resposta (Markdown) es desa com a versió del document.
"""

from __future__ import annotations

from dataclasses import dataclass

INSTRUCCIONS_COMUNES = (
    "Escriu el document complet en Markdown, a punt per enganxar a la sol·licitud, sense preàmbul ni "
    "comentaris abans o després. Fes servir l'estructura i els apartats que demanen les bases de la "
    "convocatòria (si no les tens, busca-les a la font oficial; si no les trobes, fes servir l'estructura "
    "habitual del programa i digues-ho en una nota final). No t'inventis xifres, dades ni compromisos: on "
    "falti informació escriu [PENDENT: què cal]. Acaba amb un apartat «Preguntes per completar» amb les "
    "preguntes concretes que cal respondre per tancar el document."
)


@dataclass(frozen=True)
class Plantilla:
    tipus: str
    titol: str
    descripcio: str
    instruccio: str


PLANTILLES = [
    Plantilla("encaix", "Anàlisi d'elegibilitat i encaix",
              "Requisits, punts forts, riscos i decisió hi anem / no hi anem",
              "Analitza si Stimulo i els socis compleixen tots els requisits d'elegibilitat de la convocatòria "
              "(tipus d'entitat, ubicació, mida, règim d'ajuts, pressupost mínim, terminis, incompatibilitats). "
              "Fes una taula requisit → compleix / no compleix / per verificar, amb la font. Després valora "
              "l'encaix (punts forts i febles respecte als criteris d'avaluació) i acaba amb una recomanació "
              "clara: hi anem, hi anem amb condicions o no hi anem."),
    Plantilla("fitxa", "Fitxa de projecte",
              "Una pàgina: repte, solució, objectius, TRL, socis i pressupost",
              "Redacta la fitxa de projecte d'una pàgina: títol, acrònim, repte, solució proposada, "
              "objectius mesurables, TRL inicial i final, socis i rols, durada, pressupost estimat i ajut "
              "sol·licitat."),
    Plantilla("memoria", "Memòria tècnica",
              "El document principal, amb els apartats que avaluen",
              "Redacta la memòria tècnica completa seguint els criteris d'avaluació de la convocatòria: "
              "antecedents i estat de l'art, objectius, innovació i grau de novetat, metodologia, pla de "
              "treball resumit, capacitat de l'equip i dels socis, resultats esperats, impacte i explotació."),
    Plantilla("pla_treball", "Pla de treball i cronograma",
              "Paquets de treball, tasques, fites, entregables i Gantt",
              "Redacta el pla de treball: paquets de treball amb objectius, tasques, responsable, durada, "
              "fites i entregables, i un cronograma en taula (mesos) compatible amb la durada màxima de la "
              "convocatòria."),
    Plantilla("pressupost", "Pressupost i justificació",
              "Partides elegibles, imports per soci i justificació",
              "Prepara el pressupost per partides elegibles segons les bases (personal, col·laboracions "
              "externes, materials, amortitzacions, indirectes...), per soci, amb el càlcul de l'ajut segons la "
              "intensitat aplicable i una justificació breu de cada partida. Indica quines despeses no són "
              "elegibles i els requisits de justificació (tres ofertes, timesheets, auditoria)."),
    Plantilla("impacte", "Impacte, explotació i DNSH",
              "Mercat, explotació, sostenibilitat i autoavaluació DNSH",
              "Redacta l'apartat d'impacte i pla d'explotació (mercat, model de negoci, propietat "
              "intel·lectual, escalat) i l'autoavaluació DNSH (no causar un perjudici significatiu) per als sis "
              "objectius ambientals, si la convocatòria ho demana."),
    Plantilla("consorci", "Socis i cartes de compromís",
              "Rols de cada soci i esborranys de cartes de suport",
              "Defineix el rol, l'aportació i el pressupost orientatiu de cada soci, i redacta un esborrany de "
              "carta de compromís o de suport per a cadascun, a punt per signar."),
    Plantilla("correus", "Correus als socis",
              "Missatges per convidar o coordinar els socis",
              "Redacta un correu per a cada soci (en català si és de Catalunya, en castellà si no) per "
              "proposar-li participar o per demanar-li la informació que falta, amb terminis clars."),
    Plantilla("resum", "Resum executiu",
              "Abstract curt per a formularis i presentacions",
              "Redacta el resum executiu (màxim 2.000 caràcters) i una versió curta de 500 caràcters, en "
              "l'idioma que demanin les bases (si són europees, en anglès)."),
    Plantilla("checklist", "Checklist i calendari intern",
              "Documents administratius, signatures i dates internes",
              "Fes la checklist de tota la documentació que cal presentar (administrativa i tècnica), qui la "
              "prepara, i un calendari intern amb el tancament intern 7 dies abans del termini oficial, les "
              "signatures i les validacions dels socis."),
]

PER_TIPUS = {p.tipus: p for p in PLANTILLES}


def instruccio(tipus: str) -> str:
    p = PER_TIPUS[tipus]
    return f"Prepara el document «{p.titol}». {p.instruccio}\n\n{INSTRUCCIONS_COMUNES}"
