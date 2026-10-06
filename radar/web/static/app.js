// Comportaments comuns (sense JavaScript en línia: la CSP només permet fitxers d'aquest servidor)
document.querySelectorAll("select[data-navega]").forEach(sel => {
  sel.addEventListener("change", () => {
    const url = new URL(location.href);
    if (sel.value) url.searchParams.set(sel.dataset.navega, sel.value); else url.searchParams.delete(sel.dataset.navega);
    location.href = url.toString();
  });
});
document.querySelectorAll("form[data-confirma]").forEach(f => {
  f.addEventListener("submit", ev => { if (!confirm(f.dataset.confirma)) ev.preventDefault(); });
});
document.querySelectorAll("[data-copia]").forEach(b => {
  b.addEventListener("click", async () => {
    const font = document.getElementById(b.dataset.copia);
    const text = font.value !== undefined ? font.value : font.textContent;
    const original = b.textContent;
    try { await navigator.clipboard.writeText(text); b.textContent = "Copiat ✓"; }
    catch { b.textContent = "No s'ha pogut copiar"; }
    setTimeout(() => { b.textContent = original; }, 1800);
  });
});
