function loadSettings() {
  document.getElementById("content").innerHTML = `
    <div class="settings-page">
      <div class="card">
        <div class="card-header">
          <div class="card-title">SYSTEM STATUS</div>
          <span class="card-icon" data-lucide="activity"></span>
        </div>
        <div class="card-body" id="sys-status">
          <div class="status-row"><span class="status-label">Backend</span><span class="status-value" id="be-status"><span class="status-dot status-dot-warn"></span> Checking...</span></div>
          <div class="status-row"><span class="status-label">Database (Neon)</span><span class="status-value" id="db-status"><span class="status-dot status-dot-warn"></span> Checking...</span></div>
          <div class="status-row"><span class="status-label">API URL</span><span class="status-value mono">${API}</span></div>
          <div class="status-row"><span class="status-label">Engine</span><span class="status-value">Groq Llama 3.1</span></div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title">APPEARANCE</div>
          <span class="card-icon" data-lucide="palette"></span>
        </div>
        <div class="card-body">
          <div class="appearance-toggle">
            <button class="appearance-btn ${document.body.classList.contains('light-mode') ? '' : 'active'}" onclick="setAppearance('dark')">
              <span class="appearance-icon">🌙</span>
              <span class="appearance-label">Dark</span>
            </button>
            <button class="appearance-btn ${document.body.classList.contains('light-mode') ? 'active' : ''}" onclick="setAppearance('light')">
              <span class="appearance-icon">☀️</span>
              <span class="appearance-label">Light</span>
            </button>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title">DATABASE OVERVIEW</div>
          <span class="card-icon" data-lucide="database"></span>
        </div>
        <div class="card-body" id="db-overview">
          <p style="color: #64748b; font-size: 13px;">Loading table stats...</p>
        </div>
      </div>



      <div class="card">
        <div class="card-header">
          <div class="card-title">ABOUT</div>
          <span class="card-icon" data-lucide="info"></span>
        </div>
        <div class="card-body">
          <div class="about-grid">
            <div class="about-item"><span class="about-label">Version</span><span class="about-value">FinRAG 4.6</span></div>
            <div class="about-item"><span class="about-label">LLM Engine</span><span class="about-value">Groq Llama 3.1 8B</span></div>
            <div class="about-item"><span class="about-label">Database</span><span class="about-value">Neon (PostgreSQL)</span></div>
            <div class="about-item"><span class="about-label">Deployed</span><span class="about-value">${API || 'Local'}</span></div>
          </div>
        </div>
      </div>
    </div>
  `;
  lucide.createIcons();
  checkStatus();
  loadDbStats();
}

async function checkStatus() {
  try {
    const res = await fetchWithTimeout(API + '/health', 5000);
    if (res.ok) {
      document.getElementById('be-status').innerHTML = '<span class="status-dot status-dot-ok"></span> Connected';
    } else {
      document.getElementById('be-status').innerHTML = '<span class="status-dot status-dot-err"></span> Error (status ' + res.status + ')';
    }
  } catch {
    document.getElementById('be-status').innerHTML = '<span class="status-dot status-dot-err"></span> Unreachable';
  }
  try {
    const res = await fetchWithTimeout(API + '/test-db', 5000);
    const data = await res.json();
    if (data.db === 'connected') {
      document.getElementById('db-status').innerHTML = '<span class="status-dot status-dot-ok"></span> Connected';
    } else {
      document.getElementById('db-status').innerHTML = '<span class="status-dot status-dot-err"></span> Error';
    }
  } catch {
    document.getElementById('db-status').innerHTML = '<span class="status-dot status-dot-err"></span> Unreachable';
  }
}

async function loadDbStats() {
  try {
    const res = await fetchWithTimeout(API + '/db/tables', 30000);
    if (!res.ok) throw new Error('Server returned ' + res.status);
    const tables = await res.json();
    if (tables.error) throw new Error(tables.error);
    if (!Array.isArray(tables)) throw new Error('Invalid response');
    let html = '<div class="db-stats">';
    tables.forEach(t => {
      html += `
        <div class="db-stat-row">
          <span class="db-stat-name">${t.label}</span>
          <span class="db-stat-counts">
            <span class="db-stat-active">${t.active_count} active</span>
            ${t.archived_count > 0 ? `<span class="db-stat-archived">${t.archived_count} archived</span>` : ''}
            <span class="db-stat-total">${t.row_count} total</span>
          </span>
        </div>
      `;
    });
    html += '</div>';
    document.getElementById('db-overview').innerHTML = html;
  } catch {
    document.getElementById('db-overview').innerHTML = '<p style="color: #ef4444; font-size: 13px;">Could not load database stats</p>';
  }
}

function setAppearance(mode) {
  if (mode === 'light') {
    document.body.classList.add('light-mode');
    localStorage.setItem('darkMode', 'light');
  } else {
    document.body.classList.remove('light-mode');
    localStorage.setItem('darkMode', 'dark');
  }
  document.querySelectorAll('.appearance-btn').forEach(b => b.classList.remove('active'));
  document.querySelector(`.appearance-btn[onclick*="${mode}"]`).classList.add('active');
  if (typeof updateDarkModeIcon === 'function') updateDarkModeIcon();
}

window.setAppearance = setAppearance;
window.loadSettings = loadSettings;
