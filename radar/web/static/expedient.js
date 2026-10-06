// Xat de l'expedient: envia el missatge, llegeix la resposta en temps real (SSE sobre fetch) i
// permet encadenar la redacció de tots els documents ("Preparar-ho tot").
const DADES = JSON.parse(document.getElementById("expedient-dades").textContent);
const $ = id => document.getElementById(id);
const missatges = $("missatges"), text = $("text"), estatXat = $("estat-xat");
const botoEnvia = $("envia"), botoTot = $("tot"), botoAtura = $("atura");
const pensament = $("pensament"), pensamentText = $("pensament-text");
const NOMS_EINES = { web_search: "Cercant al web…", web_fetch: "Llegint una pàgina web…" };
let ocupat = false, aturar = false;

function esc(s) { return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
function avall() { window.scrollTo({ top: document.body.scrollHeight }); }
function estat(t, error = false) { estatXat.textContent = t; estatXat.classList.toggle("error", error); }

function bloqueja(si) {
  ocupat = si;
  botoEnvia.disabled = si; botoTot.disabled = si;
  document.querySelectorAll("button.plantilla").forEach(b => { b.disabled = si; });
}

function afegeix(rol, contingut) {
  const art = document.createElement("article");
  art.className = `msg msg-${rol}`;
  if (rol === "user") art.innerHTML = `<p class="text-usuari">${esc(contingut)}</p>`;
  else { art.classList.add("escrivint"); art.innerHTML = `<p class="text-usuari"></p>`; }
  missatges.appendChild(art);
  document.querySelector(".benvinguda")?.remove();
  avall();
  return art;
}

// Un torn complet. Torna true si ha acabat bé.
async function torn(missatge, accio = "") {
  const visible = accio ? `Prepara: ${DADES.titols[accio]}${missatge ? " — " + missatge : ""}` : missatge;
  afegeix("user", visible);
  const resposta = afegeix("assistant", "");
  const sortida = resposta.querySelector("p");
  pensament.hidden = true; pensamentText.textContent = "";
  estat(accio ? `Redactant «${DADES.titols[accio]}»…` : "L'assistent està pensant…");
  let r;
  try {
    r = await fetch(`/expedients/${DADES.id}/xat`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: missatge, accio }),
    });
  } catch { estat("No s'ha pogut connectar amb el servidor.", true); resposta.remove(); return false; }
  if (!r.ok) { estat(await r.text(), true); resposta.remove(); return false; }

  const lector = r.body.getReader(), decod = new TextDecoder();
  let buffer = "", ok = false, error = false;
  while (true) {
    const { value, done } = await lector.read();
    if (done) break;
    buffer += decod.decode(value, { stream: true });
    let i;
    while ((i = buffer.indexOf("\n\n")) >= 0) {
      const bloc = buffer.slice(0, i); buffer = buffer.slice(i + 2);
      if (!bloc.startsWith("data: ")) continue;
      const ev = JSON.parse(bloc.slice(6));
      if (ev.tipus === "text") { sortida.textContent += ev.text; estat("Escrivint…"); avall(); }
      else if (ev.tipus === "pensament") { pensament.hidden = false; pensamentText.textContent += ev.text; }
      else if (ev.tipus === "eina") estat(NOMS_EINES[ev.nom] || "Consultant fonts…");
      else if (ev.tipus === "avis") estat(ev.text, true);
      else if (ev.tipus === "document") estat(`Desat: ${ev.titol}`);
      else if (ev.tipus === "error") { estat(ev.text, true); error = true; }
      else if (ev.tipus === "fi") ok = true;
    }
  }
  if (error) resposta.remove();
  return ok && !error;
}

async function envia(accio = "") {
  if (ocupat) return;
  const missatge = text.value.trim();
  if (!accio && !missatge) { text.focus(); return; }
  bloqueja(true);
  const ok = await torn(missatge, accio);
  bloqueja(false);
  if (ok) { text.value = ""; location.reload(); }
}

$("entrada").addEventListener("submit", ev => { ev.preventDefault(); envia(); });
text.addEventListener("keydown", ev => {
  if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); envia(); }
});
document.querySelectorAll("button.plantilla").forEach(b => {
  if (!DADES.pendents.includes(b.dataset.accio)) b.classList.add("fet");
  b.addEventListener("click", () => envia(b.dataset.accio));
});

// Preparar-ho tot: redacta, un darrere l'altre, els documents que encara no existeixen
const pendents = DADES.pendents;
$("tot-ajuda").textContent = pendents.length
  ? `Redacta en ordre els ${pendents.length} documents que falten (${pendents.map(t => DADES.titols[t]).join(", ")}). Cada document té en compte els anteriors. Es pot aturar en qualsevol moment.`
  : "Ja hi ha tots els documents. Pots refer-ne qualsevol amb els botons de dalt.";
botoTot.disabled = !pendents.length;
botoTot.addEventListener("click", async () => {
  if (ocupat || !pendents.length) return;
  if (!confirm(`Es redactaran ${pendents.length} documents seguits. Pot trigar una bona estona i consumeix crèdit de l'API. Continuar?`)) return;
  bloqueja(true); aturar = false; botoAtura.hidden = false;
  const indicacions = text.value.trim();
  let fets = 0;
  for (const accio of pendents) {
    if (aturar) break;
    const ok = await torn(indicacions, accio);
    if (!ok) break;
    fets++;
  }
  botoAtura.hidden = true; bloqueja(false);
  if (fets) location.reload();
});
botoAtura.addEventListener("click", () => { aturar = true; estat("S'aturarà en acabar el document actual."); });

if (estatXat.textContent.trim()) bloqueja(true);
avall();
