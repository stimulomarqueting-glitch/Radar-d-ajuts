"""Línia d'ordres del radar.

    python -m radar valida                       # comprova el catàleg (data/*.yaml)
    python -m radar informe [--avui AAAA-MM-DD]  # genera sortida/ (md, ics, csv, json, html)
    python -m radar alertes [--dies 90]          # agenda d'alertes per pantalla
    python -m radar perfil doga                  # millors oportunitats per a un perfil
    python -m radar importa-excel fitxer.xlsx    # normalitza l'Excel i diu què falta al catàleg
    python -m radar vigila                       # consulta BDNS, F&T UE, TED i PLACSP (requereix xarxa)
    python -m radar avisa [--envia]              # correu de línies noves amb potencial + socis de Holded
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import json
import os

from . import avisos, calendari, dades, excel, holded, informe, ics, socis, vigilancia
from .puntuacio import puntua

ARREL = dades.ARREL
DIR_SORTIDA = ARREL / "sortida"


def _avui(valor: str | None) -> dt.date:
    return dt.date.fromisoformat(valor) if valor else dt.date.today()


def ordre_valida(_args) -> int:
    cat = dades.carrega()
    print(f"OK: {len(cat.convocatories)} convocatòries, {len(cat.perfils)} perfils, {len(cat.fonts)} fonts.")
    sense_url = [c.id for c in cat.convocatories if not c.url]
    if sense_url:
        print("Avís: convocatòries sense URL:", ", ".join(sense_url))
    return 0


def ordre_informe(args) -> int:
    cat = dades.carrega()
    avui = _avui(args.avui)
    generats = informe.genera_tot(cat, avui, DIR_SORTIDA)
    try:
        from . import html

        generats.append(html.genera(cat, avui, DIR_SORTIDA))
    except ImportError:
        pass
    for p in generats:
        print("→", p.relative_to(ARREL))
    return 0


def ordre_alertes(args) -> int:
    cat = dades.carrega()
    avui = _avui(args.avui)
    for s in calendari.agenda(cat.convocatories, avui, args.dies, cat.config.get("alertes")):
        marca = "≈" if s.estimada else " "
        print(f"{marca}{s.data:%d/%m/%Y}  {ics.ICONES.get(s.tipus, ' ')} {s.tipus:<9} "
              f"{s.convocatoria.entitat} · {s.convocatoria.nom}\n             {s.text}")
    return 0


def ordre_perfil(args) -> int:
    cat = dades.carrega(inclou_inactius=True)
    avui = _avui(args.avui)
    if args.id not in cat.perfils:
        print(f"Perfil desconegut. Opcions: {', '.join(cat.perfils)}", file=sys.stderr)
        return 2
    p = cat.perfils[args.id]
    files = []
    for c in cat.convocatories:
        e = puntua(c, p, cat.zones, cat.config.get("pesos"))
        f = calendari.propera_finestra(c, avui)
        if f.estat != "tancada" and e.prioritat != "NE":
            files.append((e, c, f))
    files.sort(key=lambda x: -x[0].punts)
    print(f"{p.nom} — zona {cat.zones.nom(p.zona)}\n")
    for e, c, f in files[: args.n]:
        print(f"{e.punts:>3} {e.prioritat}  {c.entitat} · {c.nom}\n       {informe._descriu_finestra(f)} | "
              f"{'; '.join(e.motius)}")
    return 0


def ordre_importa_excel(args) -> int:
    origen = Path(args.fitxer)
    files = excel.llegeix(origen)
    desti = ARREL / "data" / "importat" / (origen.stem + ".yaml")
    excel.desa(files, desti)
    print(f"{len(files)} files importades → {desti.relative_to(ARREL)}")
    pendents = excel.compara(files, ARREL / "data" / "convocatories.yaml")
    if pendents:
        print(f"\n{len(pendents)} files sense fitxa al catàleg (cal crear-la a data/convocatories.yaml):")
        for r in pendents:
            print(f"  fila {r['excel_fila']}: [{r['nivell']}] {r['nom']} — {r.get('entitat', '')}")
    else:
        print("Totes les files de l'Excel tenen fitxa al catàleg.")
    return 0


def ordre_vigila(args) -> int:
    cat = dades.carrega()
    avui = _avui(args.avui)
    paraules = sorted({k for p in cat.perfils.values() for k in p.paraules_clau})
    noves, errors = vigilancia.executa(cat.config.get("vigilancia", {}), paraules,
                                       ARREL / "data" / "estat" / "vistos.json")
    DIR_SORTIDA.mkdir(exist_ok=True)
    (DIR_SORTIDA / "novetats.md").write_text(vigilancia.informe_novetats(noves, errors, avui), encoding="utf-8")
    (DIR_SORTIDA / "novetats.json").write_text(vigilancia.a_json(noves), encoding="utf-8")
    print(f"{len(noves)} novetats; errors: {', '.join(errors) or 'cap'}")
    return 0


def _contactes(args) -> tuple[list, str]:
    """Contactes de Holded: fitxer indicat, API (HOLDED_API_KEY) o exportació privada."""
    try:
        if args.contactes:
            return holded.des_de_fitxer(Path(args.contactes)), ""
        if os.environ.get("HOLDED_API_KEY"):
            return holded.des_de_api(), ""
        local = ARREL / "privat" / "holded_contactes.json"
        if local.exists():
            return holded.des_de_fitxer(local), ""
        return [], "Sense socis suggerits: no hi ha accés als contactes de Holded (configura HOLDED_API_KEY)."
    except Exception as e:  # sense contactes l'avís continua sent útil
        return [], f"Sense socis suggerits: error llegint Holded ({type(e).__name__})."


def ordre_avisa(args) -> int:
    cat = dades.carrega()
    avui = _avui(args.avui)
    cfg = {**avisos.CONFIG_PER_DEFECTE, **cat.config.get("avisos", {})}
    fitxer_estat = ARREL / "data" / "estat" / "notificades.json"
    estat = avisos.llegeix_estat(fitxer_estat)
    candidates = avisos.candidates(cat, avui, cfg)
    if args.inicialitza:
        avisos.desa_estat(fitxer_estat, estat, candidates, avui)
        print(f"{len(candidates)} línies marcades com a ja avisades (no s'envia res).")
        return 0
    noves = candidates if args.tot else avisos.noves(candidates, estat)
    maxim = args.maxim or cfg["maxim_linies"]
    principals, resum = noves[:maxim], noves[maxim:]
    novetats = []
    if args.novetats and Path(args.novetats).exists():
        novetats = json.loads(Path(args.novetats).read_text(encoding="utf-8"))
    if not principals and not novetats:
        print("Cap línia nova amb potencial: no s'envia cap correu.")
        return 0
    contactes, motiu = _contactes(args)
    llista_socis = socis.construeix(contactes) if contactes else []
    avisos.afegeix_socis(principals, llista_socis, cat, cfg["maxim_socis"])
    assumpte, text, cos_html = avisos.compon(principals, avui, cfg, resum, novetats, motiu)
    copia = avisos.desa_copia(ARREL / "privat" / "avisos", avui, assumpte, text, cos_html)
    print(f"{assumpte}\nCòpia local (no es desa a git): {copia.relative_to(ARREL)}")
    if not args.envia:
        print("Vista prèvia: no s'ha enviat (afegeix --envia).")
        return 0
    if not avisos.smtp_configurat():
        print("No s'ha enviat: falten SMTP_HOST, SMTP_USER, SMTP_PASSWORD o RADAR_DESTINATARI.")
        return 0
    try:
        destinataris = avisos.envia(assumpte, text, cos_html, cfg["remitent_nom"])
    except Exception as e:
        print(f"Error enviant el correu: {type(e).__name__}: {e}")
        return 1
    if not args.sense_estat:
        avisos.desa_estat(fitxer_estat, estat, principals + resum, avui)
    print(f"Enviat a {len(destinataris)} destinatari(s).")
    return 0


def main(argv: list[str] | None = None) -> int:
    comu = argparse.ArgumentParser(add_help=False)
    comu.add_argument("--avui", help="data de referència AAAA-MM-DD (per defecte, avui)")
    ap = argparse.ArgumentParser(prog="radar", description="Radar d'ajuts, subvencions i licitacions de Stimulo")
    sub = ap.add_subparsers(dest="ordre", required=True)
    sub.add_parser("valida", parents=[comu]).set_defaults(f=ordre_valida)
    sub.add_parser("informe", parents=[comu]).set_defaults(f=ordre_informe)
    a = sub.add_parser("alertes", parents=[comu])
    a.add_argument("--dies", type=int, default=90)
    a.set_defaults(f=ordre_alertes)
    p = sub.add_parser("perfil", parents=[comu])
    p.add_argument("id")
    p.add_argument("-n", type=int, default=15)
    p.set_defaults(f=ordre_perfil)
    i = sub.add_parser("importa-excel", parents=[comu])
    i.add_argument("fitxer")
    i.set_defaults(f=ordre_importa_excel)
    sub.add_parser("vigila", parents=[comu]).set_defaults(f=ordre_vigila)
    av = sub.add_parser("avisa", parents=[comu], help="correu amb les línies noves amb potencial")
    av.add_argument("--envia", action="store_true", help="envia per SMTP (variables SMTP_* i RADAR_DESTINATARI)")
    av.add_argument("--contactes", help="JSON de contactes de Holded (si no, HOLDED_API_KEY o privat/)")
    av.add_argument("--novetats", help="JSON de novetats dels vigilants (sortida/novetats.json)")
    av.add_argument("--tot", action="store_true", help="inclou també les línies ja avisades")
    av.add_argument("--maxim", type=int, help="línies amb fitxa completa (per defecte, config.avisos.maxim_linies)")
    av.add_argument("--inicialitza", action="store_true", help="marca les línies actuals com a avisades")
    av.add_argument("--sense-estat", action="store_true", help="no actualitza data/estat/notificades.json")
    av.set_defaults(f=ordre_avisa)
    args = ap.parse_args(argv)
    return args.f(args)


if __name__ == "__main__":
    raise SystemExit(main())
