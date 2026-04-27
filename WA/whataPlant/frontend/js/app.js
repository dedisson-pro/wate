// API_BASE : toujours sur le même serveur Flask (port 5000 local, domaine Railway en prod)
const API_BASE = `${window.location.protocol}//${window.location.hostname}:${window.location.port || (window.location.protocol === 'https:' ? 443 : 80)}/api`.replace(/:80\/api$/, '/api').replace(/:443\/api$/, '/api');

// Simplification : même origine, juste /api
const _API_BASE = `${window.location.origin}/api`;
window.API_BASE = _API_BASE;

document.querySelectorAll(".nav-tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".nav-tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(s => s.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(`tab-${tab.dataset.tab}`).classList.add("active");
    if (tab.dataset.tab === "history") loadHistory();
    if (tab.dataset.tab === "dashboard") loadDashboard();
  });
});

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

function badgeClass(val) {
  if (!val) return "badge-no";
  const v = val.toLowerCase();
  if (v === "oui") return "badge-yes";
  if (v === "non") return "badge-no";
  return "badge-partial";
}

function formatDate(dt) {
  return new Date(dt).toLocaleDateString("fr-FR", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit"
  });
}

window.badgeClass = badgeClass;
window.formatDate = formatDate;
