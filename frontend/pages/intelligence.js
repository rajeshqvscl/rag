let currentTable = 'intelligence_cloud';
let currentPageNum = 1;
let currentArchived = false;
let currentSearch = '';
let tableColumns = [];
let allTableMeta = [];
let _tableRows = [];
const PER_PAGE = 50;

function loadIntelligence() {
  document.getElementById("content").innerHTML = `
    <div class="db-manager">
      <div class="db-manager-header">
        <div class="db-manager-title">
          <span data-lucide="database" style="width: 20px; height: 20px; color: #38bdf8;"></span>
          INTELLIGENCE CLOUD
          <span class="db-manager-sub">Database Manager</span>
        </div>
      </div>

      <div class="db-toolbar">
        <div class="db-toolbar-left">
          <select id="table-selector" class="db-table-select" onchange="switchTable(this.value)">
            <option value="">Loading tables...</option>
          </select>
        </div>
        <div class="db-toolbar-center">
          <input type="text" id="db-search" class="db-search-input" placeholder="Search records..." oninput="debounceSearch()">
        </div>
        <div class="db-toolbar-right">
          <label class="db-archived-toggle">
            <input type="checkbox" id="archived-toggle" onchange="toggleArchived()">
            <span>Show archived</span>
          </label>
        </div>
      </div>

      <div class="db-table-wrapper" id="db-table-wrapper">
        <div class="db-loading">Loading data...</div>
      </div>

      <div class="db-pagination" id="db-pagination"></div>

      <div class="db-selection-bar" id="selection-bar">
        <span id="selection-count" class="selection-count">0 selected</span>
        <button class="db-btn db-btn-archive" onclick="batchArchive()">📦 Archive (Soft Delete)</button>
        <button class="db-btn db-btn-danger" onclick="batchDelete()">🗑️ Delete Permanently</button>
        <button class="db-btn db-btn-restore" id="restore-btn" style="display:none" onclick="batchRestore()">♻️ Restore</button>
      </div>
    </div>
  `;
  lucide.createIcons();
  loadTableList();
}

async function loadTableList() {
  try {
    const res = await fetchWithTimeout(API + '/db/tables', 30000);
    if (!res.ok) {
      throw new Error('Server returned ' + res.status + (res.status === 404 ? ' (endpoint not found)' : ''));
    }
    allTableMeta = await res.json();
    if (allTableMeta.error) throw new Error(allTableMeta.error);
    if (!Array.isArray(allTableMeta) || allTableMeta.length === 0) {
      throw new Error('No tables returned from server');
    }
    const sel = document.getElementById('table-selector');
    sel.innerHTML = allTableMeta.map(t =>
      `<option value="${t.name}">${t.label} (${t.active_count} active${t.archived_count > 0 ? ', ' + t.archived_count + ' archived' : ''})</option>`
    ).join('');
    currentTable = allTableMeta[0]?.name || 'intelligence_cloud';
    sel.value = currentTable;
    loadTableData();
  } catch (err) {
    document.getElementById('table-selector').innerHTML = '<option value="">Tables unavailable</option>';
    document.getElementById('db-table-wrapper').innerHTML = `
      <div class="db-error">
        <p>${err.message.includes('endpoint') ? '❌ Server missing /db/tables endpoint. Did you restart the backend?' : 
              err.message.includes('No tables') ? '❌ Backend returned empty table list' : 
              '❌ Could not connect to database'}</p>
        <p style="font-size:12px;color:#64748b;margin-top:8px;">${err.message}</p>
        <button onclick="loadTableList()" class="db-btn" style="margin-top:16px;background:#38bdf8;color:#020617;">Retry</button>
      </div>`;
  }
}

async function loadTableData() {
  const wrapper = document.getElementById('db-table-wrapper');
  wrapper.innerHTML = '<div class="db-loading">Loading data...</div>';
  document.getElementById('selection-bar').classList.remove('visible');
  document.getElementById('db-pagination').innerHTML = '';

  try {
    const params = new URLSearchParams({
      include_archived: currentArchived,
      search: currentSearch,
      page: currentPageNum,
      per_page: PER_PAGE,
    });
    const res = await fetchWithTimeout(API + '/db/table/' + currentTable + '?' + params, 30000);
    if (!res.ok) {
      throw new Error('Server returned ' + res.status);
    }
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    renderTable(data);
  } catch (err) {
    wrapper.innerHTML = `<div class="db-error">Failed to load table data: ${err.message}</div>`;
  }
}

function renderTable(data) {
  const wrapper = document.getElementById('db-table-wrapper');
  if (!data.rows || data.rows.length === 0) {
    wrapper.innerHTML = '<div class="db-empty">No records found</div>';
    document.getElementById('db-pagination').innerHTML = '';
    return;
  }

  _tableRows = data.rows;
  const columns = Object.keys(data.rows[0]).filter(c => c !== 'insights' && c !== 'messages' && c !== 'context_documents');
  tableColumns = columns;

  let html = '<table class="db-table"><thead><tr>';
  html += '<th class="db-checkbox-col"><input type="checkbox" id="select-all" onchange="toggleSelectAll(this.checked)"></th>';
  html += '<th style="width:50px;text-align:center;">View</th>';
  columns.forEach(c => {
    const label = c.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    html += `<th>${label}</th>`;
  });
  html += '</tr></thead><tbody>';

  data.rows.forEach((row, idx) => {
    const isArchived = row.archived_at;
    html += `<tr class="${isArchived ? 'archived' : ''}" data-id="${row.id}">`;
    html += `<td><input type="checkbox" class="row-checkbox" value="${row.id}" onchange="updateSelection()"></td>`;
    html += `<td style="text-align:center;"><button class="db-btn db-btn-view" onclick="event.stopPropagation();viewRecordDetail(${idx})" title="View full details">👁</button></td>`;
    columns.forEach(c => {
      let val = row[c];
      if (val === null || val === undefined) val = '-';
      if (typeof val === 'object') val = JSON.stringify(val).substring(0, 100);
      const isLongText = typeof val === 'string' && val.length > 80;
      const isDeckTable = currentTable === 'pitch_deck_library';
      if (isDeckTable && (c === 'summary' || c === 'email_draft')) {
        if (val !== '-') {
          const label = c === 'summary' ? '📄 Summary' : '📧 Email';
          html += `<td><button class="db-btn db-btn-view" onclick="event.stopPropagation();viewRecordDetail(${idx})" style="font-size:11px;" title="View full ${c}">${label}</button></td>`;
          return;
        }
        html += `<td>${val}</td>`;
        return;
      }
      if (isLongText) val = val.substring(0, 80) + '...';
      if (c === 'timestamp' || c === 'created_at' || c === 'last_active' || c === 'archived_at' || c === 'processed_at') {
        if (val !== '-') {
          try { val = new Date(val).toLocaleString(); } catch {}
        }
      }
      html += `<td title="${(row[c] !== null && row[c] !== undefined) ? String(row[c]).substring(0, 500) : ''}">${val}</td>`;
    });
    html += '</tr>';
  });

  html += '</tbody></table>';
  wrapper.innerHTML = html;

  renderPagination(data.total, data.page, data.per_page);

  if (currentArchived) {
    document.getElementById('restore-btn').style.display = 'inline-flex';
  } else {
    document.getElementById('restore-btn').style.display = 'none';
  }
}

function renderPagination(total, page, perPage) {
  const totalPages = Math.ceil(total / perPage) || 1;
  const pag = document.getElementById('db-pagination');
  if (totalPages <= 1) {
    pag.innerHTML = `<span class="db-page-info">${total} record${total !== 1 ? 's' : ''}</span>`;
    return;
  }
  let html = `<button class="db-page-btn" onclick="goToPage(${page - 1})" ${page <= 1 ? 'disabled' : ''}>&#9664;</button>`;
  const start = Math.max(1, page - 2);
  const end = Math.min(totalPages, page + 2);
  for (let i = start; i <= end; i++) {
    html += `<button class="db-page-btn ${i === page ? 'active' : ''}" onclick="goToPage(${i})">${i}</button>`;
  }
  html += `<button class="db-page-btn" onclick="goToPage(${page + 1})" ${page >= totalPages ? 'disabled' : ''}>&#9654;</button>`;
  html += `<span class="db-page-info">${total} record${total !== 1 ? 's' : ''}</span>`;
  pag.innerHTML = html;
}

function toggleSelectAll(checked) {
  document.querySelectorAll('.row-checkbox').forEach(cb => cb.checked = checked);
  updateSelection();
}

function updateSelection() {
  const selected = document.querySelectorAll('.row-checkbox:checked');
  const bar = document.getElementById('selection-bar');
  const count = document.getElementById('selection-count');
  if (selected.length > 0) {
    bar.classList.add('visible');
    count.textContent = `${selected.length} selected`;
  } else {
    bar.classList.remove('visible');
  }
}

function getSelectedIds() {
  return Array.from(document.querySelectorAll('.row-checkbox:checked')).map(cb => parseInt(cb.value));
}

async function batchDelete() {
  const ids = getSelectedIds();
  if (ids.length === 0) return;
  const confirmed = await showConfirmModal(
    '🗑️ Permanently Delete',
    `Are you sure you want to permanently delete <strong>${ids.length}</strong> record${ids.length !== 1 ? 's' : ''} from the Neon database?<br><br><span style="color:#ef4444;">This action cannot be undone.</span>`,
    'Delete Permanently',
    'danger'
  );
  if (!confirmed) return;
  try {
    const res = await fetch(API + '/db/batch-delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ table: currentTable, ids })
    });
    const data = await res.json();
    if (data.status === 'ok') {
      showToast(`Deleted ${data.deleted} record${data.deleted !== 1 ? 's' : ''}`, 'success');
      loadTableData();
    } else {
      showToast('Delete failed: ' + (data.error || 'unknown error'), 'error');
    }
  } catch {
    showToast('Delete failed - server error', 'error');
  }
}

async function batchArchive() {
  const ids = getSelectedIds();
  if (ids.length === 0) return;
  const reason = await showPromptModal(
    '📦 Archive Records',
    `Archive <strong>${ids.length}</strong> record${ids.length !== 1 ? 's' : ''}? They can be restored later.`,
    'Archive',
    'reason'
  );
  if (reason === null) return;
  try {
    const res = await fetch(API + '/db/batch-archive', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ table: currentTable, ids, reason })
    });
    const data = await res.json();
    if (data.status === 'ok') {
      showToast(`Archived ${data.archived} record${data.archived !== 1 ? 's' : ''}`, 'success');
      loadTableData();
    } else {
      showToast('Archive failed: ' + (data.error || 'unknown error'), 'error');
    }
  } catch {
    showToast('Archive failed - server error', 'error');
  }
}

async function batchRestore() {
  const ids = getSelectedIds();
  if (ids.length === 0) return;
  const confirmed = await showConfirmModal(
    '♻️ Restore Records',
    `Restore <strong>${ids.length}</strong> archived record${ids.length !== 1 ? 's' : ''}?`,
    'Restore',
    'restore'
  );
  if (!confirmed) return;
  try {
    const res = await fetch(API + '/db/batch-restore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ table: currentTable, ids })
    });
    const data = await res.json();
    if (data.status === 'ok') {
      showToast(`Restored ${data.restored} record${data.restored !== 1 ? 's' : ''}`, 'success');
      loadTableData();
    } else {
      showToast('Restore failed: ' + (data.error || 'unknown error'), 'error');
    }
  } catch {
    showToast('Restore failed - server error', 'error');
  }
}

function switchTable(name) {
  currentTable = name;
  currentPageNum = 1;
  currentArchived = false;
  currentSearch = '';
  document.getElementById('archived-toggle').checked = false;
  document.getElementById('db-search').value = '';
  document.getElementById('selection-bar').classList.remove('visible');
  loadTableData();
}

function toggleArchived() {
  currentArchived = document.getElementById('archived-toggle').checked;
  currentPageNum = 1;
  loadTableData();
}

let searchTimeout;
function debounceSearch() {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(() => {
    currentSearch = document.getElementById('db-search').value.trim();
    currentPageNum = 1;
    loadTableData();
  }, 300);
}

function goToPage(page) {
  currentPageNum = page;
  loadTableData();
}

// Modal helpers using ui.js
function showConfirmModal(title, message, btnLabel, btnType) {
  return new Promise(resolve => {
    const content = `
      <div class="modal-confirm">
        <h3 style="margin:0 0 12px;color:#f8fafc;">${title}</h3>
        <p style="color:#94a3b8;font-size:14px;line-height:1.5;">${message}</p>
        <div class="modal-actions" style="display:flex;gap:10px;justify-content:flex-end;margin-top:20px;">
          <button class="db-btn" onclick="closeModal(); window.__modalResolve(false)" style="background:#1e293b;color:#94a3b8;border:1px solid #334155;">Cancel</button>
          <button class="db-btn ${btnType === 'danger' ? 'db-btn-danger' : btnType === 'restore' ? 'db-btn-restore' : 'db-btn-archive'}" onclick="closeModal(); window.__modalResolve(true)">${btnLabel}</button>
        </div>
      </div>
    `;
    window.__modalResolve = resolve;
    showModal(content);
  });
}

function showPromptModal(title, message, btnLabel, inputType) {
  return new Promise(resolve => {
    const content = `
      <div class="modal-confirm">
        <h3 style="margin:0 0 12px;color:#f8fafc;">${title}</h3>
        <p style="color:#94a3b8;font-size:14px;line-height:1.5;">${message}</p>
        <div style="margin-top:12px;">
          <label style="color:#94a3b8;font-size:12px;display:block;margin-bottom:4px;">Reason (optional):</label>
          <input type="text" id="prompt-reason" class="db-search-input" style="width:100%;padding:10px;" placeholder="e.g. User requested cleanup">
        </div>
        <div class="modal-actions" style="display:flex;gap:10px;justify-content:flex-end;margin-top:20px;">
          <button class="db-btn" onclick="closeModal(); window.__modalResolve(null)" style="background:#1e293b;color:#94a3b8;border:1px solid #334155;">Cancel</button>
          <button class="db-btn db-btn-archive" onclick="closeModal(); window.__modalResolve(document.getElementById('prompt-reason').value)">${btnLabel}</button>
        </div>
      </div>
    `;
    window.__modalResolve = resolve;
    showModal(content);
  });
}

function viewRecordDetail(idx) {
  const row = _tableRows[idx];
  if (!row) return;
  const isDeck = currentTable === 'pitch_deck_library';
  content = isDeck ? renderDeckDetail(row) : renderRevertDetail(row);
  showModal(content);
}

function renderRevertDetail(row) {
  const emailRaw = row.email_draft || '';
  const emailHtml = emailRaw.replace(/\n/g, '<br>');
  const signals = row.signals || row.signals_json || '[]';
  let signalsHtml = '';
  try {
    const arr = typeof signals === 'string' ? JSON.parse(signals) : signals;
    if (Array.isArray(arr)) signalsHtml = arr.map(s => `<span class="detail-tag">${s}</span>`).join(' ');
  } catch { signalsHtml = signals; }

  const fields = [
    ['Company', row.company],
    ['Type', row.type],
    ['Status', row.status],
    ['Intent', row.intent],
    ['Confidence', row.confidence != null ? row.confidence + '%' : '-'],
    ['Score', row.score != null ? row.score : '-'],
    ['Priority', row.priority],
    ['Urgency Level', row.urgency_level],
    ['Query Type', row.query_type],
    ['Cheque Size', row.cheque_size],
    ['Sector', row.sector],
    ['Sender', row.sender],
    ['Subject', row.subject],
    ['Body', row.body],
    ['Next Step', row.next_step],
    ['Reasoning', row.reasoning],
    ['Document Path', row.document_path],
    ['Processed At', row.processed_at ? new Date(row.processed_at).toLocaleString() : '-'],
    ['Timestamp', row.timestamp ? new Date(row.timestamp).toLocaleString() : '-'],
  ];

  return `
    <div class="detail-modal">
      <div class="detail-header">
        <div class="detail-title">${row.company || 'Record'} <span class="detail-id">#${row.id}</span></div>
        <button class="detail-close" onclick="closeModal()">&times;</button>
      </div>
      <div class="detail-body">
        <div class="detail-section">
          <div class="detail-section-title">📋 Signals</div>
          <div class="detail-signals">${signalsHtml || 'None'}</div>
        </div>

        ${emailRaw ? `
        <div class="detail-section">
          <div class="detail-section-title">📧 Email Draft</div>
          <div class="detail-email">${emailHtml}</div>
        </div>` : ''}

        <div class="detail-section">
          <div class="detail-section-title">📄 All Fields</div>
          <table class="detail-fields">
            ${fields.map(([k, v]) => `
              <tr>
                <td class="detail-fk">${k}</td>
                <td class="detail-fv">${v != null && v !== '-' ? v : '<span class="detail-null">-</span>'}</td>
              </tr>
            `).join('')}
          </table>
        </div>
      </div>
    </div>
  `;
}

function renderDeckDetail(row) {
  const fields = [
    ['Company', row.company],
    ['Status', row.status],
    ['Verdict', row.verdict],
    ['Score', row.score != null ? row.score : '-'],
    ['Timestamp', row.timestamp ? new Date(row.timestamp).toLocaleString() : '-'],
  ];

  let insightsHtml = '';
  if (row.insights) {
    const ins = typeof row.insights === 'string' ? JSON.parse(row.insights) : row.insights;
    insightsHtml = renderInsightsReport(ins);
  }

  const emailRaw = row.email_draft || '';
  const emailHtml = emailRaw.replace(/\n/g, '<br>');

  return `
    <div class="detail-modal">
      <div class="detail-header">
        <div class="detail-title">${row.company || 'Deck'} <span class="detail-id">#${row.id}</span></div>
        <button class="detail-close" onclick="closeModal()">&times;</button>
      </div>
      <div class="detail-body">

        <div class="detail-section">
          <div class="detail-section-title">📄 Overview</div>
          <table class="detail-fields">
            ${fields.map(([k, v]) => `
              <tr>
                <td class="detail-fk">${k}</td>
                <td class="detail-fv">${v != null && v !== '-' ? v : '<span class="detail-null">-</span>'}</td>
              </tr>
            `).join('')}
          </table>
        </div>

        ${emailRaw ? `
        <div class="detail-section">
          <div class="detail-section-title">📧 Email Draft</div>
          <div class="detail-email">${emailHtml}</div>
        </div>` : ''}

        ${row.summary ? `
        <div class="detail-section">
          <div class="detail-section-title">📝 Summary</div>
          <div class="detail-summary">${row.summary.replace(/\n/g, '<br>')}</div>
        </div>` : ''}

        ${insightsHtml ? `
        <div class="detail-section">
          <div class="detail-section-title">🔍 Analysis Report</div>
          <div class="detail-insights">${insightsHtml}</div>
        </div>` : ''}
      </div>
    </div>
  `;
}

function renderInsightsReport(ins) {
  const parts = [];

  if (ins.summary) {
    parts.push(`<div class="insight-block"><div class="insight-block-title">Summary</div><div class="insight-block-body">${ins.summary.replace(/\n/g, '<br>')}</div></div>`);
  }

  const structured = ins.structured_data || ins;
  if (structured.company_brief) {
    const b = structured.company_brief;
    parts.push(`
      <div class="insight-block">
        <div class="insight-block-title">Company Brief</div>
        <table class="detail-fields">
          ${[['Name', b.name], ['Tagline', b.tagline], ['One Liner', b.one_liner], ['Stage', b.stage], ['Sector', b.sector], ['Founded Year', b.founded_year], ['Headquarters', b.headquarters]]
            .filter(([,v]) => v).map(([k,v]) => `<tr><td class="detail-fk">${k}</td><td class="detail-fv">${v}</td></tr>`).join('')}
        </table>
      </div>
    `);
  }

  if (structured.problem_statement) {
    parts.push(`<div class="insight-block"><div class="insight-block-title">Problem Statement</div><div class="insight-block-body">${structured.problem_statement.replace(/\n/g, '<br>')}</div></div>`);
  }

  if (structured.solution) {
    parts.push(`<div class="insight-block"><div class="insight-block-title">Solution</div><div class="insight-block-body">${structured.solution.replace(/\n/g, '<br>')}</div></div>`);
  }

  if (structured.business_overview) {
    parts.push(`<div class="insight-block"><div class="insight-block-title">Business Overview</div><div class="insight-block-body">${structured.business_overview.replace(/\n/g, '<br>')}</div></div>`);
  }

  if (structured.industry_overview) {
    parts.push(`<div class="insight-block"><div class="insight-block-title">Industry Overview</div><div class="insight-block-body">${structured.industry_overview.replace(/\n/g, '<br>')}</div></div>`);
  }

  // Market metrics from canonical or raw
  const canonical = ins.canonical_metrics || structured._canonical;
  if (canonical && typeof canonical === 'object') {
    const entries = Object.entries(canonical).filter(([k]) => k !== '_validation_results');
    if (entries.length > 0) {
      let rows = entries.map(([k, v]) => {
        const val = v.value || v.normalized_value || v.raw_value || '-';
        const conf = v.confidence != null ? Math.round(v.confidence * 100) + '%' : '-';
        const status = v.validation_status || '-';
        const src = v.source_type || '-';
        return `<tr><td class="detail-fk">${k.replace(/_/g, ' ')}</td><td class="detail-fv">${val}</td><td class="detail-fv" style="font-size:11px;color:#94a3b8;">${conf}</td><td class="detail-fv" style="font-size:11px;">${status}</td><td class="detail-fv" style="font-size:11px;">${src}</td></tr>`;
      }).join('');
      parts.push(`
        <div class="insight-block">
          <div class="insight-block-title">Canonical Metrics</div>
          <table class="detail-fields" style="width:100%;">
            <tr style="color:#94a3b8;font-size:11px;"><td class="detail-fk">Metric</td><td class="detail-fv">Value</td><td class="detail-fv">Conf</td><td class="detail-fv">Status</td><td class="detail-fv">Source</td></tr>
            ${rows}
          </table>
        </div>
      `);
    }
  }

  // Financial highlights
  if (ins.financial_highlights || structured.financial_highlights) {
    const fh = ins.financial_highlights || structured.financial_highlights;
    const items = typeof fh === 'object' ? Object.entries(fh).map(([k,v]) => `<tr><td class="detail-fk">${k.replace(/_/g,' ')}</td><td class="detail-fv">${v}</td></tr>`).join('') : `<tr><td class="detail-fv">${fh}</td></tr>`;
    parts.push(`<div class="insight-block"><div class="insight-block-title">Financial Highlights</div><table class="detail-fields">${items}</table></div>`);
  }

  // Traction
  if (structured.traction) {
    const t = structured.traction;
    const tHtml = typeof t === 'string' ? t.replace(/\n/g, '<br>') : JSON.stringify(t);
    parts.push(`<div class="insight-block"><div class="insight-block-title">Traction</div><div class="insight-block-body">${tHtml}</div></div>`);
  }

  // Competitive landscape
  if (structured.competitive_landscape || structured.competition) {
    const cl = structured.competitive_landscape || structured.competition;
    const clHtml = typeof cl === 'string' ? cl.replace(/\n/g, '<br>') : JSON.stringify(cl);
    parts.push(`<div class="insight-block"><div class="insight-block-title">Competitive Landscape</div><div class="insight-block-body">${clHtml}</div></div>`);
  }

  // Funding
  if (structured.funding) {
    const f = structured.funding;
    const fHtml = typeof f === 'string' ? f.replace(/\n/g, '<br>') : JSON.stringify(f);
    parts.push(`<div class="insight-block"><div class="insight-block-title">Funding</div><div class="insight-block-body">${fHtml}</div></div>`);
  }

  // Strategy
  if (ins.strategy) {
    const s = ins.strategy;
    parts.push(`<div class="insight-block"><div class="insight-block-title">Strategy</div><div class="insight-block-body">${s.next_step || ''}<br>${s.reason || ''}<br>${s.verdict || ''}</div></div>`);
  }

  // Intent
  if (ins.intent) {
    const it = ins.intent;
    parts.push(`<div class="insight-block"><div class="insight-block-title">Intent</div><table class="detail-fields">
      ${[['Intent', it.intent], ['Confidence', it.confidence != null ? it.confidence + '%' : '-'], ['Signals', Array.isArray(it.signals) ? it.signals.join(', ') : it.signals]].filter(([,v]) => v).map(([k,v]) => `<tr><td class="detail-fk">${k}</td><td class="detail-fv">${v}</td></tr>`).join('')}
    </table></div>`);
  }

  // Email
  if (ins.email) {
    parts.push(`<div class="insight-block"><div class="insight-block-title">Generated Email</div><div class="detail-email">${ins.email.replace(/\n/g, '<br>')}</div></div>`);
  }

  // Validation results summary
  if (ins.validation_results || structured._validation_results) {
    const vr = ins.validation_results || structured._validation_results;
    if (Array.isArray(vr) && vr.length > 0) {
      const vrRows = vr.slice(0, 20).map(r => {
        const f = r.field || r.metric || '-';
        const s = r.status || r.severity || '-';
        const msg = r.message || r.reason || '';
        return `<tr><td class="detail-fk">${f}</td><td class="detail-fv" style="font-size:11px;">${s}</td><td class="detail-fv" style="font-size:11px;">${msg}</td></tr>`;
      }).join('');
      parts.push(`<div class="insight-block"><div class="insight-block-title">Validation Results (${vr.length})</div>
        <table class="detail-fields" style="width:100%;"><tr style="color:#94a3b8;font-size:11px;"><td class="detail-fk">Field</td><td class="detail-fv">Status</td><td class="detail-fv">Message</td></tr>${vrRows}</table>
        ${vr.length > 20 ? `<div style="color:#64748b;font-size:11px;margin-top:4px;">... and ${vr.length - 20} more</div>` : ''}
      </div>`);
    }
  }

  // Raw JSON toggle
  parts.push(`
    <details style="margin-top:12px;">
      <summary style="cursor:pointer;font-size:12px;color:#64748b;">Raw JSON</summary>
      <pre style="background:#0f172a;padding:12px;border-radius:6px;font-size:11px;overflow-x:auto;margin-top:8px;color:#94a3b8;max-height:400px;overflow-y:auto;">${JSON.stringify(ins, null, 2).replace(/</g, '&lt;')}</pre>
    </details>
  `);

  return parts.join('\n');
}

window.viewRecordDetail = viewRecordDetail;
