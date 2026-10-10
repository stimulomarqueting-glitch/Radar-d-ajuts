"""Pla d'ajuts per a un horitzó concret (per defecte, de novembre de 2026 a juny de 2027) en dues línies:

1. **Projectes**: convocatòries que generen projectes de desenvolupament de producte amb clients i
   consorcis (Stimulo hi entra com a proveïdor, subcontractat o soci). És la línia amb més retorn
   comercial: s'ordena per retorn estimat i s'hi planifica la prospecció de clients.
2. **Creixement**: finançament per al creixement i la transformació de Stimulo (Stimulo sol·licitant):
   talent, R+D propi, cupons, internacionalització, finançament.

    python -m radar pla                         # sortida/pla-2026-2027.md i .html (sense dades de Holded)
    python -m radar pla --des 2026-11-01 --fins 2027-06-30
    python -m radar pla --privat                # privat/pla-…-clients: amb clients i socis de Holded

Horitzó per defecte: de l'1 de novembre (o avui, si ja ha passat) al 30 de juny següent.

El retorn estimat és un ordre de magnitud per prioritzar, no una previsió: projecte típic segons
l'import i la intensitat de la fitxa, per la part que sol correspondre a Stimulo segons el seu rol.
"""

from __future__ import annotations

import datetime as dt
import html
from dataclasses import dataclass, field
from pathlib import Path

from . import calendari, seguiment as mod_seguiment
from .dades import Cataleg, Convocatoria
from .puntuacio import Encaix, puntua

# Part del projecte que sol correspondre a Stimulo segons el rol (mínim, màxim) i sostre per projecte
QUOTA_ROL = {"proveidor_extern": (0.30, 0.60), "subcontractat": (0.15, 0.40), "soci": (0.05, 0.15)}
SOSTRE_ROL = {"proveidor_extern": 300_000, "subcontractat": 300_000, "soci": 500_000}
ORDRE_ROL = ("proveidor_extern", "subcontractat", "soci")
NOMS_ROL = {"proveidor_extern": "proveïdor", "subcontractat": "subcontractat", "soci": "soci de consorci"}
LLINDAR_ALT, LLINDAR_MITJA = 75_000, 20_000
NOMS_LINIA = {"projectes": "Projectes de producte amb clients i consorcis",
              "creixement": "Creixement i transformació de Stimulo"}
MESOS = ["gener", "febrer", "març", "abril", "maig", "juny", "juliol", "agost", "setembre", "octubre",
         "novembre", "desembre"]


@dataclass
class Retorn:
    minim: float
    maxim: float
    rol: str
    suposit: str

    @property
    def mig(self) -> float:
        return (self.minim + self.maxim) / 2

    @property
    def nivell(self) -> str:
        return "alt" if self.mig >= LLINDAR_ALT else "mitjà" if self.mig >= LLINDAR_MITJA else "baix"


@dataclass
class Fita:
    data: dt.date
    tipus: str  # prospectar / preparar / presentar / termini
    text: str
    c: Convocatoria
    linia: str = "projectes"
    ja: bool = False  # la data ideal ja ha passat: cal començar ara
    titol: str = ""  # el que es mostra en lloc del nom de la convocatòria (p. ex. un programa sencer)


@dataclass
class Entrada:
    c: Convocatoria
    f: calendari.Finestra
    e: Encaix
    linia: str
    retorn: Retorn | None = None
    fites: list[Fita] = field(default_factory=list)
    clients_servei: list[str] = field(default_factory=list)
    socis: list = field(default_factory=list)  # propostes de Holded (només a la versió privada)


@dataclass
class Pla:
    avui: dt.date
    inici: dt.date
    fi: dt.date
    projectes: list[Entrada]
    creixement: list[Entrada]
    vigilar: list[Entrada]  # anunciades sense dates
    ara: list[Entrada] = field(default_factory=list)  # tanquen abans de començar l'horitzó
    # Programes en seguiment actiu (p. ex. Cupons ACCIÓ): [(programa o None, [(convocatòria, estat)])]
    seguiment: list = field(default_factory=list)
    fites_seguiment: list[Fita] = field(default_factory=list)

    def fites(self) -> list[Fita]:
        """Fites sense repetir (una convocatòria a les dues línies comparteix el tancament i el termini)."""
        vistes, totes = set(), []
        for f in self.fites_seguiment:
            vistes.add((f.c.id, f.data, f.tipus))
            totes.append(f)
        for e in self.ara + self.projectes + self.creixement:
            for f in e.fites:
                clau = (f.c.id, f.data, f.tipus if f.tipus in ("presentar", "termini") else f.tipus + f.linia)
                if clau not in vistes:
                    vistes.add(clau)
                    totes.append(f)
        return sorted(totes, key=lambda f: (f.data, f.c.nom))

    def comencar_ja(self) -> list[Entrada]:
        """Entrades amb la feina prèvia endarrerida: s'hi ha de posar ara (per retorn i encaix)."""
        ids = {f.c.id for f in self.fites() if f.ja}
        vistes, sortida = {e.c.id for e in self.ara}, []
        for e in self.projectes + self.creixement:
            if e.c.id in ids and e.c.id not in vistes:
                vistes.add(e.c.id)
                sortida.append(e)
        return sortida

    def permanents(self) -> list[Entrada]:
        vistes, sortida = set(), []
        for e in self.projectes + self.creixement:
            if e.f.estat == "permanent" and e.c.id not in vistes:
                vistes.add(e.c.id)
                sortida.append(e)
        return sortida


def horitzo(avui: dt.date) -> tuple[dt.date, dt.date]:
    """Temporada de novembre a juny: la que ve (de juliol a octubre) o la que corre (de novembre a juny)."""
    any_ = avui.year if avui.month >= 7 else avui.year - 1
    return max(avui, dt.date(any_, 11, 1)), dt.date(any_ + 1, 6, 30)


def _eur(v: float) -> str:
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f} M€".replace(".", ",")
    return f"{round(v / 1000):,.0f} k€".replace(",", ".")


def retorn(c: Convocatoria) -> Retorn | None:
    """Retorn per projecte per a Stimulo a la línia de projectes (ordre de magnitud)."""
    rol = next((r for r in ORDRE_ROL if r in c.rols_stimulo), None)
    if c.retorn_eur:
        return Retorn(c.retorn_eur[0], c.retorn_eur[1], rol or "proveidor_extern", "fixat a la fitxa")
    if not rol:
        return None
    if c.import_max_eur:
        projecte_max = c.import_max_eur / (c.intensitat_max / 100) if c.intensitat_max else c.import_max_eur
        projecte_min = min(c.pressupost_min_eur or projecte_max / 3, projecte_max)
        base = ""
    elif c.pressupost_min_eur:
        projecte_min, projecte_max = c.pressupost_min_eur, c.pressupost_min_eur * 3
        base = " (a partir del pressupost mínim)"
    elif c.nivell == "europa" and "consorci" in c.beneficiaris:
        projecte_min, projecte_max = 2_000_000, 6_000_000
        base = " (projecte europeu en consorci típic)"
    else:
        return None
    qmin, qmax = QUOTA_ROL[rol]
    sostre = SOSTRE_ROL[rol]
    minim, maxim = min(projecte_min * qmin, sostre), min(projecte_max * qmax, sostre)
    suposit = (f"projecte de {_eur(projecte_min)} a {_eur(projecte_max)}{base}; part de Stimulo com a "
               f"{NOMS_ROL[rol]}: {qmin:.0%}–{qmax:.0%}" + (f", màxim {_eur(sostre)}" if maxim == sostre else ""))
    return Retorn(minim, maxim, rol, suposit)


def _dins(f: calendari.Finestra, fi: dt.date, avui: dt.date, marge: int) -> bool:
    """La finestra (o la feina prèvia, `marge` dies abans d'obrir) cau dins de l'horitzó."""
    if f.estat == "permanent":
        return True
    if f.estat == "oberta":
        return f.tancament is None or f.tancament >= avui
    if f.estat == "propera":
        a = f.obertura or f.tancament
        b = f.tancament or f.obertura
        return a is not None and a - dt.timedelta(days=marge) <= fi and (b is None or b >= avui)
    return False


MARGE = {"projectes": 90, "creixement": 45}  # dies de feina prèvia abans d'obrir


def _fites(en: Entrada, avui: dt.date) -> list[Fita]:
    """Calendari de feina d'una entrada. Les permanents no en tenen: surten a «Obertes tot l'any»."""
    c, f, li = en.c, en.f, en.linia
    if f.estat == "permanent":
        return []
    fites = []
    obre = f.obertura if f.estat == "propera" else None
    tanca = f.tancament
    if li == "projectes":
        inici = (obre - dt.timedelta(days=90)) if obre else (tanca - dt.timedelta(days=75) if tanca else avui)
        text = "Prospectar clients i socis i triar la idea de projecte"
        fites.append(Fita(max(avui, inici), "prospectar", text, c, li, ja=inici < avui))
        if obre and obre - dt.timedelta(days=30) > avui:
            fites.append(Fita(obre - dt.timedelta(days=30), "preparar", "Tancar client, consorci i pressupost", c, li))
    else:
        inici = (obre - dt.timedelta(days=45)) if obre else (tanca - dt.timedelta(days=45) if tanca else avui)
        fites.append(Fita(max(avui, inici), "preparar", "Preparar la sol·licitud de Stimulo", c, li, ja=inici < avui))
    if tanca and tanca >= avui:
        if tanca - dt.timedelta(days=7) > avui:
            fites.append(Fita(tanca - dt.timedelta(days=7), "presentar", "Tancament intern de la proposta", c, li))
        fites.append(Fita(tanca, "termini", "Termini" + (" (data estimada)" if f.estimada else ""), c, li))
    return fites


def construeix(cat: Cataleg, avui: dt.date, inici: dt.date, fi: dt.date, socis: list | None = None,
               clients: list | None = None) -> Pla:
    from .avisos import _clients_servei
    from .socis import proposa

    perfil = next(iter(cat.perfils.values()))
    projectes, creixement, vigilar, ara = [], [], [], []
    for c in cat.convocatories:
        if not c.linies or c.seguiment:  # les que estan en seguiment tenen el seu bloc
            continue
        f = calendari.propera_finestra(c, avui)
        e = puntua(c, perfil, cat.zones, cat.config.get("pesos"))
        anunciada = f.estat == "propera" and not f.obertura and not f.tancament
        abans = f.estat == "oberta" and f.tancament is not None and avui <= f.tancament < inici
        for linia in c.linies:
            if not (anunciada or _dins(f, fi, avui, MARGE[linia])):
                continue
            en = Entrada(c, f, e, linia)
            if linia == "projectes":
                en.retorn = retorn(c)
                en.clients_servei = _clients_servei(c, cat, clients or [])
                if socis:
                    en.socis = proposa(c, socis, cat.zones, 5)
            if anunciada:
                if c.id not in {x.c.id for x in vigilar}:
                    vigilar.append(en)
                continue
            if abans:
                if c.id not in {x.c.id for x in ara} and (linia == "projectes" or e.prioritat in ("A", "B")):
                    en.fites = _fites(en, avui)
                    ara.append(en)
                continue
            en.fites = _fites(en, avui)
            (projectes if linia == "projectes" else creixement).append(en)
    projectes.sort(key=lambda x: (-(x.retorn.mig if x.retorn else 0), -x.e.punts))
    creixement.sort(key=lambda x: (-x.e.punts, x.f.tancament or dt.date.max))
    # De la línia de creixement només interessen les que Stimulo pot demanar (prioritat A o B)
    creixement = [x for x in creixement if x.e.prioritat in ("A", "B")]
    vigilar.sort(key=lambda x: (x.linia != "projectes", -x.e.punts))
    ara.sort(key=lambda x: x.f.tancament or dt.date.max)
    segs = mod_seguiment.per_programa(cat, avui)
    return Pla(avui, inici, fi, projectes, creixement, vigilar, ara, segs, _fites_seguiment(segs, avui, fi))


def _fites_seguiment(segs: list, avui: dt.date, fi: dt.date) -> list[Fita]:
    """Obertures i terminis dels programes en seguiment, una fita per programa i data."""
    grups: dict[tuple, list[Convocatoria]] = {}
    for programa, modalitats in segs:
        for c, e in modalitats:
            if e.f.estat == "propera" and e.f.obertura and avui <= e.f.obertura <= fi:
                grups.setdefault((programa.id if programa else c.id, e.f.obertura, "preparar"), []).append(c)
            if e.f.estat in ("oberta", "propera") and e.f.tancament and avui <= e.f.tancament <= fi:
                grups.setdefault((programa.id if programa else c.id, e.f.tancament, "termini"), []).append(c)
    noms = {(programa.id if programa else ms[0][0].id): programa for programa, ms in segs if ms}
    fites = []
    for (clau, data, tipus), cs in grups.items():
        programa = noms.get(clau)
        titol = (f"{programa.nom} ({', '.join(mod_seguiment.nom_curt(c) for c in cs)})" if programa else cs[0].nom)
        text = ("Obren: tenir les sol·licituds a punt (ordre d'entrada)" if tipus == "preparar"
                else "Termini" + (" (o quan s'exhaureixi el pressupost)" if cs[0].instrument == "cupo" else ""))
        fites.append(Fita(data, tipus, text, cs[0], cs[0].linies[0] if cs[0].linies else "projectes", titol=titol))
    return fites


# --- Sortides -------------------------------------------------------------------------------------

def _finestra(f: calendari.Finestra) -> str:
    m = "≈ " if f.estimada else ""
    if f.estat == "permanent":
        return "Oberta tot l'any"
    if f.estat == "oberta":
        return f"Oberta fins al {m}{f.tancament:%d/%m/%Y}" if f.tancament else "Oberta"
    if f.obertura and f.tancament:
        return f"{m}{f.obertura:%d/%m/%Y} → {f.tancament:%d/%m/%Y}"
    if f.tancament:
        return f"Termini {m}{f.tancament:%d/%m/%Y}"
    if f.obertura:
        return f"Obre el {m}{f.obertura:%d/%m/%Y}"
    return "Anunciada (dates per confirmar)"


def _retorn_text(r: Retorn | None) -> str:
    if not r:
        return "per estimar"
    interval = f"≈ {_eur(r.maxim)}" if r.minim == r.maxim else f"{_eur(r.minim)}–{_eur(r.maxim)}"
    return f"{interval} ({r.nivell})"


def resum(pla: Pla) -> dict:
    alts = [e for e in pla.projectes if e.retorn and e.retorn.nivell == "alt"]
    return {"projectes": len(pla.projectes), "alt": len(alts), "creixement": len(pla.creixement),
            "comencar_ja": len(pla.comencar_ja()),
            "seguiment_obertes": sum(1 for _p, ms in pla.seguiment for _c, e in ms if e.f.estat == "oberta"),
            "terminis_30": sum(1 for f in pla.fites() if f.tipus == "termini" and 0 <= (f.data - pla.avui).days <= 30)}


def mesos(pla: Pla) -> list[tuple[str, list[Fita]]]:
    """Fites amb data per mes. Les de «començar ja» no hi surten: tenen la seva llista."""
    sortida: dict[str, list[Fita]] = {}
    for f in pla.fites():
        if f.data > pla.fi or f.ja:
            continue
        sortida.setdefault(f"{MESOS[f.data.month - 1]} {f.data.year}", []).append(f)
    return list(sortida.items())


def _socis_text(e: Entrada) -> str:
    return "; ".join([f"{p.soci.nom} ({p.rol})" for p in e.socis] + e.clients_servei)


COM_ES_CALCULA = ("Ordre de magnitud per prioritzar: mida típica del projecte segons l'import màxim i la intensitat de "
                  "la fitxa, per la part que sol correspondre a Stimulo segons el rol (proveïdor 30–60 %, subcontractat "
                  "15–40 %, soci de consorci 5–15 %), amb un sostre per projecte. Alt ≥ 75 k€, mitjà ≥ 20 k€ (punt mitjà "
                  "de l'interval). Una mateixa convocatòria pot donar diversos projectes amb clients diferents.")


def markdown(pla: Pla, privat: bool = False) -> str:
    r = resum(pla)
    t = [f"# Pla d'ajuts {pla.inici:%m/%Y}–{pla.fi:%m/%Y}", "",
         f"_Generat el {pla.avui:%d/%m/%Y}. Dues línies de treball; la de projectes té més retorn comercial "
         "i va primer._", "",
         f"- **{r['projectes']}** convocatòries per generar projectes amb clients i consorcis "
         f"({r['alt']} amb retorn alt).",
         f"- **{r['creixement']}** per al creixement de Stimulo.",
         f"- **{r['comencar_ja']}** on cal començar ja la feina prèvia; **{r['terminis_30']}** terminis en 30 dies.", ""]
    if pla.ara:
        t += [f"## Ara mateix: tanquen abans del {pla.inici:%d/%m/%Y}", ""]
        t += [f"- {e.c.nom} ({e.c.entitat}) · {_finestra(e.f)} · línia de {e.linia}" for e in pla.ara] + [""]
    for programa, modalitats in pla.seguiment:
        nom = programa.nom if programa else modalitats[0][0].nom
        t += [f"## En seguiment: {nom}", ""]
        if programa and programa.regles:
            t += [f"_{programa.regles[0]}_", ""]
        t += [f"- **{mod_seguiment.nom_curt(c)}** · {e.etiqueta.lower()}: {e.text} · {c.ajuda_text or '—'}"
              for c, e in modalitats] + [""]
    if pla.comencar_ja():
        t += ["## Començar ja", "", "La feina prèvia ideal (prospectar ≈ 90 dies abans d'obrir, o preparar ≈ 45) "
              "ja hauria d'haver començat:", ""]
        for e in pla.comencar_ja():
            extra = f" · retorn {_retorn_text(e.retorn)}" if e.linia == "projectes" else ""
            t.append(f"- **{e.c.nom}** ({e.c.entitat}) · {_finestra(e.f)} · línia de {e.linia}{extra}")
        t.append("")
    t += [f"## 1. {NOMS_LINIA['projectes']}", "",
          "| Convocatòria | Finestra | Rol de Stimulo | Retorn per projecte | Encaix |", "|---|---|---|---|---|"]
    for e in pla.projectes:
        t.append(f"| {e.c.nom} ({e.c.entitat}) | {_finestra(e.f)} | "
                 f"{NOMS_ROL.get(e.retorn.rol, '—') if e.retorn else '—'} | {_retorn_text(e.retorn)} | "
                 f"{e.e.punts} {e.e.prioritat} |")
    if privat:
        t += ["", "### Clients i socis de Holded per a cada convocatòria", ""]
        t += [f"- **{e.c.nom}:** {_socis_text(e)}" for e in pla.projectes if e.socis or e.clients_servei]
    t += ["", f"## 2. {NOMS_LINIA['creixement']}", "",
          "| Convocatòria | Finestra | Ajut | Encaix |", "|---|---|---|---|"]
    for e in pla.creixement:
        t.append(f"| {e.c.nom} ({e.c.entitat}) | {_finestra(e.f)} | {e.c.ajuda_text or '—'} | "
                 f"{e.e.punts} {e.e.prioritat} |")
    if pla.permanents():
        t += ["", "## Obertes tot l'any", "", "Sense calendari: es poden proposar a cada conversa amb clients.", ""]
        t += [f"- {e.c.nom} ({e.c.entitat}) · línia de {e.linia}" for e in pla.permanents()]
    t += ["", "## Accions mes a mes", ""]
    for mes, fites in mesos(pla):
        t += [f"### {mes.capitalize()}", ""] + [f"- {f.data:%d/%m} · {f.text}: **{f.titol or f.c.nom}**"
                                                 for f in fites] + [""]
    if pla.vigilar:
        t += ["## Anunciades, a vigilar", ""]
        t += [f"- {e.c.nom} ({e.c.entitat}) · línia de {e.linia}" for e in pla.vigilar] + [""]
    t += ["## Com es calcula el retorn", "", COM_ES_CALCULA, ""]
    return "\n".join(t)



def _e(x) -> str:
    return html.escape(str(x or ""), quote=True)


CSS_EXTRA = """
.linia-cap { display: flex; flex-wrap: wrap; gap: 6px 14px; align-items: baseline; }
.nivell { font: 600 12px/1 var(--f-body); padding: 4px 7px; border-radius: 5px; white-space: nowrap; }
.n-alt { background: var(--ok-soft); color: var(--ok); }
.n-mitjà { background: var(--accent-soft); color: var(--accent); }
.n-baix, .n-cap { background: var(--off-soft); color: var(--muted); }
td small { display: block; color: var(--muted); font-size: 12px; }
.mesos { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
.mes { background: var(--surface); border: 1px solid var(--line); border-radius: var(--r); padding: 14px 16px; display: grid; gap: 8px; align-content: start; }
.mes h3 { font-size: 16px; text-transform: capitalize; }
.mes ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; font-size: 13px; }
.mes li { display: grid; grid-template-columns: 44px minmax(0, 1fr); gap: 8px; }
.mes time { font: 500 12px/1.4 var(--f-mono); color: var(--muted); }
.t-prospectar { color: var(--ok); font-weight: 600; }
.t-termini { color: var(--warn); font-weight: 600; }
.t-preparar, .t-presentar { color: var(--accent); font-weight: 600; }
.tag-linia { font: 500 10px/1 var(--f-mono); letter-spacing: .05em; text-transform: uppercase; padding: 3px 5px; border-radius: 4px; }
.tag-projectes { background: var(--ok-soft); color: var(--ok); }
.tag-creixement { background: var(--accent-soft); color: var(--accent); }
.tornar { margin: 0 0 8px; font-size: 14px; }
"""


def _llista(entrades: list[Entrada], detall) -> str:
    return '<ul class="missatges">' + "".join(
        f'<li><b>{_e(e.c.nom)}</b><span>{_e(detall(e))}</span></li>' for e in entrades) + "</ul>"


def informe_html(pla: Pla, privat: bool = False, app: bool = False) -> str:
    """`app`: dins de l'aplicació (enllaç al tauler i botons per obrir una sol·licitud)."""
    from .screening import CSS

    r = resum(pla)
    titol = f"Pla d'ajuts {pla.inici.year}-{pla.fi.year}"
    h = [f"<title>{_e(titol)}</title>",
         '<link rel="preconnect" href="https://fonts.googleapis.com">',
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500'
         '&family=IBM+Plex+Sans:wght@400;500;600&family=Schibsted+Grotesk:wght@600;800&display=swap">',
         f"<style>{CSS}\n{CSS_EXTRA}</style>", '<main class="informe">',
         ('<p class="tornar"><a href="/">← Tauler</a></p>' if app else ""),
         '<header class="cap"><span class="eti">Stimulo · Radar d\'ajuts</span>'
         f'<h1>{_e(titol)}: dues línies de treball</h1>'
         f'<p class="sub">De {MESOS[pla.inici.month - 1]} de {pla.inici.year} a {MESOS[pla.fi.month - 1]} de '
         f'{pla.fi.year}. La línia de projectes amb clients i consorcis va primer: és la que té més retorn '
         'comercial. La de creixement recull el finançament per a Stimulo.</p>'
         f'<div class="meta"><span>Generat el <b>{pla.avui:%d/%m/%Y}</b></span></div></header>',
         '<section class="seccio"><div class="xifres">'
         f'<div><b>{r["projectes"]}</b><span>convocatòries per a projectes amb clients</span></div>'
         f'<div><b>{r["alt"]}</b><span>amb retorn alt (≥ 75 k€ per projecte)</span></div>'
         f'<div><b>{r["creixement"]}</b><span>per al creixement de Stimulo</span></div>'
         f'<div><b>{r["comencar_ja"]}</b><span>on cal començar ja</span></div></div></section>']

    if pla.ara:
        h.append(f'<section class="seccio"><header><span class="eti">Abans del {pla.inici:%d/%m/%Y}</span>'
                 '<h2>Ara mateix</h2><p class="sub">Obertes i tanquen abans de començar l\'horitzó: '
                 'decidir aquesta setmana si s\'hi va.</p></header>'
                 + _llista(pla.ara, lambda e: f"{_finestra(e.f)} · {e.c.entitat} · línia de {e.linia}")
                 + "</section>")
    for programa, modalitats in pla.seguiment:
        nom = programa.nom if programa else modalitats[0][0].nom
        regla = f'<p class="sub">{_e(programa.regles[0])}</p>' if programa and programa.regles else ""
        enllac = (f'<p class="sub"><a href="{_e(programa.url)}" target="_blank" rel="noopener">Pàgina oficial ↗</a>'
                  + (' · <a href="/seguiment">Seguiment a l\'aplicació</a>' if app else "") + "</p>"
                  if programa and programa.url else "")
        h.append(f'<section class="seccio"><header><span class="eti">En seguiment</span><h2>{_e(nom)}</h2>{regla}'
                 f'{enllac}</header><div class="taula-embolcall"><table><thead><tr><th>Modalitat</th><th>Estat</th>'
                 '<th>Ajut</th><th>Línia</th></tr></thead><tbody>')
        for c, e in modalitats:
            classe = "n-alt" if e.f.estat == "oberta" else "n-mitjà" if e.f.estat == "propera" else "n-cap"
            h.append(f'<tr><td class="nom"><b>{_e(mod_seguiment.nom_curt(c))}</b></td>'
                     f'<td><span class="nivell {classe}">{_e(e.etiqueta)}</span><small>{_e(e.text)}</small></td>'
                     f'<td>{_e(c.ajuda_text or "—")}</td><td>{_e(", ".join(c.linies))}</td></tr>')
        h.append("</tbody></table></div></section>")
    if pla.comencar_ja():
        h.append('<section class="seccio"><header><h2>Començar ja</h2><p class="sub">La feina prèvia ideal '
                 '(prospectar clients ≈ 90 dies abans d\'obrir, o preparar la sol·licitud ≈ 45) ja hauria d\'haver '
                 'començat.</p></header>'
                 + _llista(pla.comencar_ja(), lambda e: f"{_finestra(e.f)} · línia de {e.linia}"
                           + (f" · retorn {_retorn_text(e.retorn)}" if e.linia == "projectes" else ""))
                 + "</section>")

    # Línia 1: projectes
    h.append(f'<section class="seccio"><header><span class="eti">Línia 1 · més retorn comercial</span>'
             f'<h2>{_e(NOMS_LINIA["projectes"])}</h2><p class="sub">Convocatòries on el client o el consorci '
             'demana l\'ajut i Stimulo fa el desenvolupament de producte. Ordenades per retorn estimat per projecte.'
             '</p></header><div class="taula-embolcall"><table><thead><tr><th>Convocatòria</th><th>Finestra</th>'
             '<th>Rol</th><th>Retorn per projecte</th>' + ("<th>Clients i socis (Holded)</th>" if privat else "")
             + '<th>Encaix</th></tr></thead><tbody>')
    for e in pla.projectes:
        nivell = e.retorn.nivell if e.retorn else "cap"
        socis = ""
        if privat:
            noms = [p.soci.nom for p in e.socis[:4]] + e.clients_servei[:2]
            socis = f"<td>{_e(', '.join(noms) or '—')}</td>"
        obre = (f'<small><a href="/expedients/nou?convocatoria={_e(e.c.id)}">Preparar sol·licitud</a></small>'
                if app else "")
        h.append(f'<tr><td class="nom"><b>{_e(e.c.nom)}</b><small>{_e(e.c.entitat)}</small>{obre}</td>'
                 f'<td>{_e(_finestra(e.f))}</td>'
                 f'<td>{_e(NOMS_ROL.get(e.retorn.rol, "—") if e.retorn else "—")}</td>'
                 f'<td><span class="nivell n-{nivell}">{_e(_retorn_text(e.retorn))}</span>'
                 f'{"<small>" + _e(e.retorn.suposit) + "</small>" if e.retorn else ""}</td>{socis}'
                 f'<td class="punt">{e.e.punts} {e.e.prioritat}</td></tr>')
    h.append("</tbody></table></div></section>")

    # Línia 2: creixement
    h.append(f'<section class="seccio"><header><span class="eti">Línia 2</span>'
             f'<h2>{_e(NOMS_LINIA["creixement"])}</h2><p class="sub">Ajuts que Stimulo pot demanar per a ella mateixa: '
             'talent, R+D propi, cupons, internacionalització i finançament. Només les de prioritat A o B.</p></header>'
             '<div class="taula-embolcall"><table><thead><tr><th>Convocatòria</th><th>Finestra</th><th>Ajut</th>'
             '<th>Encaix</th></tr></thead><tbody>')
    for e in pla.creixement:
        h.append(f'<tr><td class="nom"><b>{_e(e.c.nom)}</b><small>{_e(e.c.entitat)}</small></td>'
                 f'<td>{_e(_finestra(e.f))}</td><td>{_e(e.c.ajuda_text or "—")}</td>'
                 f'<td class="punt">{e.e.punts} {e.e.prioritat}</td></tr>')
    h.append("</tbody></table></div></section>")

    if pla.permanents():
        h.append('<section class="seccio"><header><h2>Obertes tot l\'any</h2><p class="sub">Sense calendari: es '
                 'poden proposar a cada conversa amb clients.</p></header>'
                 + _llista(pla.permanents(), lambda e: f"{e.c.entitat} · línia de {e.linia}") + "</section>")

    # Accions mes a mes
    h.append('<section class="seccio"><header><h2>Accions mes a mes</h2><p class="sub">Prospectar clients ≈ 90 dies '
             'abans de l\'obertura; tancar client i pressupost 30 dies abans; tancament intern 7 dies abans del '
             'termini.</p></header><div class="mesos">')
    for mes, fites in mesos(pla):
        h.append(f'<div class="mes"><h3>{_e(mes)}</h3><ul>')
        for f in fites:
            h.append(f'<li><time>{f.data:%d/%m}</time><span><span class="tag-linia tag-{f.linia}">{f.linia}</span> '
                     f'<span class="t-{f.tipus}">{_e(f.text)}</span>: {_e(f.titol or f.c.nom)}</span></li>')
        h.append("</ul></div>")
    h.append("</div></section>")

    if pla.vigilar:
        h.append('<section class="seccio"><header><h2>Anunciades, a vigilar</h2></header>'
                 + _llista(pla.vigilar, lambda e: f"{e.c.entitat} · línia de {e.linia}") + "</section>")
    h.append(f"<footer><p>Retorn per projecte: {_e(COM_ES_CALCULA)} Les dates amb ≈ són estimades.</p>"
             "</footer></main>")
    return "\n".join(h)



def pagina(cos: str) -> str:
    return ('<!doctype html>\n<html lang="ca">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            + cos.replace("</style>", "</style>\n</head>\n<body>", 1) + "\n</body>\n</html>\n")


def genera(pla: Pla, dir_sortida: Path, privat: bool = False) -> dict[str, Path]:
    dir_sortida.mkdir(parents=True, exist_ok=True)
    base = f"pla-{pla.inici.year}-{pla.fi.year}" + ("-clients" if privat else "")
    fitxers = {"md": dir_sortida / f"{base}.md", "html": dir_sortida / f"{base}.html"}
    fitxers["md"].write_text(markdown(pla, privat), encoding="utf-8")
    fitxers["html"].write_text(pagina(informe_html(pla, privat)), encoding="utf-8")
    return fitxers
