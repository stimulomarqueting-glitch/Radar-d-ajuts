"""Línia d'ordres del radar.

    python -m radar valida                       # comprova el catàleg (data/*.yaml)
    python -m radar informe [--avui AAAA-MM-DD]  # genera sortida/ (md, ics, csv, json, html)
    python -m radar alertes [--dies 90]          # agenda d'alertes per pantalla
    python -m radar perfil doga                  # millors oportunitats per a un perfil
    python -m radar importa-excel fitxer.xlsx    # normalitza l'Excel i diu què falta al catàleg
    python -m radar vigila                       # consulta BDNS, F&T UE, TED i PLACSP (requereix xarxa)
    python -m radar avisa [--envia]              # correu de línies noves amb potencial + socis de Holded
    python -m radar diari                        # revisió del matí: vigila + informe + avisa --envia
    python -m radar programador                  # servei: revisió diària a RADAR_HORA (VPS)
    python -m radar web                          # aplicació web (tauler, expedients i assistent)
    python -m radar contrasenya                  # genera les claus d'accés de l'aplicació
    python -m radar screening doga               # informe d'ajuts per a un client, per divisions
    python -m radar licitacions                  # licitacions (PSCP, PLACSP, TED) amb semàfor go/no-go
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import json

from . import avisos, calendari, dades, excel, informe, ics, vigilancia
from .puntuacio import puntua

ARREL = dades.ARREL
DIR_SORTIDA = ARREL / "sortida"


def _avui(valor: str | None) -> dt.date:
    return dt.date.fromisoformat(valor) if valor else dt.date.today()


def ordre_valida(_args) -> int:
    cat = dades.carrega()
    from . import screening

    from . import ecosistema

    clients = screening.carrega_clients(cat)
    eco = ecosistema.carrega(cat)
    print(f"OK: {len(cat.convocatories)} convocatòries, {len(cat.perfils)} perfils, {len(cat.fonts)} fonts, "
          f"{len(clients)} clients ({sum(len(c.divisions) for c in clients.values())} divisions), "
          f"ecosistema: {len(eco.actors)} actors, {len(eco.trobades)} trobades, {len(eco.requisits)} requisits.")
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


def ordre_screening(args) -> int:
    from . import screening

    cat = dades.carrega()
    clients = screening.carrega_clients(cat)
    if args.client not in clients:
        print(f"Client desconegut. Opcions: {', '.join(clients) or 'cap (data/clients/*.yaml)'}", file=sys.stderr)
        return 2
    client = clients[args.client]
    divisions = args.divisio or None
    if divisions and (desconegudes := set(divisions) - {d.id for d in client.divisions}):
        print(f"Divisió desconeguda: {', '.join(desconegudes)}. Opcions: {', '.join(d.id for d in client.divisions)}",
              file=sys.stderr)
        return 2
    sc = screening.screening(cat, client, _avui(args.avui), divisions, maxim=args.maxim)
    dir_sortida = Path(args.sortida) if args.sortida else ARREL / "privat" / "clients" / client.id
    for r in sc.resultats:
        print(f"{r.divisio.nom}: {len(r.oportunitats)} línies · {screening.missatge_divisio(r)}")
    for tipus, ruta in screening.genera(sc, dir_sortida, cat.config.get("alertes")).items():
        print(f"→ {ruta}")
    return 0


def ordre_licitacions(args) -> int:
    from . import licitacions

    cat = dades.carrega()
    avui = _avui(args.avui)
    db = None
    if _path_db().exists():
        from .web.db import BaseDades

        db = BaseDades(_path_db())
    r = licitacions.executa(cat, avui, DIR_SORTIDA, ARREL / "data" / "estat" / "licitacions-vistes.json", db)
    print(f"{r['totes']} anuncis llegits · {r['rellevants']} amb encaix · {len(r['noves'])} nous")
    for l, a in r["noves"][:20]:
        print(f"  [{a.semafor}] {licitacions.resum_curt(l, a)}")
    for font, error in r["errors"].items():
        print(f"  Error a {font}: {error}")
    print("→ sortida/licitacions.md")
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


def ordre_avisa(args) -> int:
    from . import diari

    avui = _avui(args.avui)
    if args.inicialitza:
        cat = dades.carrega()
        cfg = {**avisos.CONFIG_PER_DEFECTE, **cat.config.get("avisos", {})}
        fitxer_estat = ARREL / "data" / "estat" / "notificades.json"
        candidates = avisos.candidates(cat, avui, cfg)
        avisos.desa_estat(fitxer_estat, avisos.llegeix_estat(fitxer_estat), candidates, avui)
        print(f"{len(candidates)} línies marcades com a ja avisades (no s'envia res).")
        return 0
    novetats = []
    if args.novetats and Path(args.novetats).exists():
        novetats = json.loads(Path(args.novetats).read_text(encoding="utf-8"))
    noves_lics = []
    if args.licitacions:
        from . import licitacions

        noves_lics = licitacions.llegeix_noves(Path(args.licitacions))
    try:
        r = diari.prepara_avis(avui, envia=args.envia, tot=args.tot, maxim=args.maxim, novetats=novetats,
                               fitxer_contactes=args.contactes, path_db=_path_db(),
                               actualitza_estat=not args.sense_estat, noves_licitacions=noves_lics)
    except Exception as e:
        print(f"Error enviant el correu: {type(e).__name__}: {e}")
        return 1
    if r.assumpte:
        print(r.assumpte)
    if r.copia:
        print(f"Còpia local (no es desa a git): {r.copia.relative_to(ARREL)}")
    print(r.missatge)
    return 0


def _path_db():
    from .web.config import Config

    return Config().db


def ordre_diari(args) -> int:
    from . import diari

    r = diari.executa_diari(_avui(args.avui), envia=not args.sense_enviar, path_db=_path_db())
    print(r.assumpte or "Sense correu", "·", r.missatge)
    for k, v in r.errors.items():
        print(f"  error {k}: {v.splitlines()[-1] if v else ''}")
    return 0


def ordre_programador(args) -> int:
    from . import diari

    diari.programador(args.hora, path_db=_path_db())
    return 0


def ordre_web(args) -> int:
    import os

    import uvicorn

    # Darrere de Caddy (Docker) RADAR_PROXY_IPS=* perquè el límit d'intents vegi la IP real del client
    uvicorn.run("radar.web.app:crea_app", factory=True, host=args.host, port=args.port, proxy_headers=True,
                forwarded_allow_ips=os.environ.get("RADAR_PROXY_IPS", "127.0.0.1"))
    return 0


def ordre_contrasenya(_args) -> int:
    from .web import auth

    return auth.main()


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
    sc = sub.add_parser("screening", parents=[comu], help="informe d'ajuts per a un client, divisió per divisió")
    sc.add_argument("client", help="id del client (data/clients/<id>.yaml)")
    sc.add_argument("--divisio", action="append", help="limita'l a una divisió (es pot repetir)")
    sc.add_argument("--maxim", type=int, default=8, help="línies per divisió (per defecte, 8)")
    sc.add_argument("--sortida", help="carpeta de sortida (per defecte, privat/clients/<id>/)")
    sc.set_defaults(f=ordre_screening)
    sub.add_parser("licitacions", parents=[comu],
                   help="cerca licitacions (PSCP, PLACSP, TED) i les avalua").set_defaults(f=ordre_licitacions)
    i = sub.add_parser("importa-excel", parents=[comu])
    i.add_argument("fitxer")
    i.set_defaults(f=ordre_importa_excel)
    sub.add_parser("vigila", parents=[comu]).set_defaults(f=ordre_vigila)
    av = sub.add_parser("avisa", parents=[comu], help="correu amb les línies noves amb potencial")
    av.add_argument("--envia", action="store_true", help="envia per SMTP (variables SMTP_* i RADAR_DESTINATARI)")
    av.add_argument("--contactes", help="JSON de contactes de Holded (si no, HOLDED_API_KEY o privat/)")
    av.add_argument("--novetats", help="JSON de novetats dels vigilants (sortida/novetats.json)")
    av.add_argument("--tot", action="store_true", help="inclou també les línies ja avisades")
    av.add_argument("--licitacions", help="JSON de licitacions noves (sortida/licitacions-noves.json)")
    av.add_argument("--maxim", type=int, help="línies amb fitxa completa (per defecte, config.avisos.maxim_linies)")
    av.add_argument("--inicialitza", action="store_true", help="marca les línies actuals com a avisades")
    av.add_argument("--sense-estat", action="store_true", help="no actualitza data/estat/notificades.json")
    av.set_defaults(f=ordre_avisa)
    di = sub.add_parser("diari", parents=[comu], help="revisió completa: vigilància, informe i avís per correu")
    di.add_argument("--sense-enviar", action="store_true", help="prepara l'avís però no l'envia")
    di.set_defaults(f=ordre_diari)
    pr = sub.add_parser("programador", help="servei: revisió diària a RADAR_HORA (Europe/Madrid)")
    pr.add_argument("--hora", help="HH:MM (per defecte RADAR_HORA o 07:30)")
    pr.set_defaults(f=ordre_programador)
    we = sub.add_parser("web", help="aplicació web (tauler, expedients i assistent)")
    we.add_argument("--host", default="127.0.0.1")
    we.add_argument("--port", type=int, default=8000)
    we.set_defaults(f=ordre_web)
    sub.add_parser("contrasenya", help="genera les claus d'accés per al fitxer .env").set_defaults(f=ordre_contrasenya)
    args = ap.parse_args(argv)
    return args.f(args)


if __name__ == "__main__":
    raise SystemExit(main())
