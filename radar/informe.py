"""Sortides del radar: informe Markdown, agenda d'alertes (.ics), enviaments per zona (CSV) i dades (JSON)."""

from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

from . import calendari, ics
from .dades import Cataleg
from .puntuacio import Encaix, puntua

NOMS_NIVELL = {
    "local": "Local",
    "catalunya": "Catalunya",
    "estat": "Estat",
    "europa": "Europa",
    "internacional": "Internacional",
}
NOMS_ORIGEN = {
    "public": "Públic",
    "privat": "Privat",
    "universitat": "Universitat",
    "fundacio_publica": "Fundació pública",
    "fundacio_privada": "Fundació privada",
    "corporatiu": "Corporatiu",
    "mixt": "Mixt",
}


def _eur(valor: float | None) -> str:
    if valor is None:
        return "—"
    if valor >= 1_000_000:
        return f"{valor / 1_000_000:,.1f} M€".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{valor:,.0f} €".replace(",", ".")


def _data(d: dt.date | None) -> str:
    return f"{d:%d/%m/%Y}" if d else "—"


def matriu(cat: Cataleg, avui: dt.date) -> list[dict]:
    """Una fila per convocatòria amb finestra i encaix amb tots els perfils."""
    pesos = cat.config.get("pesos")
    files = []
    for c in cat.convocatories:
        f = calendari.propera_finestra(c, avui)
        encaixos = {pid: puntua(c, p, cat.zones, pesos) for pid, p in cat.perfils.items()}
        files.append({"c": c, "f": f, "e": encaixos})
    return files


def _ordre_finestra(fila) -> tuple:
    f = fila["f"]
    ordre_estat = {"oberta": 0, "propera": 1, "permanent": 2, "sense_dades": 3, "tancada": 4}
    referencia = f.tancament if f.estat == "oberta" else (f.obertura or f.tancament)
    return (ordre_estat.get(f.estat, 9), referencia or dt.date.max)


def _linia_encaix(e: Encaix) -> str:
    return f"{e.punts} ({e.prioritat})"


def markdown(cat: Cataleg, avui: dt.date, dies_agenda: int = 180) -> str:
    files = matriu(cat, avui)
    antelacio = cat.config.get("alertes")
    agenda = calendari.agenda(cat.convocatories, avui, dies_agenda, antelacio)
    perfils = list(cat.perfils.values())
    l: list[str] = []
    l.append("# Radar d'ajuts, subvencions i licitacions — Stimulo")
    l.append("")
    l.append(f"_Generat el {avui:%d/%m/%Y} amb `python -m radar informe`. "
             f"{len(cat.convocatories)} convocatòries al catàleg · {len(cat.fonts)} fonts vigilades._")
    l.append("")
    l.append("> Les dates marcades amb ≈ són **estimades** a partir de l'edició anterior: serveixen de senyal "
             "d'alerta, no substitueixen la convocatòria oficial.")
    l.append("")

    oberts = [r for r in files if r["f"].estat == "oberta"]
    l.append(f"## 1. Oberts ara ({len(oberts)})")
    l.append("")
    l.append("| Convocatòria | Entitat | Zona elegible | Tanca | Ajut | " + " | ".join(p.nom for p in perfils) + " |")
    l.append("|---|---|---|---|---|" + "---|" * len(perfils))
    for r in sorted(oberts, key=_ordre_finestra):
        c, f = r["c"], r["f"]
        tanca = ("≈ " if f.estimada else "") + _data(f.tancament)
        l.append(f"| [{c.nom}]({c.url}) | {c.entitat} | {cat.zones.etiqueta(c.zones)} | {tanca} | "
                 f"{_eur(c.import_max_eur)} | " + " | ".join(_linia_encaix(r["e"][p.id]) for p in perfils) + " |")
    l.append("")

    l.append(f"## 2. Agenda d'alertes (propers {dies_agenda} dies)")
    l.append("")
    l.append("| Data | Senyal | Convocatòria | Acció |")
    l.append("|---|---|---|---|")
    for s in agenda:
        marca = "≈ " if s.estimada else ""
        l.append(f"| {marca}{s.data:%d/%m/%Y} | {ics.ICONES.get(s.tipus, '')} {s.tipus} | "
                 f"{s.convocatoria.entitat} · {s.convocatoria.nom} | {s.text} |")
    l.append("")

    l.append("## 3. Millors oportunitats" + (" per perfil" if len(perfils) > 1 else f" per a {perfils[0].nom}"))
    for p in perfils:
        l.append("")
        if len(perfils) > 1:
            l.append(f"### {p.nom} ({cat.zones.nom(p.zona)})")
            l.append("")
        l.append("| Punts | Convocatòria | Rol | Finestra | Per què |")
        l.append("|---|---|---|---|---|")
        candidats = [r for r in files if r["e"][p.id].prioritat in ("A", "B") and r["f"].estat != "tancada"]
        candidats.sort(key=lambda r: -r["e"][p.id].punts)
        for r in candidats[:15]:
            e, c, f = r["e"][p.id], r["c"], r["f"]
            finestra = _descriu_finestra(f)
            l.append(f"| **{e.punts}** {e.prioritat} | [{c.nom}]({c.url}) · {c.entitat} | {e.rol} | {finestra} | "
                     f"{'; '.join(e.motius)} |")
    l.append("")

    l.append("## 4. Per zona geogràfica on ha d'estar el beneficiari")
    l.append("")
    per_zona: dict[str, list] = {}
    for r in files:
        if r["f"].estat == "tancada":
            continue
        clau = cat.zones.etiqueta(r["c"].zones)
        per_zona.setdefault(clau, []).append(r)
    for zona in sorted(per_zona, key=lambda z: (-len(per_zona[z]), z)):
        l.append(f"- **{zona}** ({len(per_zona[zona])}): " + ", ".join(
            r["c"].nom for r in sorted(per_zona[zona], key=_ordre_finestra)))
    l.append("")

    l.append("## 5. Catàleg complet")
    l.append("")
    l.append("| Nivell | Origen | Convocatòria | Entitat | Instrument | Intensitat | Màx. | TRL | Finestra | Confiança |")
    l.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(files, key=lambda r: (list(NOMS_NIVELL).index(r["c"].nivell), r["c"].entitat, r["c"].nom)):
        c, f = r["c"], r["f"]
        trl = f"{c.trl[0]}–{c.trl[1]}" if c.trl else "—"
        intensitat = f"{c.intensitat_max:g}%" if c.intensitat_max else "—"
        l.append(f"| {NOMS_NIVELL[c.nivell]} | {NOMS_ORIGEN[c.origen]} | [{c.nom}]({c.url}) | {c.entitat} | "
                 f"{c.instrument} | {intensitat} | {_eur(c.import_max_eur)} | {trl} | {_descriu_finestra(f)} | "
                 f"{c.confianca} |")
    l.append("")
    return "\n".join(l)


def _descriu_finestra(f: calendari.Finestra) -> str:
    marca = "≈ " if f.estimada else ""
    if f.estat == "permanent":
        return "Oberta tot l'any"
    if f.estat == "oberta":
        if not f.tancament:
            return "Oberta (termini a confirmar)"
        return f"Oberta fins {marca}{_data(f.tancament)}"
    if f.estat == "propera":
        if f.obertura and f.tancament:
            return f"{marca}{_data(f.obertura)} → {_data(f.tancament)}"
        if f.obertura:
            return f"Obre {marca}{_data(f.obertura)}"
        if f.tancament:
            return f"Propera, tall {marca}{_data(f.tancament)}"
        return "Anunciada (dates pendents)"
    if f.estat == "tancada":
        return "Tancada"
    return "Sense dates"


def enviaments(cat: Cataleg, avui: dt.date, dies: int = 120) -> list[dict]:
    """Oportunitats obertes o que obren aviat x clients elegibles per zona (prioritat A/B)."""
    limit = avui + dt.timedelta(days=dies)
    files = []
    clients = [p for p in cat.perfils.values() if p.tipus == "client"]
    for r in matriu(cat, avui):
        c, f = r["c"], r["f"]
        rellevant = f.estat in ("oberta", "permanent") or (
            f.estat == "propera" and (f.obertura or f.tancament or dt.date.max) <= limit
        )
        if not rellevant:
            continue
        for p in clients:
            e = r["e"][p.id]
            if e.rol != "beneficiari" or e.prioritat not in ("A", "B"):
                continue
            files.append({
                "client": p.nom,
                "zona_client": cat.zones.nom(p.zona),
                "contacte": p.contacte,
                "convocatoria": c.nom,
                "entitat": c.entitat,
                "zona_elegible": cat.zones.etiqueta(c.zones),
                "estat": f.estat,
                "obertura": _data(f.obertura),
                "tancament": _data(f.tancament),
                "dates_estimades": "sí" if f.estimada else "no",
                "punts": e.punts,
                "prioritat": e.prioritat,
                "motius": "; ".join(e.motius),
                "url": c.url,
            })
    files.sort(key=lambda x: (x["client"], -x["punts"]))
    return files


def dades_json(cat: Cataleg, avui: dt.date) -> dict:
    antelacio = cat.config.get("alertes")
    sortida = {
        "generat": avui.isoformat(),
        "perfils": [{"id": p.id, "nom": p.nom, "tipus": p.tipus, "zona": cat.zones.nom(p.zona), "codi_zona": p.zona}
                    for p in cat.perfils.values()],
        "zones": {codi: {"nom": d.get("nom", codi), "pare": d.get("pare")}
                  for codi, d in cat.zones.definicions.items()},
        "convocatories": [],
        "agenda": [],
    }
    for r in matriu(cat, avui):
        c, f = r["c"], r["f"]
        sortida["convocatories"].append({
            "id": c.id, "nom": c.nom, "entitat": c.entitat, "nivell": c.nivell, "origen": c.origen,
            "instrument": c.instrument, "descripcio": c.descripcio, "zones": c.zones,
            "zona_etiqueta": cat.zones.etiqueta(c.zones), "ambit_geografic": c.ambit_geografic,
            "focus": c.focus, "intensitat_max": c.intensitat_max, "import_max_eur": c.import_max_eur,
            "ajuda_text": c.ajuda_text, "trl": list(c.trl) if c.trl else None, "url": c.url,
            "notes": c.notes, "confianca": c.confianca, "beneficiaris": c.beneficiaris,
            "rols_stimulo": c.rols_stimulo, "excel_fila": c.excel_fila, "compartir_clients": c.compartir_clients,
            "linies": c.linies, "seguiment": c.seguiment,
            "finestra": {"estat": f.estat, "obertura": f.obertura.isoformat() if f.obertura else None,
                         "tancament": f.tancament.isoformat() if f.tancament else None,
                         "estimada": f.estimada, "text": _descriu_finestra(f)},
            "encaix": {pid: {"punts": e.punts, "prioritat": e.prioritat, "rol": e.rol, "motius": e.motius}
                       for pid, e in r["e"].items()},
        })
    for s in calendari.agenda(cat.convocatories, avui, 400, antelacio):
        sortida["agenda"].append({"data": s.data.isoformat(), "tipus": s.tipus, "id": s.convocatoria.id,
                                  "nom": s.convocatoria.nom, "entitat": s.convocatoria.entitat,
                                  "estimada": s.estimada, "text": s.text})
    return sortida


def genera_tot(cat: Cataleg, avui: dt.date, dir_sortida: Path) -> list[Path]:
    dir_sortida.mkdir(parents=True, exist_ok=True)
    generats = []

    md = dir_sortida / "radar.md"
    md.write_text(markdown(cat, avui), encoding="utf-8")
    generats.append(md)

    agenda = calendari.agenda(cat.convocatories, avui, 450, cat.config.get("alertes"))
    ics_path = dir_sortida / "alertes.ics"
    ics_path.write_text(
        ics.genera(agenda, dt.datetime.combine(avui, dt.time(6, 0))), encoding="utf-8", newline=""
    )
    generats.append(ics_path)

    # Enviaments per zona: només si algun client de servei té el perfil actiu (p. ex. DOGA)
    csv_path = dir_sortida / "enviaments_per_zona.csv"
    if any(p.tipus == "client" for p in cat.perfils.values()):
        env = enviaments(cat, avui)
        camps = ["client", "zona_client", "contacte", "convocatoria", "entitat", "zona_elegible", "estat", "obertura",
                 "tancament", "dates_estimades", "punts", "prioritat", "motius", "url"]
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=camps)
            w.writeheader()
            w.writerows(env)
        generats.append(csv_path)
    elif csv_path.exists():
        csv_path.unlink()

    from . import ecosistema  # importació local: ecosistema depèn de dades, com aquest mòdul

    eco_md = dir_sortida / "ecosistema.md"
    eco_md.write_text(ecosistema.markdown(ecosistema.carrega(cat), avui), encoding="utf-8")
    generats.append(eco_md)

    from . import pla  # pla públic per línies (sense clients ni socis de Holded)

    inici, fi = pla.horitzo(avui)
    generats += pla.genera(pla.construeix(cat, avui, inici, fi), dir_sortida).values()

    js = dir_sortida / "radar.json"
    js.write_text(json.dumps(dades_json(cat, avui), ensure_ascii=False, indent=1), encoding="utf-8")
    generats.append(js)
    return generats
