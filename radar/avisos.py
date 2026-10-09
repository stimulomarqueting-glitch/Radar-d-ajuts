"""Avís per correu quan surt una línia d'ajuts nova amb potencial per a Stimulo.

Per a cada línia nova (prioritat A, o B amb dates properes) l'avís inclou: inici, finalització,
import, descripció, per què encaixem, socis potencials de Holded i altres consideracions. També
inclou un esborrany de correu per a cada soci, a punt per revisar i enviar.

Cada edició d'una convocatòria s'avisa una sola vegada (estat a data/estat/notificades.json, que
només conté identificadors de convocatòries; cap dada de contactes).
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import smtplib
import ssl
import urllib.parse
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path

from . import calendari
from .dades import Cataleg, Convocatoria
from .puntuacio import Encaix, puntua
from .socis import Proposta, Soci, nom_des_del_correu, proposa

NOMS_FOCUS = {
    "deep_tech": "deep tech", "dual": "ús dual", "defensa": "defensa", "espai": "espai",
    "sostenibilitat": "sostenibilitat", "economia_circular": "economia circular", "transferencia": "transferència",
    "prova_concepte": "prova de concepte", "mobilitat": "mobilitat", "automocio": "automoció",
    "robotica": "robòtica", "agrotech": "agrotech", "aigua": "aigua", "salut": "salut",
    "dispositius_medics": "dispositius mèdics", "fotonica": "fotònica", "digital": "digital", "ia": "IA",
    "industria": "indústria", "energia": "energia", "internacionalitzacio": "internacionalització",
    "creixement_startup": "creixement de startups", "talent": "talent", "disseny": "disseny",
    "cooperacio": "cooperació",
}
NOMS_ROL = {"beneficiari": "beneficiari", "soci": "soci de consorci", "proveidor_extern": "proveïdor / agent extern",
            "subcontractat": "subcontractat", "assessor": "assessor"}
NOMS_TIPUS = {"recerca": "recerca", "hospital": "hospital / institut sanitari", "empresa": "empresa",
              "startup": "startup", "cluster": "clúster", "inversor": "inversor"}
CONFIG_PER_DEFECTE = {"prioritats": ["A"], "prioritat_b_dies": 45, "antelacio_dies": 60, "maxim_linies": 8,
                      "maxim_socis": 3, "maxim_socis_clients": 5, "remitent_nom": "Radar d'ajuts Stimulo",
                      "signatura": "Xavi\nStimulo · stimulo.com"}


@dataclass
class Linia:
    c: Convocatoria
    f: calendari.Finestra
    e: Encaix
    clau: str
    motiu: str
    propostes: list[Proposta] = field(default_factory=list)
    per_clients: bool = False  # línia per compartir amb clients i potencials clients
    clients_servei: list[str] = field(default_factory=list)  # divisions de clients de servei amb encaix A/B


def _data(d: dt.date | None, estimada: bool = False) -> str:
    if not d:
        return ""
    return ("≈ " if estimada else "") + f"{d:%d/%m/%Y}"


def _eur(v: float | None) -> str:
    if v is None:
        return ""
    if v >= 1_000_000:
        return f"{v / 1_000_000:,.1f} M€".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{v:,.0f} €".replace(",", ".")


def clau_edicio(c: Convocatoria, f: calendari.Finestra, avui: dt.date) -> str:
    if f.estat == "permanent":
        return f"{c.id}|permanent"
    referencia = f.obertura or f.tancament or avui
    return f"{c.id}|{referencia.year}"


def _motiu(f: calendari.Finestra, avui: dt.date) -> str:
    if f.estat == "permanent":
        return "Oberta tot l'any"
    if f.estat == "oberta":
        return "Oberta ara (verificar a la font)" if f.estimada else "Oberta ara"
    if f.obertura:
        dies = (f.obertura - avui).days
        return f"Obre d'aquí a {dies} dies" + (" (data estimada)" if f.estimada else "")
    if f.tancament:
        return f"Propera data límit: {f.tancament:%d/%m/%Y}"
    return "Anunciada: dates pendents"


def _clients_servei(c: Convocatoria, cat: Cataleg, clients: list) -> list[str]:
    """Divisions de clients de servei (data/clients) amb encaix A o B per a la línia."""
    sortida = []
    for cl in clients:
        for d in cl.divisions:
            e = puntua(c, d.perfil, cat.zones, cat.config.get("pesos"))
            if e.prioritat in ("A", "B") and e.rol:
                sortida.append(f"{cl.nom} · {d.nom} ({e.punts} {e.prioritat})")
    return sortida


def candidates(cat: Cataleg, avui: dt.date, config: dict | None = None, clients: list | None = None) -> list[Linia]:
    """Línies amb potencial ara mateix (sense mirar l'estat de notificacions).

    Hi entren les de prioritat alta per a Stimulo, les marcades per compartir amb clients
    (`compartir_clients`) i les que encaixen amb una divisió d'un client de servei (`clients`).
    """
    cfg = {**CONFIG_PER_DEFECTE, **(config or {})}
    perfil = next(iter(cat.perfils.values()))  # el radar puntua per a Stimulo (primer perfil actiu)
    clients = clients or []
    sortida = []
    for c in cat.convocatories:
        f = calendari.propera_finestra(c, avui)
        if f.estat in ("tancada", "sense_dades"):
            continue
        e = puntua(c, perfil, cat.zones, cat.config.get("pesos"))
        referencia = f.tancament if f.estat == "oberta" else (f.obertura or f.tancament)
        dies = (referencia - avui).days if referencia else None
        if f.estat == "propera" and f.obertura and (f.obertura - avui).days > cfg["antelacio_dies"]:
            continue  # encara massa lluny: ja s'avisarà quan s'acosti
        if f.estat == "propera" and not f.obertura and f.tancament \
                and (f.tancament - avui).days > cfg["antelacio_dies"] + 45:
            continue  # tall llunyà d'una convocatòria que encara no ha obert
        servei = _clients_servei(c, cat, clients)
        per_stimulo = e.prioritat in cfg["prioritats"] or (
            e.prioritat == "B" and dies is not None and 0 <= dies <= cfg["prioritat_b_dies"])
        if not (per_stimulo or c.compartir_clients or servei):
            continue
        sortida.append(Linia(c, f, e, clau_edicio(c, f, avui), _motiu(f, avui),
                             per_clients=c.compartir_clients or bool(servei), clients_servei=servei))
    # Primer les línies amb dates (les fitxes fiables abans que les pendents de verificar, i per encaix);
    # les obertes tot l'any, al final
    sortida.sort(key=lambda l: (l.f.estat == "permanent", l.c.confianca == "baixa", -l.e.punts,
                                (l.f.tancament if l.f.estat == "oberta" else l.f.obertura) or dt.date.max))
    return sortida


def linia(cat: Cataleg, c: Convocatoria, avui: dt.date) -> Linia:
    """Una línia concreta, encara que no passi els filtres de l'avís (per a l'aplicació web)."""
    f = calendari.propera_finestra(c, avui)
    e = puntua(c, next(iter(cat.perfils.values())), cat.zones, cat.config.get("pesos"))
    return Linia(c, f, e, clau_edicio(c, f, avui), _motiu(f, avui))


def noves(linies: list[Linia], estat: dict) -> list[Linia]:
    return [l for l in linies if l.clau not in estat]


def afegeix_socis(linies: list[Linia], socis: list[Soci], cat: Cataleg, maxim: int,
                  maxim_clients: int | None = None) -> None:
    """Socis de Holded per a cada línia; a les línies per a clients, més empreses (clients i contactes)."""
    for l in linies:
        l.propostes = proposa(l.c, socis, cat.zones, (maxim_clients or maxim) if l.per_clients else maxim)


# --- Redacció ----------------------------------------------------------------------------------

def _encaix(l: Linia) -> str:
    if l.c.encaix_stimulo:
        return l.c.encaix_stimulo
    rols = ", ".join(NOMS_ROL.get(r, r) for r in l.c.rols_stimulo) or "per definir"
    temes = [m[7:] for m in l.e.motius if m.startswith("temes: ")]
    temes_txt = ", ".join(NOMS_FOCUS.get(t, t) for t in temes[0].split(", ")) if temes else ""
    frase = f"Stimulo hi pot entrar com a {rols}."
    if temes_txt:
        frase += f" Encaixa amb els nostres àmbits: {temes_txt}."
    if l.c.trl:
        frase += f" Maduresa TRL {l.c.trl[0]}–{l.c.trl[1]}."
    return frase


def _consideracions(l: Linia) -> list[str]:
    punts = list(l.c.punts_forts)
    if l.c.intensitat_max and l.c.intensitat_max >= 70 and not any("%" in p for p in punts):
        punts.append(f"Intensitat alta: fins al {l.c.intensitat_max:g} %.")
    if "dual" in l.c.focus and not any("dual" in p.lower() for p in punts):
        punts.append("Admet tecnologies d'ús dual.")
    if l.f.estimada and (l.f.obertura or l.f.tancament):
        punts.append("Dates estimades a partir de l'edició anterior: confirmar-les a la font oficial.")
    elif not (l.f.obertura or l.f.tancament) and l.f.estat != "permanent":
        punts.append("Encara sense dates oficials: el radar ho tornarà a revisar i avisarà quan es publiquin.")
    if l.c.confianca == "baixa":
        punts.append("Fitxa amb dades pendents de verificar.")
    return punts


def _motius(motius: list[str]) -> str:
    sortida = []
    for m in motius:
        if m.startswith("temes: "):
            m = "temes: " + ", ".join(NOMS_FOCUS.get(x, x) for x in m[7:].split(", "))
        sortida.append(m)
    return "; ".join(sortida)


def _primer_nom(nom: str) -> str:
    parts = [p for p in nom.replace("'", "").split() if p]
    return parts[0].capitalize() if parts else ""


def esborrany(l: Linia, p: Proposta, signatura: str) -> dict:
    """Correu per al soci potencial: català si és a Catalunya, castellà a la resta."""
    s, c, f = p.soci, l.c, l.f
    dest = s.destinatari or {}
    catala = (s.zona or "").startswith("ES-CT") or (dest.get("email", "").endswith(".cat"))
    nom = _primer_nom(dest.get("nom", "")) or (nom_des_del_correu(dest["email"]) if dest.get("email") and not dest.get("generic") else "")
    inici = _data(f.obertura, f.estimada) or ("oberta" if f.estat in ("oberta", "permanent") else "per confirmar")
    final = _data(f.tancament, f.estimada) or ("tot l'any" if f.estat == "permanent" else "per confirmar")
    ajut = c.ajuda_text or _eur(c.import_max_eur)
    temes = ", ".join(NOMS_FOCUS.get(t, t) for t in c.focus if t in s.focus)
    if catala:
        salutacio = f"Hola {nom}," if nom else f"Hola, equip de {s.nom},"
        if p.rol.startswith("sol·licitant") and "proveïdor" in p.rol:
            rol = ("Vosaltres en podríeu ser els sol·licitants i Stimulo hi participaria com a agent tecnològic: "
                   "disseny, prototip i validació. També us podem ajudar a preparar la proposta.")
        elif s.tipus in ("recerca", "hospital"):
            rol = ("Estem valorant muntar-hi un consorci i creiem que el vostre grup hi encaixa"
                   + (f" ({temes})" if temes else "") + ". Stimulo aportaria el disseny i el desenvolupament de producte.")
        elif s.tipus == "inversor":
            rol = "Tenim projectes deep tech a la cartera que hi podrien optar i ens agradaria compartir-los amb vosaltres."
        else:
            rol = ("Estem preparant un consorci i pensem que hi podríeu tenir un paper clau"
                   + (f" ({temes})" if temes else "") + ". Stimulo s'encarregaria del disseny i el desenvolupament de producte.")
        cos = (f"{salutacio}\n\nT'escric perquè hi ha una convocatòria que pot encaixar amb {s.nom}: "
               f"{c.nom} ({c.entitat}).\n\n"
               f"- Què finança: {_resum(c.descripcio)}\n- Ajut: {ajut}\n- Calendari: {inici} – {final}\n"
               f"- Qui hi pot optar: {c.ambit_geografic or 'vegeu les bases'}\n\n{rol}\n\n"
               f"Et va bé que en parlem 20 minuts aquesta setmana o la que ve?\n\n"
               + (f"Més informació: {c.url}\n\n" if c.url else "") + signatura)
        assumpte = f"Oportunitat de finançament: {_curt(c.nom)}"
    else:
        inici = _data(f.obertura, f.estimada) or ("abierta" if f.estat in ("oberta", "permanent") else "por confirmar")
        final = _data(f.tancament, f.estimada) or ("todo el año" if f.estat == "permanent" else "por confirmar")
        ajut = " · ".join(filter(None, [f"hasta {_eur(c.import_max_eur)}" if c.import_max_eur else "",
                                        f"intensidad máxima {c.intensitat_max:g} %" if c.intensitat_max else ""])) \
            or "ver bases"
        salutacio = f"Hola {nom}:" if nom else f"Hola, equipo de {s.nom}:"
        if p.rol.startswith("sol·licitant") and "proveïdor" in p.rol:
            rol = ("Vosotros podríais ser los solicitantes y Stimulo participaría como agente tecnológico: "
                   "diseño, prototipo y validación. También podemos ayudaros a preparar la propuesta.")
        elif s.tipus in ("recerca", "hospital"):
            rol = ("Estamos valorando montar un consorcio y creemos que vuestro grupo encaja"
                   + (f" ({temes})" if temes else "") + ". Stimulo aportaría el diseño y el desarrollo de producto.")
        elif s.tipus == "inversor":
            rol = "Tenemos proyectos deep tech en cartera que podrían optar y nos gustaría compartirlos con vosotros."
        else:
            rol = ("Estamos preparando un consorcio y pensamos que podríais tener un papel clave"
                   + (f" ({temes})" if temes else "") + ". Stimulo se encargaría del diseño y el desarrollo de producto.")
        cos = (f"{salutacio}\n\nTe escribo porque hay una convocatoria que puede encajar con {s.nom}: "
               f"{c.nom} ({c.entitat}).\n\n"
               f"- Ayuda: {ajut}\n- Calendario: {inici} – {final}\n\n{rol}\n\n"
               f"¿Te va bien que lo hablemos 20 minutos esta semana o la próxima?\n\n"
               + (f"Más información: {c.url}\n\n" if c.url else "") + signatura)
        assumpte = f"Oportunidad de financiación: {_curt(c.nom)}"
    return {"per_a": dest.get("email", ""), "nom": dest.get("nom", ""), "generic": bool(dest.get("generic")),
            "assumpte": assumpte, "cos": cos, "idioma": "ca" if catala else "es"}


def _per_clients(l: Linia) -> str:
    """Qui en pot ser sol·licitant i què hi fa Stimulo (per a les línies que es comparteixen amb clients)."""
    noms = {"pime": "pimes", "gran_empresa": "grans empreses", "startup": "startups"}
    qui = [noms[b] for b in l.c.beneficiaris if b in noms]
    rols = set(l.c.rols_stimulo)
    if rols & {"proveidor_extern", "subcontractat"}:
        stimulo = "Stimulo hi entra com a proveïdor (disseny, prototip, validació)"
    elif rols & {"soci", "beneficiari"}:
        stimulo = "Stimulo hi pot ser soci del projecte"
    else:
        stimulo = "Stimulo pot ajudar a preparar-la"
    text = (f"Sol·licitant: el client ({', '.join(qui) or 'vegeu les bases'}). {stimulo}.")
    if l.clients_servei:
        text += " Clients de servei amb encaix: " + "; ".join(l.clients_servei) + "."
    return text


def _resum(text: str, maxim: int = 260) -> str:
    text = " ".join(text.split())
    if len(text) <= maxim:
        return text
    tall = text[:maxim].rsplit(" ", 1)[0]
    return tall.rstrip(",;:") + "…"


def _curt(nom: str, maxim: int = 70) -> str:
    return nom if len(nom) <= maxim else nom[:maxim].rsplit(" ", 1)[0] + "…"


def _mailto(d: dict) -> str:
    return "mailto:" + urllib.parse.quote(d["per_a"]) + "?" + urllib.parse.urlencode(
        {"subject": d["assumpte"], "body": d["cos"]}, quote_via=urllib.parse.quote)


def _camps(l: Linia) -> list[tuple[str, str]]:
    c, f = l.c, l.f
    inici = _data(f.obertura, f.estimada) or ("Oberta" if f.estat in ("oberta", "permanent") else "Per confirmar")
    final = _data(f.tancament, f.estimada) or ("Tot l'any" if f.estat == "permanent" else "Per confirmar")
    ajut = c.ajuda_text or " · ".join(filter(None, [_eur(c.import_max_eur),
                                                    f"{c.intensitat_max:g} %" if c.intensitat_max else ""]))
    return [("Inici", inici), ("Finalització", final), ("Ajut", ajut or "Per confirmar"),
            ("Zona elegible", c.ambit_geografic or ", ".join(c.zones)), ("Entitat", c.entitat)]


def compon(linies: list[Linia], avui: dt.date, config: dict | None = None, resum: list[Linia] | None = None,
           novetats: list[dict] | None = None, sense_socis_motiu: str = "",
           recordatoris: list[str] | None = None, licitacions: list | None = None) -> tuple[str, str, str]:
    """Retorna (assumpte, text pla, html) de l'avís per a Stimulo.

    `licitacions`: parells (Licitacio, Avaluacio) nous amb semàfor verd o groc (radar.licitacions).
    """
    cfg = {**CONFIG_PER_DEFECTE, **(config or {})}
    resum = resum or []
    novetats = novetats or []
    recordatoris = recordatoris or []
    licitacions = licitacions or []
    n = len(linies)
    assumpte = (f"Radar d'ajuts · {n} línia nova amb potencial" if n == 1 else
                f"Radar d'ajuts · {n} línies noves amb potencial") + f" · {avui:%d/%m/%Y}"
    n_clients = sum(1 for l in linies if l.per_clients)
    if linies and n_clients:
        assumpte = assumpte.replace(f" · {avui:%d/%m/%Y}", f" ({n_clients} per compartir amb clients) · {avui:%d/%m/%Y}")
    if not linies and licitacions:
        assumpte = (f"Radar d'ajuts · {len(licitacions)} licitaci{'ó nova' if len(licitacions) == 1 else 'ons noves'}"
                    f" amb encaix · {avui:%d/%m/%Y}")
    elif not linies and novetats:
        assumpte = f"Radar d'ajuts · {len(novetats)} novetats a les fonts oficials · {avui:%d/%m/%Y}"
    elif not linies and recordatoris:
        assumpte = f"Radar d'ajuts · recordatoris d'avui · {avui:%d/%m/%Y}"

    # ---- text pla
    t = [assumpte, ""]
    if recordatoris:
        t += ["Recordatoris d'avui:"] + [f"- {r}" for r in recordatoris] + [""]
    for i, l in enumerate(linies, 1):
        t += [f"{i}. {l.c.nom} — {l.c.entitat}", f"   {l.motiu} · encaix {l.e.punts}/100 ({l.e.prioritat})"]
        if l.per_clients:
            t.append(f"   PER COMPARTIR AMB CLIENTS: {_per_clients(l)}")
        t += [f"   {k}: {v}" for k, v in _camps(l)]
        t += [f"   Descripció: {_resum(l.c.descripcio, 500)}", f"   Per què encaixem: {_encaix(l)}"]
        if l.propostes:
            t.append("   Socis potencials:")
            for p in l.propostes:
                dest = p.soci.destinatari or {}
                t.append(f"   - {p.soci.nom} ({NOMS_TIPUS.get(p.soci.tipus, p.soci.tipus)}; {p.rol}): "
                         f"{_motius(p.motius)} · {dest.get('email', 'sense correu')}")
        for cons in _consideracions(l):
            t.append(f"   · {cons}")
        if l.c.url:
            t.append(f"   Fitxa: {l.c.url}")
        t.append("")
    if resum:
        t += ["Altres línies obertes o properes amb encaix:"]
        t += [f"- {l.c.nom} ({l.c.entitat}) · {l.motiu} · {l.e.punts}/100" for l in resum]
        t.append("")
    if licitacions:
        t += ["LICITACIONS NOVES AMB ENCAIX (detall i decisió a l'aplicació > Licitacions)"]
        for lic, av in licitacions:
            icona = {"verd": "[analitzar]", "groc": "[vigilar]"}.get(av.semafor, "")
            t.append(f"- {icona} {lic.titol} — {lic.organ}")
            termini = f"{lic.termini:%d/%m/%Y} ({av.dies} dies)" if lic.termini else "per confirmar"
            t.append(f"  Import: {_eur(lic.import_eur or lic.valor_estimat) or 'per confirmar'} · Termini: {termini}"
                     f" · {av.punts}/100 · {lic.font}: {lic.url}")
            for alerta in av.alertes[:2]:
                t.append(f"  ! {alerta}")
        t.append("")
    if novetats:
        t += ["Detectat a les fonts oficials (pendent de classificar):"]
        t += [f"- {'[ACCIÓ] ' if 'ACCIÓ' in nv.get('paraules', []) else ''}{nv['titol']} · {nv['organisme']} · "
              f"termini {nv.get('termini') or '—'} · {nv['url']}"
              for nv in sorted(novetats, key=lambda x: 'ACCIÓ' not in x.get('paraules', []))[:15]]
        t.append("")
    esborranys = [(l, p, esborrany(l, p, cfg["signatura"])) for l in linies for p in l.propostes]
    if esborranys:
        t += ["ESBORRANYS DE CORREU PER ALS SOCIS", ""]
        for l, p, d in esborranys:
            t += [f"Per a: {d['per_a'] or '(sense correu a Holded)'}", f"Assumpte: {d['assumpte']}", "", d["cos"],
                  "", "-" * 60, ""]
    if sense_socis_motiu:
        t += [sense_socis_motiu, ""]
    t.append("Generat pel Radar d'ajuts de Stimulo. Les dates amb ≈ són estimades.")
    text = "\n".join(t)

    # ---- html (estils en línia per als clients de correu)
    e = html.escape
    tinta, gris, linia, accent, fons = "#131A2A", "#5B6579", "#DCE1EA", "#2A3DBA", "#F3F5F9"
    h = [f'<div style="background:{fons};padding:24px 12px;font-family:Arial,Helvetica,sans-serif;color:{tinta}">',
         f'<div style="max-width:680px;margin:0 auto">',
         f'<p style="margin:0 0 4px;font:12px/1.4 monospace;letter-spacing:.06em;text-transform:uppercase;color:{gris}">'
         f'Radar d\'ajuts · {avui:%d/%m/%Y}</p>',
         f'<h1 style="margin:0 0 16px;font-size:22px;line-height:1.25">{e(assumpte.split(" · ")[1])}</h1>']
    if sense_socis_motiu:
        h.append(f'<p style="margin:0 0 16px;color:{gris};font-size:13px">{e(sense_socis_motiu)}</p>')
    if recordatoris:
        h.append(f'<div style="background:#fff;border:1px solid {linia};border-left:4px solid #B3261E;border-radius:10px;'
                 f'padding:14px 18px;margin:0 0 14px"><p style="margin:0 0 6px;font-size:14px"><b>Recordatoris d’avui</b></p>'
                 f'<ul style="margin:0;padding-left:18px;font-size:14px;line-height:1.5">'
                 + "".join(f"<li>{e(r)}</li>" for r in recordatoris) + "</ul></div>")
    for i, l in enumerate(linies, 1):
        c = l.c
        h.append(f'<div style="background:#fff;border:1px solid {linia};border-radius:10px;padding:18px 20px;margin:0 0 14px">')
        h.append(f'<p style="margin:0 0 6px;font-size:12px;color:{accent};font-weight:bold">{e(l.motiu)} · '
                 f'encaix {l.e.punts}/100 ({e(l.e.prioritat)})</p>')
        h.append(f'<h2 style="margin:0 0 12px;font-size:17px;line-height:1.3">{i}. {e(c.nom)}</h2>')
        if l.per_clients:
            h.append(f'<p style="margin:0 0 12px;font-size:13px;line-height:1.5;background:#E1F2E9;color:#13202A;'
                     f'border-radius:6px;padding:8px 10px"><b style="color:#19744B">Per compartir amb clients.</b> '
                     f'{e(_per_clients(l))}</p>')
        h.append('<table role="presentation" style="border-collapse:collapse;width:100%;font-size:14px;margin:0 0 12px">')
        for k, v in _camps(l):
            h.append(f'<tr><td style="padding:4px 12px 4px 0;color:{gris};white-space:nowrap;vertical-align:top;width:110px">'
                     f'{e(k)}</td><td style="padding:4px 0;vertical-align:top">{e(v)}</td></tr>')
        h.append("</table>")
        h.append(f'<p style="margin:0 0 10px;font-size:14px;line-height:1.5"><b>Descripció.</b> {e(_resum(c.descripcio, 600))}</p>')
        h.append(f'<p style="margin:0 0 10px;font-size:14px;line-height:1.5"><b>Per què encaixem.</b> {e(_encaix(l))}</p>')
        if l.propostes:
            h.append('<p style="margin:12px 0 6px;font-size:14px"><b>Socis potencials (Holded)</b></p><ul style="margin:0 0 10px;padding-left:18px;font-size:14px;line-height:1.5">')
            for p in l.propostes:
                d = esborrany(l, p, cfg["signatura"])
                dest = p.soci.destinatari or {}
                contacte = (f'{e(dest.get("nom") or "")} &lt;{e(dest["email"])}&gt;'.strip() if dest.get("email")
                            else "sense correu a Holded")
                avis_generic = " (adreça genèrica: buscar la persona de contacte)" if dest.get("generic") else ""
                enllac = (f' · <a href="{e(_mailto(d))}" style="color:{accent}">obrir esborrany</a>'
                          if d["per_a"] else "")
                h.append(f'<li><b>{e(p.soci.nom)}</b> · {e(NOMS_TIPUS.get(p.soci.tipus, p.soci.tipus))} · {e(p.rol)}<br>'
                         f'<span style="color:{gris}">{e(_motius(p.motius))}</span><br>{contacte}{e(avis_generic)}{enllac}</li>')
            h.append("</ul>")
        cons = _consideracions(l)
        if cons:
            h.append(f'<p style="margin:12px 0 6px;font-size:14px"><b>Altres consideracions</b></p>'
                     f'<ul style="margin:0 0 10px;padding-left:18px;font-size:14px;line-height:1.5">'
                     + "".join(f"<li>{e(x)}</li>" for x in cons) + "</ul>")
        if c.url:
            h.append(f'<p style="margin:8px 0 0;font-size:13px"><a href="{e(c.url)}" style="color:{accent}">Fitxa o font de la convocatòria</a></p>')
        h.append("</div>")
    if resum:
        h.append(f'<h3 style="font-size:15px;margin:22px 0 8px">Altres línies obertes o properes amb encaix</h3>'
                 f'<table role="presentation" style="border-collapse:collapse;width:100%;font-size:13px;background:#fff;border:1px solid {linia}">')
        for l in resum:
            h.append(f'<tr><td style="padding:8px 10px;border-top:1px solid {linia}">'
                     + (f'<a href="{e(l.c.url)}" style="color:{tinta}">{e(l.c.nom)}</a>' if l.c.url else e(l.c.nom))
                     + f'<br><span style="color:{gris}">{e(l.c.entitat)}</span></td>'
                     f'<td style="padding:8px 10px;border-top:1px solid {linia};color:{gris}">{e(l.motiu)}</td>'
                     f'<td style="padding:8px 10px;border-top:1px solid {linia};text-align:right">{l.e.punts}</td></tr>')
        h.append("</table>")
    if licitacions:
        colors = {"verd": "#19744B", "groc": "#9A5800"}
        h.append(f'<h3 style="font-size:15px;margin:22px 0 8px">Licitacions noves amb encaix</h3>'
                 f'<p style="font-size:13px;color:{gris};margin:0 0 8px">Detall, fitxa de decisió i seguiment a '
                 f'l\'aplicació, secció Licitacions.</p>')
        for lic, av in licitacions:
            termini = f"{lic.termini:%d/%m/%Y} · {av.dies} dies" if lic.termini else "termini per confirmar"
            h.append(f'<div style="background:#fff;border:1px solid {linia};border-left:4px solid '
                     f'{colors.get(av.semafor, gris)};border-radius:8px;padding:10px 14px;margin:0 0 8px;font-size:13px">'
                     f'<p style="margin:0 0 4px"><a href="{e(lic.url)}" style="color:{accent};font-weight:bold">'
                     f'{e(lic.titol[:180])}</a></p>'
                     f'<p style="margin:0;color:{gris}">{e(lic.organ[:120])} · '
                     f'{e(_eur(lic.import_eur or lic.valor_estimat) or "import per confirmar")} · {e(termini)} · '
                     f'{av.punts}/100 · {e(lic.font)}</p>'
                     + "".join(f'<p style="margin:4px 0 0;color:#9A5800">{e(x)}</p>' for x in av.alertes[:2])
                     + "</div>")
    if novetats:
        h.append(f'<h3 style="font-size:15px;margin:22px 0 8px">Detectat a les fonts oficials (pendent de classificar)</h3><ul style="font-size:13px;line-height:1.5;padding-left:18px">')
        for nv in sorted(novetats, key=lambda x: "ACCIÓ" not in x.get("paraules", []))[:15]:
            accio = "ACCIÓ" in nv.get("paraules", [])
            h.append(f'<li>{"<b>ACCIÓ · </b>" if accio else ""}<a href="{e(nv["url"])}" style="color:{accent}">'
                     f'{e(nv["titol"][:160])}</a> · {e(nv["organisme"][:80])}'
                     f' · termini {e(nv.get("termini") or "—")}</li>')
        h.append("</ul>")
    if esborranys:
        h.append(f'<h3 style="font-size:15px;margin:26px 0 8px">Esborranys de correu per als socis</h3>'
                 f'<p style="font-size:13px;color:{gris};margin:0 0 10px">Revisa\'ls abans d\'enviar-los. L\'enllaç «obrir esborrany» de cada soci els obre al teu programa de correu.</p>')
        for l, p, d in esborranys:
            h.append(f'<div style="background:#fff;border:1px solid {linia};border-radius:8px;padding:12px 14px;margin:0 0 10px;font-size:13px">'
                     f'<p style="margin:0 0 4px;color:{gris}">Per a: {e(d["per_a"] or "(sense correu a Holded)")}</p>'
                     f'<p style="margin:0 0 8px"><b>{e(d["assumpte"])}</b></p>'
                     f'<pre style="margin:0;white-space:pre-wrap;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:1.5">{e(d["cos"])}</pre></div>')
    h.append(f'<p style="font-size:12px;color:{gris};margin:22px 0 0">Generat pel Radar d\'ajuts de Stimulo. '
             f'Les dates amb ≈ són estimades a partir de l\'edició anterior.</p></div></div>')
    return assumpte, text, "\n".join(h)


# --- Enviament i estat ---------------------------------------------------------------------------

def smtp_configurat() -> bool:
    return all(os.environ.get(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "RADAR_DESTINATARI"))


def envia(assumpte: str, text: str, cos_html: str, remitent_nom: str = "Radar d'ajuts Stimulo") -> list[str]:
    destinataris = [d.strip() for d in os.environ["RADAR_DESTINATARI"].split(",") if d.strip()]
    usuari = os.environ["SMTP_USER"]
    msg = EmailMessage()
    msg["Subject"] = assumpte
    msg["From"] = formataddr((remitent_nom, os.environ.get("SMTP_FROM") or usuari))
    msg["To"] = ", ".join(destinataris)
    msg["Message-ID"] = make_msgid(domain="radar-ajuts.stimulo")
    msg.set_content(text)
    msg.add_alternative(cos_html, subtype="html")
    port = int(os.environ.get("SMTP_PORT") or 587)
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(os.environ["SMTP_HOST"], port, context=context, timeout=60) as s:
            s.login(usuari, os.environ["SMTP_PASSWORD"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(os.environ["SMTP_HOST"], port, timeout=60) as s:
            s.starttls(context=context)
            s.login(usuari, os.environ["SMTP_PASSWORD"])
            s.send_message(msg)
    return destinataris


def llegeix_estat(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def desa_estat(path: Path, estat: dict, linies: list[Linia], avui: dt.date) -> None:
    for l in linies:
        estat[l.clau] = avui.isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(sorted(estat.items())), ensure_ascii=False, indent=1), encoding="utf-8")


def desa_copia(dir_privat: Path, avui: dt.date, assumpte: str, text: str, cos_html: str) -> Path:
    """Còpia local de l'avís (directori privat, ignorat per git)."""
    dir_privat.mkdir(parents=True, exist_ok=True)
    base = dir_privat / f"avis-{avui:%Y-%m-%d}"
    base.with_suffix(".txt").write_text(text, encoding="utf-8")
    pagina = (f'<!doctype html><html lang="ca"><head><meta charset="utf-8"><title>{html.escape(assumpte)}</title>'
              f'<meta name="viewport" content="width=device-width, initial-scale=1"></head>'
              f'<body style="margin:0">{cos_html}</body></html>')
    base.with_suffix(".html").write_text(pagina, encoding="utf-8")
    return base.with_suffix(".html")
