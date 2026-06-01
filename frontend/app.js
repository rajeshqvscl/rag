// Central API Configuration
const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
let API = isLocalhost ? "http://localhost:8080" : (window.API_URL || "");

console.log("Using API:", API);

function loadPage(page, el) {
  currentPage = page;
  document.querySelectorAll(".nav-item").forEach(i => i.classList.remove("active"));
  if (el) {
    el.classList.add("active");
    el.setAttribute('data-page', page);
  }

  switch (page) {
    case 'revert':
      loadRevert();
      break;
    case 'intelligence':
      loadIntelligence();
      break;
    case 'settings':
      loadSettings();
      break;
    default:
      document.getElementById("content").innerHTML = `
        <div class="empty-state">
          <h2>${page}</h2>
        </div>
      `;
  }
}

setTimeout(() => {
  if (window.lucide) lucide.createIcons();
}, 0);

window.onload = () => {
  loadPage("revert", document.querySelector(".nav-item"));
  initDarkMode();
  applySavedLogo();
};

function initDarkMode() {
  const savedMode = localStorage.getItem('darkMode');
  if (savedMode === 'light') {
    document.body.classList.add('light-mode');
    updateDarkModeIcon();
  }
}

function toggleDarkMode() {
  document.body.classList.toggle('light-mode');
  const isLight = document.body.classList.contains('light-mode');
  localStorage.setItem('darkMode', isLight ? 'light' : 'dark');
  updateDarkModeIcon();
  showToast(isLight ? 'Light mode enabled' : 'Dark mode enabled', 'info');
}

function updateDarkModeIcon() {
  const icon = document.getElementById('dark-mode-icon');
  if (icon) {
    icon.setAttribute('data-lucide', document.body.classList.contains('light-mode') ? 'sun' : 'moon');
    if (window.lucide) lucide.createIcons();
  }
}

function fetchWithTimeout(url, ms) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  return fetch(url, { signal: controller.signal }).finally(() => clearTimeout(timer));
}

let currentPage = 'revert';

function setCurrentPage(page) {
  currentPage = page;
}

function applySavedLogo() {
  const mode = localStorage.getItem('pitchMode') || 'general';
  const branding = {
    general: { name: 'FinRAG', subtitle: '4.6' },
    investor: { name: 'FinRAG', subtitle: 'Capital' },
    enterprise: { name: 'Enterprise Brain', subtitle: 'AI' },
    technical: { name: 'Multi-Agent', subtitle: 'Cloud' }
  };
  const b = branding[mode] || branding.general;
  const logoMain = document.querySelector('.logo-main');
  const logoSub = document.querySelector('.logo-sub');
  if (logoMain) logoMain.textContent = b.name;
  if (logoSub) logoSub.textContent = b.subtitle;
}

function applyPitchLogo(mode) {
  const branding = {
    general: { name: 'FinRAG', subtitle: '4.6' },
    investor: { name: 'FinRAG', subtitle: 'Capital' },
    enterprise: { name: 'Enterprise Brain', subtitle: 'AI' },
    technical: { name: 'Multi-Agent', subtitle: 'Cloud' }
  };
  const b = branding[mode] || branding.general;
  const logoMain = document.querySelector('.logo-main');
  const logoSub = document.querySelector('.logo-sub');
  if (logoMain) logoMain.textContent = b.name;
  if (logoSub) logoSub.textContent = b.subtitle;
}