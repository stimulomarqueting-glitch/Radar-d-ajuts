"""Tauler HTML autònom del radar (sortida/radar.html), amb filtres per perfil, zona i estat.

`genera(..., autonom=False)` escriu només el contingut de la pàgina (sense <!doctype>/<head>), que és
el format que espera la publicació com a Artifact.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .dades import Cataleg
from .informe import dades_json

PLANTILLA = r"""<title>Radar d'ajuts Stimulo</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Schibsted+Grotesk:wght@600;800&display=swap">
<style>
/* Layout: capçalera amb selector de perfil, franja de resum, i dues columnes (oportunitats | senyals) que s'apilen al mòbil */
:root {
  --bg: #F3F5F9; --surface: #FFFFFF; --ink: #131A2A; --muted: #5B6579; --line: #DCE1EA;
  --accent: #2A3DBA; --accent-soft: #E7EAFB; --accent-ink: #FFFFFF;
  --ok: #19744B; --ok-soft: #E1F2E9; --warn: #9A5800; --warn-soft: #FAEED8;
  --off: #7D879B; --off-soft: #ECEFF4; --danger: #B3261E;
  --f-display: "Schibsted Grotesk", "Helvetica Neue", Arial, sans-serif;
  --f-body: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --f-mono: "IBM Plex Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
  --r: 10px;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #0D121C; --surface: #151C2A; --ink: #E6EAF2; --muted: #9AA3B6; --line: #273145;
  --accent: #8F9DFF; --accent-soft: #222A50; --accent-ink: #0D121C;
  --ok: #5BC892; --ok-soft: #153126; --warn: #EFB25A; --warn-soft: #382912;
  --off: #6F7891; --off-soft: #1C2332; --danger: #FF8A80; color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #0D121C; --surface: #151C2A; --ink: #E6EAF2; --muted: #9AA3B6; --line: #273145;
  --accent: #8F9DFF; --accent-soft: #222A50; --accent-ink: #0D121C;
  --ok: #5BC892; --ok-soft: #153126; --warn: #EFB25A; --warn-soft: #382912;
  --off: #6F7891; --off-soft: #1C2332; --danger: #FF8A80; color-scheme: dark; }

* { box-sizing: border-box; }
body { background: var(--bg); color: var(--ink); font: 15px/1.5 var(--f-body); }
.pagina { max-width: 1240px; margin: 0 auto; padding-inline: 20px; padding-block: 28px 56px; display: grid; gap: 22px; }
a { color: var(--accent); }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px; }

header.cap { display: flex; flex-wrap: wrap; gap: 16px 28px; align-items: end; justify-content: space-between; }
.marca { display: grid; gap: 4px; min-width: 0; }
.marca .eti { font: 500 12px/1 var(--f-mono); letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
h1 { font: 800 clamp(28px, 4.2vw, 40px)/1.05 var(--f-display); letter-spacing: -.02em; margin: 0; text-wrap: balance; }
.sub { color: var(--muted); margin: 0; max-width: 62ch; }
.perfils { display: grid; gap: 6px; }
.perfils > span { font: 500 12px/1 var(--f-mono); letter-spacing: .06em; text-transform: uppercase; color: var(--muted); }
.seg { display: inline-flex; background: var(--surface); border: 1px solid var(--line); border-radius: 999px; padding: 3px; gap: 2px; }
.seg button { font: 600 14px/1 var(--f-body); color: var(--ink); background: none; border: 0; border-radius: 999px; padding: 9px 16px; cursor: pointer; }
.seg button[aria-pressed="true"] { background: var(--accent); color: var(--accent-ink); }

.resum { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1px; background: var(--line); border: 1px solid var(--line); border-radius: var(--r); overflow: hidden; }
.resum div { background: var(--surface); padding: 14px 16px; display: grid; gap: 2px; }
.resum b { font: 800 26px/1.1 var(--f-display); font-variant-numeric: tabular-nums; }
.resum span { color: var(--muted); font-size: 13px; }

.filtres { display: flex; flex-wrap: wrap; gap: 10px 14px; align-items: end; }
.camp { display: grid; gap: 4px; min-width: 0; }
.camp label { font: 500 11px/1 var(--f-mono); letter-spacing: .06em; text-transform: uppercase; color: var(--muted); }
.camp select, .camp input { font: 14px/1.2 var(--f-body); color: var(--ink); background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 9px 10px; min-width: 0; max-width: 100%; }
.camp input { width: 220px; }
.compte { margin-left: auto; color: var(--muted); font-size: 13px; }

.cos { display: grid; grid-template-columns: minmax(0, 1fr) 330px; gap: 22px; align-items: start; }
.llista { display: grid; gap: 8px; min-width: 0; }
.op { background: var(--surface); border: 1px solid var(--line); border-radius: var(--r); }
.op[open] { border-color: color-mix(in srgb, var(--accent) 45%, var(--line)); }
.op > summary { list-style: none; cursor: pointer; display: grid; grid-template-columns: 52px minmax(0, 1fr) 170px 150px; gap: 14px; align-items: center; padding: 12px 14px; }
.op > summary::-webkit-details-marker { display: none; }
.punts { display: grid; place-items: center; width: 48px; height: 48px; border-radius: 9px; font: 500 17px/1 var(--f-mono); font-variant-numeric: tabular-nums; border: 1px solid var(--line); }
.punts small { font: 600 10px/1 var(--f-body); letter-spacing: .06em; margin-top: -6px; }
.p-A { background: var(--accent); color: var(--accent-ink); border-color: var(--accent); }
.p-B { background: var(--accent-soft); color: var(--accent); border-color: transparent; }
.p-C, .p-NE { background: var(--off-soft); color: var(--muted); border-color: transparent; }
.tit { min-width: 0; display: grid; gap: 3px; }
.tit strong { font-weight: 600; line-height: 1.3; }
.tit .meta { color: var(--muted); font-size: 13px; display: flex; flex-wrap: wrap; gap: 4px 10px; }
.estat { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 500; padding: 5px 9px; border-radius: 6px; width: fit-content; }
.estat::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.e-oberta { background: var(--ok-soft); color: var(--ok); }
.e-propera { background: var(--warn-soft); color: var(--warn); }
.e-permanent { background: var(--accent-soft); color: var(--accent); }
.e-tancada, .e-sense_dades { background: var(--off-soft); color: var(--muted); }
.e-estimada { outline: 1px dashed currentColor; outline-offset: -1px; }
.zona { font-size: 13px; color: var(--muted); min-width: 0; }
.zona b { display: block; color: var(--ink); font-weight: 500; }
.det { padding: 2px 14px 16px 80px; display: grid; gap: 12px; font-size: 14px; }
.det p { margin: 0; max-width: 72ch; }
.fitxa { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 10px 18px; margin: 0; }
.fitxa div { min-width: 0; }
.fitxa dt { font: 500 11px/1.3 var(--f-mono); letter-spacing: .05em; text-transform: uppercase; color: var(--muted); }
.fitxa dd { margin: 2px 0 0; overflow-wrap: anywhere; }
.trl { display: inline-grid; grid-template-columns: repeat(9, 10px); gap: 2px; vertical-align: middle; margin-right: 6px; }
.trl i { height: 10px; border-radius: 2px; background: var(--off-soft); border: 1px solid var(--line); }
.trl i.on { background: var(--accent); border-color: var(--accent); }
.etiquetes { display: flex; flex-wrap: wrap; gap: 6px; }
.etiquetes span { font: 12px/1 var(--f-mono); padding: 5px 7px; border-radius: 5px; background: var(--off-soft); color: var(--muted); }
.etiquetes span.match { background: var(--accent-soft); color: var(--accent); }
.nota { border-left: 3px solid var(--warn); padding: 4px 0 4px 12px; color: var(--ink); }
.conf { font: 12px/1 var(--f-mono); }
.conf-baixa { color: var(--danger); } .conf-mitjana { color: var(--warn); } .conf-alta { color: var(--ok); }
.buit { padding: 28px; text-align: center; color: var(--muted); background: var(--surface); border: 1px dashed var(--line); border-radius: var(--r); }

aside.senyals { position: sticky; top: calc(env(safe-area-inset-top, 0px) + 12px); background: var(--surface); border: 1px solid var(--line); border-radius: var(--r); padding: 16px; display: grid; gap: 12px; max-height: calc(100vh - 24px); overflow: auto; }
aside h2 { font: 800 18px/1.2 var(--f-display); margin: 0; }
aside .ajuda { margin: 0; color: var(--muted); font-size: 13px; }
.setmana { display: grid; gap: 6px; }
.setmana h3 { font: 500 11px/1 var(--f-mono); letter-spacing: .06em; text-transform: uppercase; color: var(--muted); margin: 6px 0 0; }
.sen { display: grid; grid-template-columns: 54px minmax(0, 1fr); gap: 10px; font-size: 13px; padding: 6px 0; border-top: 1px solid var(--line); }
.sen time { font: 500 13px/1.3 var(--f-mono); font-variant-numeric: tabular-nums; }
.sen time.est::before { content: "≈"; color: var(--warn); margin-right: 1px; }
.sen .tx { min-width: 0; }
.sen .tx b { font-weight: 600; display: block; }
.sen .tx span { color: var(--muted); }
.tip { display: inline-block; font: 600 10px/1 var(--f-body); letter-spacing: .06em; text-transform: uppercase; padding: 3px 5px; border-radius: 4px; margin-right: 6px; vertical-align: 1px; }
.t-tancament { background: var(--off-soft); background: color-mix(in srgb, var(--danger) 14%, transparent); color: var(--danger); }
.t-obertura { background: var(--ok-soft); color: var(--ok); }
.t-preparar, .t-tall { background: var(--warn-soft); color: var(--warn); }
.t-vigilar { background: var(--accent-soft); color: var(--accent); }
.sen.destacat .tx b { color: var(--accent); }
footer { color: var(--muted); font-size: 13px; display: grid; gap: 4px; }
footer p { margin: 0; max-width: 90ch; }

@media (max-width: 960px) {
  .cos { grid-template-columns: minmax(0, 1fr); }
  aside.senyals { position: static; max-height: 440px; order: -1; }
  .resum { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 680px) {
  .op > summary { grid-template-columns: 48px minmax(0, 1fr); }
  .op > summary .estat, .op > summary .zona { grid-column: 2; }
  .det { padding-left: 14px; }
  .camp input { width: 100%; }
  .compte { margin-left: 0; }
}
@media (prefers-reduced-motion: no-preference) { .op > summary { transition: background .15s; } .op > summary:hover { background: color-mix(in srgb, var(--accent) 4%, transparent); } }
</style>

<div class="pagina">
  <header class="cap">
    <div class="marca">
      <span class="eti" id="generat">Radar d'ajuts · subvencions · licitacions</span>
      <h1>Radar d'ajuts Stimulo</h1>
      <p class="sub">Oportunitats de finançament públic i privat ordenades per encaix amb Stimulo, amb la zona on ha d'estar el beneficiari i les properes senyals d'alerta.</p>
    </div>
    <div class="perfils" id="bloc-perfils">
      <span>Puntuació per a</span>
      <div class="seg" id="perfils" role="group" aria-label="Perfil"></div>
    </div>
  </header>

  <section class="resum" aria-label="Resum">
    <div><b id="k-obertes">–</b><span>obertes ara</span></div>
    <div><b id="k-properes">–</b><span>obren en 90 dies</span></div>
    <div><b id="k-senyals">–</b><span>senyals en 14 dies</span></div>
    <div><b id="k-a">–</b><span id="k-a-txt">prioritat A</span></div>
  </section>

  <section class="filtres" aria-label="Filtres">
    <div class="camp"><label for="f-estat">Estat</label>
      <select id="f-estat">
        <option value="actives">Obertes, properes i permanents</option>
        <option value="oberta">Obertes ara</option>
        <option value="propera">Properes</option>
        <option value="permanent">Tot l'any</option>
        <option value="totes">Totes (incl. tancades)</option>
      </select></div>
    <div class="camp"><label for="f-zona">Elegible per a un client a</label><select id="f-zona"></select></div>
    <div class="camp"><label for="f-nivell">Nivell</label>
      <select id="f-nivell">
        <option value="">Tots</option><option value="local">Local</option><option value="catalunya">Catalunya</option>
        <option value="estat">Estat</option><option value="europa">Europa</option><option value="internacional">Internacional</option>
      </select></div>
    <div class="camp"><label for="f-focus">Tema</label><select id="f-focus"><option value="">Tots</option></select></div>
    <div class="camp"><label for="f-text">Cerca</label><input id="f-text" type="search" placeholder="CDTI, prototip, defensa…"></div>
    <div class="camp"><label for="f-ordre">Ordre</label>
      <select id="f-ordre"><option value="punts">Per encaix</option><option value="data">Per data</option></select></div>
    <span class="compte" id="compte"></span>
  </section>

  <div class="cos">
    <main class="llista" id="llista" aria-live="polite"></main>
    <aside class="senyals" aria-labelledby="t-senyals">
      <h2 id="t-senyals">Properes senyals</h2>
      <p class="ajuda">90 dies. ≈ indica una data estimada a partir de l'edició anterior: serveix d'alerta, cal confirmar-la a la font.</p>
      <div id="agenda"></div>
    </aside>
  </div>

  <footer>
    <p>Puntuació 0–100: tema 40 · rol 20 · zona 15 · TRL 10 · import 15. A ≥ 80, B ≥ 65. «NE» = no elegible per zona i sense rol indirecte.</p>
    <p>Font: catàleg <code>data/convocatories.yaml</code> del repositori Radar-d-ajuts (recull 2025 + recerca d'octubre 2026). Confiança baixa = dada pendent de verificar.</p>
  </footer>
</div>

<script>
const D = __DADES__;
const AVUI = new Date(D.generat + "T00:00:00");
const NOMS_FOCUS = {deep_tech:"deep tech", dual:"ús dual", defensa:"defensa", espai:"espai", sostenibilitat:"sostenibilitat",
  economia_circular:"economia circular", transferencia:"transferència", prova_concepte:"prova de concepte", mobilitat:"mobilitat",
  automocio:"automoció", robotica:"robòtica", agrotech:"agrotech", aigua:"aigua", salut:"salut", dispositius_medics:"dispositius mèdics",
  fotonica:"fotònica", digital:"digital", ia:"IA", industria:"indústria", energia:"energia", internacionalitzacio:"internacionalització",
  creixement_startup:"creixement startup", talent:"talent", disseny:"disseny", cooperacio:"cooperació"};
const NOMS_ROL = {beneficiari:"beneficiari", soci:"soci", proveidor_extern:"proveïdor extern", subcontractat:"subcontractat", assessor:"assessor"};
const NOMS_INSTR = {subvencio:"Subvenció", prestec:"Préstec", prestec_parcialment_reemborsable:"Préstec parcialment reemborsable",
  cupo:"Cupó", premi:"Premi", capital:"Capital", acceleracio:"Acceleració", licitacio:"Licitació",
  compra_publica_innovacio:"Compra pública d'innovació", beca_contracte:"Contracte / beca", mixt:"Mixt"};
const NIVELLS = {local:"Local", catalunya:"Catalunya", estat:"Estat", europa:"Europa", internacional:"Internacional"};
const TIPUS = {preparar:"preparar", vigilar:"vigilar", obertura:"obre", tancament:"tanca", tall:"tall"};

const desa = (k, v) => { try { localStorage.setItem("radar-" + k, v); } catch (e) {} };
const llegeix = (k) => { try { return localStorage.getItem("radar-" + k); } catch (e) { return null; } };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const dataTxt = (iso) => { if (!iso) return "—"; const [a, m, d] = iso.split("-"); return `${d}/${m}/${a}`; };
const dataCurta = (iso) => { const [, m, d] = iso.split("-"); return `${d}/${m}`; };
const dies = (iso) => Math.round((new Date(iso + "T00:00:00") - AVUI) / 864e5);
const eur = (v) => v == null ? "—" : v >= 1e6 ? (v / 1e6).toLocaleString("ca-ES", {maximumFractionDigits: 1}) + " M€" : v.toLocaleString("ca-ES") + " €";

let perfil = llegeix("perfil") || D.perfils[0].id;
if (!D.perfils.some(p => p.id === perfil)) perfil = D.perfils[0].id;

function avantpassats(codi) { const out = []; while (codi) { out.push(codi); codi = D.zones[codi]?.pare; } return out; }
function elegible(c, zona) { if (!zona) return true; const cami = new Set(avantpassats(zona)); return c.zones.length === 0 || c.zones.some(z => cami.has(z)); }

function iniFiltres() {
  const seg = document.getElementById("perfils");
  document.getElementById("bloc-perfils").hidden = D.perfils.length < 2;
  seg.innerHTML = D.perfils.map(p => `<button type="button" data-id="${esc(p.id)}" aria-pressed="${p.id === perfil}">${esc(p.nom)}</button>`).join("");
  seg.addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; perfil = b.dataset.id; desa("perfil", perfil);
    seg.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", x.dataset.id === perfil)); pinta(); });
  const zones = Object.entries(D.zones).filter(([k]) => k !== "INT" && k !== "EU");
  document.getElementById("f-zona").innerHTML = `<option value="">Qualsevol zona</option>` +
    zones.map(([k, z]) => `<option value="${esc(k)}">${esc(z.nom)} (${esc(k)})</option>`).join("");
  const temes = [...new Set(D.convocatories.flatMap(c => c.focus))].sort((a, b) => (NOMS_FOCUS[a] || a).localeCompare(NOMS_FOCUS[b] || b, "ca"));
  document.getElementById("f-focus").innerHTML += temes.map(t => `<option value="${esc(t)}">${esc(NOMS_FOCUS[t] || t)}</option>`).join("");
  for (const id of ["f-estat", "f-zona", "f-nivell", "f-focus", "f-ordre"]) document.getElementById(id).addEventListener("change", pinta);
  document.getElementById("f-text").addEventListener("input", pinta);
  document.getElementById("generat").textContent = `Radar d'ajuts · actualitzat el ${dataTxt(D.generat)}`;
}

function refData(c) { const f = c.finestra; return f.estat === "oberta" ? f.tancament : (f.obertura || f.tancament); }

function filtra() {
  const estat = document.getElementById("f-estat").value, zona = document.getElementById("f-zona").value;
  const nivell = document.getElementById("f-nivell").value, focus = document.getElementById("f-focus").value;
  const text = document.getElementById("f-text").value.trim().toLowerCase();
  let llista = D.convocatories.filter(c => {
    const e = c.finestra.estat;
    if (estat === "actives" && !["oberta", "propera", "permanent"].includes(e)) return false;
    if (["oberta", "propera", "permanent"].includes(estat) && e !== estat) return false;
    if (nivell && c.nivell !== nivell) return false;
    if (focus && !c.focus.includes(focus)) return false;
    if (!elegible(c, zona)) return false;
    if (text && !(c.nom + " " + c.entitat + " " + c.descripcio + " " + c.focus.join(" ")).toLowerCase().includes(text)) return false;
    return true;
  });
  if (document.getElementById("f-ordre").value === "data") {
    llista.sort((a, b) => (refData(a) || "9999").localeCompare(refData(b) || "9999"));
  } else {
    llista.sort((a, b) => b.encaix[perfil].punts - a.encaix[perfil].punts || (refData(a) || "9999").localeCompare(refData(b) || "9999"));
  }
  return llista;
}

function trl(t) { if (!t) return "—"; return `<span class="trl" aria-hidden="true">${Array.from({length: 9}, (_, i) => `<i class="${i + 1 >= t[0] && i + 1 <= t[1] ? "on" : ""}"></i>`).join("")}</span>TRL ${t[0]}–${t[1]}`; }

function motius(llista) {
  return llista.map(m => m.startsWith("temes: ") ? "temes: " + m.slice(7).split(", ").map(t => NOMS_FOCUS[t] || t).join(", ")
    : m.startsWith("rol: ") ? "rol: " + (NOMS_ROL[m.slice(5)] || m.slice(5)) : m).join("; ");
}

function fila(c) {
  const e = c.encaix[perfil], f = c.finestra;
  const p = D.perfils.find(x => x.id === perfil);
  const quan = f.estat === "oberta" && f.tancament ? ` · ${dies(f.tancament)} dies` : "";
  const temes = e.motius.find(m => m.startsWith("temes: "));
  const focusPerfil = new Set(temes ? temes.slice(7).split(", ") : []);
  return `<details class="op">
    <summary>
      <span class="punts p-${e.prioritat}" title="Encaix amb ${esc(p.nom)}">${e.punts}<small>${e.prioritat}</small></span>
      <span class="tit"><strong>${esc(c.nom)}</strong>
        <span class="meta"><span>${esc(c.entitat)}</span><span>${NIVELLS[c.nivell]}</span><span>${e.rol ? esc(NOMS_ROL[e.rol]) : "sense rol"}</span><span>${eur(c.import_max_eur)}${c.intensitat_max ? " · " + c.intensitat_max + "%" : ""}</span></span></span>
      <span class="estat e-${f.estat}${f.estimada && f.estat !== "permanent" ? " e-estimada" : ""}">${esc(f.text)}${quan}</span>
      <span class="zona"><b>${esc(c.zona_etiqueta)}</b>${esc(c.zones.join(" · "))}</span>
    </summary>
    <div class="det">
      ${c.descripcio ? `<p>${esc(c.descripcio)}</p>` : ""}
      ${c.ajuda_text ? `<p><b>Ajut:</b> ${esc(c.ajuda_text)}</p>` : ""}
      <dl class="fitxa">
        <div><dt>Instrument</dt><dd>${esc(NOMS_INSTR[c.instrument] || c.instrument)}</dd></div>
        <div><dt>Qui hi pot optar</dt><dd>${esc(c.beneficiaris.join(", ").replaceAll("_", " "))}</dd></div>
        <div><dt>Rol de Stimulo</dt><dd>${esc(c.rols_stimulo.map(r => NOMS_ROL[r]).join(", ") || "—")}</dd></div>
        <div><dt>Maduresa</dt><dd>${trl(c.trl)}</dd></div>
        <div><dt>Àmbit geogràfic</dt><dd>${esc(c.ambit_geografic || "—")}</dd></div>
        <div><dt>Confiança de la fitxa</dt><dd class="conf conf-${esc(c.confianca)}">${esc(c.confianca)}${c.excel_fila ? ` · Excel fila ${c.excel_fila}` : ""}</dd></div>
      </dl>
      <div class="etiquetes">${c.focus.map(t => `<span class="${focusPerfil.has(t) ? "match" : ""}">${esc(NOMS_FOCUS[t] || t)}</span>`).join("")}</div>
      <p><b>Per què per a ${esc(p.nom)}:</b> ${esc(motius(e.motius) || "—")}</p>
      ${c.notes ? `<p class="nota">${esc(c.notes)}</p>` : ""}
      ${c.url ? `<p><a href="${esc(c.url)}" target="_blank" rel="noopener">Fitxa o font de la convocatòria ↗</a></p>` : ""}
    </div>
  </details>`;
}

function pintaAgenda() {
  const pA = new Set(D.convocatories.filter(c => c.encaix[perfil].prioritat === "A").map(c => c.id));
  const items = D.agenda.filter(s => dies(s.data) <= 90);
  const grups = new Map();
  for (const s of items) {
    const d = new Date(s.data + "T00:00:00"); const dl = new Date(d); dl.setDate(d.getDate() - ((d.getDay() + 6) % 7));
    const k = dl.toISOString().slice(0, 10); if (!grups.has(k)) grups.set(k, []); grups.get(k).push(s);
  }
  document.getElementById("agenda").innerHTML = [...grups].map(([k, ss]) => `<div class="setmana"><h3>Setmana del ${dataCurta(k)}</h3>${
    ss.map(s => `<div class="sen${pA.has(s.id) ? " destacat" : ""}"><time class="${s.estimada ? "est" : ""}" datetime="${s.data}">${dataCurta(s.data)}</time>
      <div class="tx"><b><span class="tip t-${s.tipus}">${TIPUS[s.tipus] || s.tipus}</span>${esc(s.nom)}</b><span>${esc(s.text)}</span></div></div>`).join("")}</div>`).join("")
    || `<p class="ajuda">Cap senyal en els propers 90 dies.</p>`;
}

function pinta() {
  const llista = filtra();
  document.getElementById("llista").innerHTML = llista.map(fila).join("") ||
    `<div class="buit">Cap convocatòria compleix aquests filtres. Prova «Totes (incl. tancades)» o treu la zona.</div>`;
  document.getElementById("compte").textContent = `${llista.length} de ${D.convocatories.length} convocatòries`;
  const C = D.convocatories, nom = D.perfils.find(p => p.id === perfil).nom;
  document.getElementById("k-obertes").textContent = C.filter(c => c.finestra.estat === "oberta").length;
  document.getElementById("k-properes").textContent = C.filter(c => c.finestra.estat === "propera" && c.finestra.obertura && dies(c.finestra.obertura) <= 90).length;
  document.getElementById("k-senyals").textContent = D.agenda.filter(s => dies(s.data) <= 14).length;
  document.getElementById("k-a").textContent = C.filter(c => c.encaix[perfil].prioritat === "A" && c.finestra.estat !== "tancada").length;
  document.getElementById("k-a-txt").textContent = D.perfils.length > 1 ? `prioritat A per a ${nom}` : "prioritat A";
  pintaAgenda();
}

iniFiltres();
pinta();
</script>
"""


def genera(cat: Cataleg, avui: dt.date, dir_sortida: Path, autonom: bool = True, nom: str = "radar.html") -> Path:
    dades = json.dumps(dades_json(cat, avui), ensure_ascii=False).replace("</", "<\\/")
    cos = PLANTILLA.replace("__DADES__", dades)
    if autonom:
        cos = ('<!doctype html>\n<html lang="ca">\n<head>\n<meta charset="utf-8">\n'
               '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
               + cos.replace("</style>\n", "</style>\n</head>\n<body>\n", 1) + "</body>\n</html>\n")
    desti = dir_sortida / nom
    desti.write_text(cos, encoding="utf-8")
    return desti
