const D = window.RADAR_DADES || JSON.parse(document.getElementById("radar-dades").textContent);
const APP = window.RADAR_APP || (document.getElementById("radar-app") ? JSON.parse(document.getElementById("radar-app").textContent) : null);
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
  for (const id of ["f-estat", "f-linia", "f-zona", "f-nivell", "f-focus", "f-ordre"]) document.getElementById(id).addEventListener("change", pinta);
  document.getElementById("f-text").addEventListener("input", pinta);
  document.getElementById("generat").textContent = `Radar d'ajuts · actualitzat el ${dataTxt(D.generat)}`;
}

function refData(c) { const f = c.finestra; return f.estat === "oberta" ? f.tancament : (f.obertura || f.tancament); }

function filtra() {
  const estat = document.getElementById("f-estat").value, zona = document.getElementById("f-zona").value;
  const nivell = document.getElementById("f-nivell").value, focus = document.getElementById("f-focus").value;
  const linia = document.getElementById("f-linia").value;
  const text = document.getElementById("f-text").value.trim().toLowerCase();
  let llista = D.convocatories.filter(c => {
    const e = c.finestra.estat;
    if (estat === "actives" && !["oberta", "propera", "permanent"].includes(e)) return false;
    if (["oberta", "propera", "permanent"].includes(estat) && e !== estat) return false;
    if (nivell && c.nivell !== nivell) return false;
    if (linia && !(c.linies || []).includes(linia)) return false;
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
        <span class="meta"><span>${esc(c.entitat)}</span><span>${NIVELLS[c.nivell]}</span><span>${e.rol ? esc(NOMS_ROL[e.rol]) : "sense rol"}</span><span>${eur(c.import_max_eur)}${c.intensitat_max ? " · " + c.intensitat_max + "%" : ""}</span>${c.compartir_clients ? `<span class="xip-clients" title="Línia per compartir amb clients i potencials clients">per a clients</span>` : ""}</span></span>
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
      <p class="accions">${c.url ? `<a href="${esc(c.url)}" target="_blank" rel="noopener">Fitxa o font de la convocatòria ↗</a>` : ""}
        ${APP ? (APP.expedients[c.id] ? `<a class="boto" href="/expedients/${APP.expedients[c.id]}">Obrir l'expedient</a>`
          : `<a class="boto" href="/expedients/nou?convocatoria=${encodeURIComponent(c.id)}">Preparar sol·licitud</a>`) : ""}</p>
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
