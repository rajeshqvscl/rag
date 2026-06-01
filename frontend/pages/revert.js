// API is defined in app.js

let currentChartType = 'bar';
let currentMetric = 'revenue';

// Pitch mode branding
function getPitchBranding() {
  const mode = localStorage.getItem('pitchMode') || 'general';
  const branding = {
    general: {
      title: 'INBOUND REVERT PROCESSOR',
      button: 'Analyze Pitch Deck',
      agentTitle: 'AGENT INTELLIGENCE',
      tagline: 'AI Intelligence Cloud'
    },
    investor: {
      title: 'DUE DILIGENCE ANALYZER',
      button: 'Launch Investment Analyst Agent',
      agentTitle: 'INVESTMENT SIGNALS',
      tagline: 'Investment Intelligence Platform'
    },
    enterprise: {
      title: 'DECISION INTELLIGENCE ENGINE',
      button: 'Launch Autonomous Due Diligence',
      agentTitle: 'ENTERPRISE INSIGHTS',
      tagline: 'Enterprise Research Brain'
    },
    technical: {
      title: 'RESEARCH INTELLIGENCE PIPELINE',
      button: 'Run Multi-Agent Analysis',
      agentTitle: 'AGENT ORCHESTRATION',
      tagline: 'Multi-Agent Intelligence Cloud'
    }
  };
  return branding[mode] || branding.general;
}

function withOpacity(color, opacity) {
    if (color.startsWith('rgba(')) {
        return color.replace(/[\d.]+\)$/, opacity + ')');
    }
    return color;
}

function loadDemoData() {
    financialData = {
        years: ['FY21', 'FY22', 'FY23', 'FY24', 'FY25', 'FY26'],
        revenue: [2.5, 4.2, 7.8, 12.5, 18.2, 25.0],
        growth: [45, 68, 86, 60, 46, 37],
        orders: [12000, 18500, 32000, 58000, 85000, 120000]
    };
    
    document.getElementById('financial-graph-card').style.display = 'block';
    document.getElementById('file-status').innerHTML = '<span style="color: #10b981;">✓ Demo data loaded</span>';
    document.getElementById('analysis-report').innerHTML = `
        <div style="color: #10b981; font-weight: 600;">✓ Demo Financial Analysis Loaded</div>
        <div style="margin-top: 10px; padding: 12px; background: #0f172a; border-radius: 6px; font-size: 12px; color: #94a3b8;">
            <strong style="color: #38bdf8;">Revenue Growth:</strong><br>
            FY21: ₹2.5Cr → FY26: ₹25Cr (10x growth)<br><br>
            <strong style="color: #38bdf8;">Key Metrics:</strong><br>
            • 6-Year CAGR: 58%<br>
            • Current Growth Rate: 37%<br>
            • Total Orders: 3.93L+
        </div>
    `;
    switchChartType(currentChartType);
    renderFinancialChart(currentMetric);
}

let pollInterval = null;
let activeJobId = null;

const FINAL_STATES = ["completed", "degraded", "failed"];

// ── Response Normalizers ───────────────────────────────────────────

function normalizeInsightsResponse(data) {
  if (!data || typeof data !== 'object') return {};
  return {
    summary: data.summary || '',
    email: data.email || '',
    key_signal: data.key_signal || 'N/A',
    score: data.score ?? null,
    confidence: data.confidence || 0,
    intent: data.intent || {},
    strategy: data.strategy || {},
    rag_status: data.rag_status || '',
    status: data.status || data.deal_status || '',
    data_warnings: Array.isArray(data.data_warnings) ? data.data_warnings : [],
    financial_highlights: data.financial_highlights || {},
    chart_data: data.chart_data || {},
    confidence_by_section: data.confidence_by_section || {},
    canonical_metrics: data.canonical_metrics || {},
    field_confidence: data.field_confidence || {},
    pipeline_health: data.pipeline_health || { rag: true, agent: true, email: true },
    _infra_confidence: data._infra_confidence,
    _degraded_stages: Array.isArray(data._degraded_stages) ? data._degraded_stages : [],
    chart_metrics: data.chart_metrics || [],
    deal_status: data.deal_status || data.status || '',
  };
}

function normalizeStatusResponse(data) {
  if (!data || typeof data !== 'object') return { status: 'unknown', id: null };
  return {
    id: data.id ?? null,
    job_id: data.job_id ?? null,
    company: data.company || '',
    status: data.status || (data.id ? 'processing' : 'failed'),
    stage: data.stage || 'processing',
    progress: data.progress ?? 0,
    elapsed_time: data.elapsed_time ?? null,
    error: data.error || data.detail || '',
    insights: data.insights ? normalizeInsightsResponse(data.insights) : null,
  };
}

// ── Canvas resize handler ───────────────────────────────────────────
window.addEventListener('resize', function() {
    // Re-render financial chart if visible
    var chartCard = document.getElementById('financial-graph-card');
    if (chartCard && chartCard.style.display !== 'none') {
        try {
            var canvas = document.getElementById('financial-chart');
            if (canvas && canvas.offsetWidth > 0) {
                renderFinancialChart(currentMetric);
            }
        } catch(e) { /* ignore resize errors */ }
    }
});

// ── Async Job Persistence ──────────────────────────────────────────
const JOB_STORAGE_KEY = 'rag_active_jobs';

function saveJobId(jobId) {
  try {
    let jobs = JSON.parse(localStorage.getItem(JOB_STORAGE_KEY) || '[]');
    const strId = String(jobId);
    if (!jobs.some(id => String(id) === strId)) {
      jobs.push(jobId);
      localStorage.setItem(JOB_STORAGE_KEY, JSON.stringify(jobs));
    }
  } catch(e) { /* ignore storage errors */ }
}

function removeJobId(jobId) {
  try {
    let jobs = JSON.parse(localStorage.getItem(JOB_STORAGE_KEY) || '[]');
    jobs = jobs.filter(id => String(id) !== String(jobId));
    localStorage.setItem(JOB_STORAGE_KEY, JSON.stringify(jobs));
  } catch(e) { /* ignore */ }
}

function getSavedJobIds() {
  try {
    return JSON.parse(localStorage.getItem(JOB_STORAGE_KEY) || '[]');
  } catch(e) { return []; }
}

// Cleanup polling interval when user navigates away (keep job alive)
window.addEventListener("beforeunload", () => {
  if (pollInterval) {
    clearInterval(pollInterval);
    pollInterval = null;
  }
});

// Reconnect to active jobs on page load
document.addEventListener("DOMContentLoaded", () => {
  const savedJobs = getSavedJobIds();
  if (savedJobs.length > 0) {
    // Check each saved job to see if it's still running
    savedJobs.forEach(jobId => {
      if (!jobId) {
        removeJobId(jobId);
        return;
      }
      fetch(API + "/status/" + jobId)
        .then(r => {
          if (!r.ok) {
            throw new Error(`HTTP error! status: ${r.status}`);
          }
          return r.json();
        })
        .then(raw => {
          const data = normalizeStatusResponse(raw);
          if (data.status === "processing") {
            if (!activeJobId) {
              startPolling(jobId);
            }
          } else if (data.status === "completed") {
            removeJobId(jobId);
          } else if (data.status === "failed") {
            removeJobId(jobId);
          }
        })
        .catch(() => removeJobId(jobId));
    });
  }
});

function loadRevert() {
  const branding = getPitchBranding();
  
  document.getElementById("content").innerHTML = `
  <div class="dashboard-grid">

    <!-- LEFT COLUMN: Input & Analysis -->
    <div style="display: flex; flex-direction: column; gap: 24px;">
      
      <!-- INBOUND PROCESSOR -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">${branding.title}</div>
          <span class="card-icon" data-lucide="cloud-upload"></span>
        </div>
        
        <div class="upload-box" onclick="document.getElementById('file-input').click()">
          <div style="border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 4px; padding: 4px; display: flex;">
            <span data-lucide="file-plus" style="color: #38bdf8; width: 20px;"></span>
          </div>
          <div class="file-count" id="file-status">No file selected</div>
          <input type="file" id="file-input" class="hidden" onchange="handleFileSelect(this)">
        </div>

        <button class="btn-process" id="process-btn" onclick="processFile()">
          ${branding.button}
        </button>
        <button class="btn-demo" onclick="loadDemoData()" style="margin-top: 8px; width: 100%; padding: 8px; background: transparent; border: 1px dashed #475569; color: #64748b; border-radius: 6px; cursor: pointer; font-size: 12px;">
          📊 Load Demo Data
        </button>
        
        <!-- Live progress visualization -->
        <div id="progress-container" style="display: none; margin-top: 15px; background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.05); padding: 12px; border-radius: 6px;">
          <div style="display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 6px;">
            <span id="progress-stage" style="color: #38bdf8; font-weight: 600;">Initializing...</span>
            <span id="progress-percent" style="color: #94a3b8;">0%</span>
          </div>
          <div style="width: 100%; height: 6px; background: rgba(255, 255, 255, 0.08); border-radius: 3px; overflow: hidden;">
            <div id="progress-bar-fill" style="width: 0%; height: 100%; background: linear-gradient(90deg, #06b6d4, #3b82f6); transition: width 0.4s ease; border-radius: 3px;"></div>
          </div>
        </div>
      </div>

      <!-- ANALYST DEEP-DIVE (SUMMARY) -->
      <div class="card" style="flex: 1;">
        <div class="card-header">
          <div class="card-title">ANALYST DEEP-DIVE</div>
          <span class="card-icon" data-lucide="file-text"></span>
        </div>
        <div class="deepdive-content" id="analysis-report">
          <span style="opacity: 0.5;">Upload a deck to generate analysis...</span>
        </div>
      </div>

      <!-- FINANCIAL GRAPH - MULTIPLE VISUALIZATIONS -->
      <div class="card" id="financial-graph-card" style="display: none;">
        <div class="card-header">
          <div class="card-title">📈 FINANCIAL VISUALIZATIONS</div>
          <span class="card-icon" data-lucide="trending-up"></span>
        </div>
        <div style="padding: 15px;">
          <!-- Visualization Type Selector -->
          <div style="display: flex; gap: 8px; margin-bottom: 15px; flex-wrap: wrap;">
            <button onclick="switchChartType('bar')" id="btn-bar" class="chart-type-btn active">📊 Bar</button>
            <button onclick="switchChartType('pie')" id="btn-pie" class="chart-type-btn">🥧 Pie</button>
          </div>
          
          <!-- Metric Toggle -->
          <div style="display: flex; gap: 8px; margin-bottom: 15px;">
            <button onclick="renderFinancialChart('revenue')" id="btn-revenue" style="padding: 6px 12px; background: #3b82f6; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 11px;">Revenue</button>
            <button onclick="renderFinancialChart('growth')" id="btn-growth" style="padding: 6px 12px; background: #1e293b; color: #94a3b8; border: 1px solid #334155; border-radius: 4px; cursor: pointer; font-size: 11px;">Growth %</button>
            <button onclick="renderFinancialChart('orders')" id="btn-orders" style="padding: 6px 12px; background: #1e293b; color: #94a3b8; border: 1px solid #334155; border-radius: 4px; cursor: pointer; font-size: 11px;">Orders</button>
          </div>
          
          <!-- Chart Canvas -->
          <canvas id="financial-chart" style="width: 100%; height: 200px; max-height: 200px;"></canvas>
          <div id="financial-legend" style="margin-top: 10px; font-size: 11px; color: #64748b; text-align: center;"></div>
        </div>
      </div>

    </div>

    <!-- RIGHT COLUMN: Agent Insights & Email -->
    <div style="display: flex; flex-direction: column; gap: 24px;">
      
      <!-- AGENT INTELLIGENCE -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">${branding.agentTitle}</div>
          <span class="card-icon" data-lucide="bot"></span>
        </div>
        <div id="agent-insights" style="display: flex; flex-direction: column; gap: 15px;">
           <div style="display: flex; justify-content: space-between; align-items: center;">
             <span style="font-size: 13px; color: #94a3b8;">INTENT</span>
             <span id="intent-badge" class="status-pill" style="opacity: 0.3;">Unknown</span>
           </div>
           <div style="display: flex; justify-content: space-between; align-items: center;">
             <span style="font-size: 13px; color: #94a3b8;">STRATEGY</span>
             <span id="strategy-text" style="font-weight: 600; font-size: 14px; color: #38bdf8;">N/A</span>
           </div>
           <div style="display: flex; justify-content: space-between; align-items: center;">
             <span style="font-size: 13px; color: #94a3b8;">SCORE</span>
             <span id="score-text" style="font-weight: 700; font-size: 18px; color: white;">0</span>
           </div>
        </div>
      </div>

      <!-- EMAIL DRAFT PORTFOLIO -->
      <div class="card" style="flex: 1;">
        <div class="card-header">
          <div class="card-title">EMAIL DRAFT PORTFOLIO</div>
          <span class="card-icon" data-lucide="mail"></span>
        </div>
        <div style="position: relative; flex: 1; display: flex; flex-direction: column;">
          <button class="copy-btn" onclick="copyEmail()">
            <span data-lucide="copy" style="width: 12px;"></span>
            Copy
          </button>
          <div id="email-draft" style="font-size: 14px; color: #e2e8f0; line-height: 1.6; white-space: pre-wrap; max-height: 400px; overflow-y: auto;">
              Draft will appear here...
          </div>
        </div>
        <button class="btn-process" style="margin-top: 20px; background: rgba(56, 189, 248, 0.1);" onclick="approveAndSend()">
          Approve & Send
        </button>
      </div>

    </div>

  </div>
  `;
  lucide.createIcons();
}

function handleFileSelect(input) {
  const statusEl = document.getElementById('file-status');
  if (!statusEl) return;
  const count = input.files.length;
  statusEl.innerText = count > 0 ? input.files[0].name : "No file selected";
}

async function processFile() {
  const fileInput = document.getElementById("file-input");
  if (!fileInput || !fileInput.files || !fileInput.files[0]) return alert("Select a PDF pitch deck first");
  const f = fileInput.files[0];

  const btn = document.getElementById("process-btn");
  if (btn) { btn.innerText = "⏳ Uploading..."; btn.disabled = true; }

  const form = new FormData();
  form.append("file", f);

  // Timeout after 180s for the upload itself (generous)
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 180000);

  try {
    const res = await fetch(API + "/process", { 
      method: "POST", 
      body: form,
      signal: controller.signal
    });
    clearTimeout(timeout);
    
    if (!res.ok) {
      const errTxt = await res.text();
      console.error("Upload failed:", errTxt);
      alert("Upload failed: " + errTxt);
      if (btn) { btn.innerText = "Analyze Pitch Deck"; btn.disabled = false; }
      return;
    }
    
    const text = await res.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch (e) {
      console.error("Invalid JSON response:", text);
      alert("Server error: " + (text.slice(0, 100) || "Invalid response"));
      if (btn) { btn.innerText = "Analyze Pitch Deck"; btn.disabled = false; }
      return;
    }
    console.log("Upload success:", data);
    
    if (data.status === "processing" && data.id) {
      saveJobId(data.id);
      activeJobId = data.id;
      if (btn) { btn.innerText = "Processing..."; }
      startPolling(data.id);
    } else if (data.summary) {
      renderAll(data);
      if (btn) { btn.innerText = "Analyze Pitch Deck"; btn.disabled = false; }
    } else {
      alert("Processing completed but no results");
      if (btn) { btn.innerText = "Analyze Pitch Deck"; btn.disabled = false; }
    }
  } catch (err) {
    console.error("Error:", err);
    if (err.name === "AbortError") {
      alert("Upload request timed out. The server may be busy — please try again. Your job will persist if already submitted.");
    } else {
      alert("Error: " + err.message);
    }
    if (btn) { btn.innerText = "Analyze Pitch Deck"; btn.disabled = false; }
  }
}

async function startPolling(insightId) {
  if (pollInterval) clearInterval(pollInterval);
  
  const progContainer = document.getElementById("progress-container");
  if (progContainer) progContainer.style.display = "block";

  // Match backend stage names from run_pipeline_background and orchestrator
  const stageNames = {
    "initializing": "Initializing",
    "pdf_parsing": "Extracting PDF",
    "text_chunking": "Chunking Text",
    "embedding": "Embedding",
    "retrieving": "Retrieving",
    "generating": "Generating Analysis",
    "scoring": "Scoring",
    "finalizing": "Finalizing",
    "completed": "Complete",
    "text_extraction": "Extracting Text",
    "domain_detection": "Detecting Domain",
    "triage": "Classifying Document",
    "chunking": "Chunking",
    "retrieval": "Retrieving Context",
    "generation": "Generating Analysis",
    "strategy": "Building Strategy",
    "processing": "Processing"
  };

  let pollAttempts = 0;
  const MAX_POLL_ATTEMPTS = 120;  // 6 minutes limit (120 attempts at 3000ms)
  let baseInterval = 3000;         // default 3s
  let warningShown = false;
  
  async function poll() {
    pollAttempts++;
    
    // ── Non-destructive time warning ──────────────────────────
    if (pollAttempts > 80 && !warningShown) {
      warningShown = true;
      showToast("Processing is taking longer than expected. Your job is still running — you can leave and come back.", "warning");
    }
    
    // ── Hard cap: give up after 120 attempts (6 minutes) ──────
    if (pollAttempts > MAX_POLL_ATTEMPTS) {
      clearInterval(pollInterval);
      pollInterval = null;
      activeJobId = null;
      removeJobId(insightId);
      if (progContainer) progContainer.style.display = "none";
      const btn = document.getElementById("process-btn");
      if (btn) { btn.innerText = "Analyze Pitch Deck"; btn.disabled = false; }
      showToast("Processing did not complete within the 6-minute limit. Please try again.", "error");
      return;
    }
    
    try {
      const res = await fetch(API + "/status/" + insightId);
      if (!res.ok) {
        console.warn("Status fetch failed:", res.status);
        if (res.status === 404) {
          clearInterval(pollInterval);
          pollInterval = null;
          activeJobId = null;
          removeJobId(insightId);
          if (progContainer) progContainer.style.display = "none";
          const btn = document.getElementById("process-btn");
          const branding = getPitchBranding();
          if (btn) { btn.innerText = branding.button; btn.disabled = false; }
          showToast("Job not found on server", "error");
        }
        return;
      }
      const raw = await res.json();
      const data = normalizeStatusResponse(raw);
      
      const btn = document.getElementById("process-btn");
      const stage = data.stage;
      const progress = data.progress;
      
      // Update visual progress bar elements
      const stageMsg = stageNames[stage] || "Processing";
      const progStage = document.getElementById("progress-stage");
      const progPercent = document.getElementById("progress-percent");
      const progBarFill = document.getElementById("progress-bar-fill");
      if (progStage) progStage.innerText = stageMsg;
      if (progPercent) progPercent.innerText = `${progress}%`;
      if (progBarFill) progBarFill.style.width = `${progress}%`;

      // Handle final states - completed, degraded, or failed
      if (FINAL_STATES.includes(data.status)) {
        clearInterval(pollInterval);
        pollInterval = null;
        activeJobId = null;
        removeJobId(insightId);
        if (progContainer) progContainer.style.display = "none";
        const branding = getPitchBranding();
        if (btn) { btn.innerText = branding.button; btn.disabled = false; }

        const hasAnyData = data.insights && (
          data.insights.summary ||
          data.insights.financial_highlights ||
          data.insights.canonical_metrics ||
          data.insights.chart_data ||
          data.insights.intent
        );

        if (data.insights) {
          renderAll(data.insights);

          const elapsed = data.elapsed_time ? ` (${data.elapsed_time}s)` : "";
          if (data.status === "degraded") {
            const degraded = data.insights._degraded_stages;
            if (degraded && degraded.length > 0) {
              showToast("Processing complete with warnings. Some metrics may be incomplete." + elapsed, "warning");
            } else {
              showToast("Processing complete (some pipeline stages degraded)." + elapsed, "warning");
            }
          } else if (data.status === "completed") {
            showToast("Processing complete!" + elapsed, "success");
          } else if (data.status === "failed") {
            showToast("Processing failed: " + (data.error || "Unknown error"), "error");
          }
        } else if (data.status === "failed") {
          showToast("Processing failed: " + (data.error || "Unknown error"), "error");
        } else if (!hasAnyData) {
          showToast("Processing complete but no results found", "warning");
        }
      } else {
        if (btn) { btn.innerText = `${stageMsg}... ${progress}%`; btn.disabled = true; }
      }
    } catch (err) {
      console.error("Poll error:", err);
      // Transient error — keep polling, don't abort
    }
  }
  
  // Initial poll immediately, then set interval
  poll();
  pollInterval = setInterval(poll, baseInterval);
}

function renderFinancialCard(h, conf) {
    const tag = (s) => {
        const c = conf?.[s] || 'none';
        return `<span class="confidence-tag ${c}">${c}</span>`;
    };
    return `
        <div class="card financials-card">
            <div class="card-header">FINANCIAL PERFORMANCE ${tag('revenue')}</div>
            <div class="card-body">
                <div class="metric-row">
                    <span class="metric-label">Revenue</span>
                    <span class="metric-value">${h?.current_revenue || 'N/A'}</span>
                </div>
                ${h?.previous_revenue ? `<div class="metric-row muted">
                    <span>Previous</span><span>${h.previous_revenue}</span>
                </div>` : ''}
                ${h?.growth_rate ? `<div class="metric-row">
                    <span>Growth</span><span class="metric-value">${h.growth_rate}</span>
                </div>` : ''}
                ${h?.customers ? `<div class="metric-row">
                    <span>Customers</span><span>${h.customers}</span>
                </div>` : ''}
                ${h?.orders ? `<div class="metric-row">
                    <span>Orders</span><span>${h.orders}</span>
                </div>` : ''}
                ${h?.gross_margin ? `<div class="metric-row">
                    <span>Margin</span><span>${h.gross_margin}</span>
                </div>` : ''}
                ${Array.isArray(h?.projections) && h.projections.length ? `<div class="projections-row">
                    <span class="metric-label">Projections</span>
                    <div style="margin-top:6px;">${h.projections.map(function(p) {
                        if (typeof p === 'string') return '<span class="projection-chip">' + p + '</span>';
                        if (typeof p === 'object' && p !== null) {
                            var val = p.display_value || p.normalized_value || p.value || JSON.stringify(p.period || '') + ' ' + JSON.stringify(p.value || '');
                            return '<span class="projection-chip">' + val + '</span>';
                        }
                        return '';
                    }).join(' ')}</div>
                </div>` : ''}
            </div>
        </div>
    `;
}

function renderMarketCard(h) {
    return `
        <div class="card market-card">
            <div class="card-header">MARKET</div>
            <div class="card-body">
                ${h?.market_tam ? `<div class="metric-row">
                    <span class="metric-label">TAM</span><span>${h.market_tam}</span>
                </div>` : ''}
                ${h?.market_sam ? `<div class="metric-row">
                    <span class="metric-label">SAM</span><span>${h.market_sam}</span>
                </div>` : ''}
                ${h?.market_som ? `<div class="metric-row">
                    <span class="metric-label">SOM</span><span>${h.market_som}</span>
                </div>` : ''}
                ${!h?.market_tam ? '<div style="color:var(--text-secondary);font-size:12px;">Market data not extracted</div>' : ''}
            </div>
        </div>
    `;
}

function renderFundingCard(h) {
    return `
        <div class="card funding-card">
            <div class="card-header">FUNDING</div>
            <div class="card-body">
                ${h?.funding_raise ? `<div class="metric-row">
                    <span class="metric-label">Raising</span>
                    <span class="metric-value">${h.funding_raise}</span>
                </div>` : ''}
                ${h?.funding_valuation ? `<div class="metric-row">
                    <span class="metric-label">Valuation</span><span>${h.funding_valuation}</span>
                </div>` : ''}
                ${h?.pipeline_value ? `<div class="metric-row">
                    <span class="metric-label">Pipeline</span><span>${h.pipeline_value}</span>
                </div>` : ''}
                ${!h?.funding_raise ? '<div style="color:var(--text-secondary);font-size:12px;">Funding data not extracted</div>' : ''}
            </div>
        </div>
    `;
}

function renderDataQualityCard(warnings) {
    if (!warnings || warnings.length === 0) return '';
    return `
        <div class="card quality-card">
            <div class="card-header">⚠ DATA QUALITY NOTES</div>
            <div class="card-body">
                ${warnings.map(w => `<div class="warning-item">• ${w}</div>`).join('')}
            </div>
        </div>
    `;
}

function renderCanonicalMetricsCard(canonical) {
    if (!canonical || Object.keys(canonical).length === 0) return '';
    const fields = {
        "total_revenue": "Revenue",
        "current_period_revenue": "Period Revenue",
        "tam": "TAM",
        "sam": "SAM",
        "som": "SOM",
        "funding_raise": "Funding Raise",
        "valuation": "Valuation",
        "orders": "Orders",
        "customers": "Customers",
        "arr_run_rate": "ARR Run Rate",
        "pipeline_value": "Pipeline",
        "purchase_order_value": "PO Value",
        "expected_booking": "Expected Booking",
        "expected_units": "Expected Units",
        "invoiced_amount": "Invoiced",
        "government_grants": "Grants",
    };
    function statusIcon(status) {
        if (status === "validated") return "🟢";
        if (status === "plausible") return "🟡";
        if (status === "uncertain") return "🟠";
        return "⚪";
    }
    function statusColor(status) {
        if (status === "validated") return "#10b981";
        if (status === "plausible") return "#facc15";
        if (status === "uncertain") return "#f97316";
        return "#64748b";
    }
    function sourceBadge(type) {
        if (type === "explicit") return '<span class="source-badge explicit">extracted</span>';
        if (type === "visual_parsed") return '<span class="source-badge visual">visual</span>';
        if (type === "inferred") return '<span class="source-badge inferred">inferred</span>';
        return '<span class="source-badge">' + (type || 'unknown') + '</span>';
    }
    var visible = [], hidden = [];
    for (var key in canonical) {
        var entry = canonical[key];
        if (!entry || !entry.value) continue;
        var display = fields[key] || entry.display_name || key.replace(/_/g, ' ').replace(/\b\w/g, function(c){return c.toUpperCase();});
        var status = entry.validation_status || "unknown";
        var conf = entry.confidence || 0;
        if (conf < 0.4) { hidden.push({key:key, entry:entry, display:display, status:status, conf:conf}); }
        else { visible.push({key:key, entry:entry, display:display, status:status, conf:conf}); }
    }
    if (visible.length === 0) return '';
    var rows = visible.map(function(m) {
        return '<div class="canonical-row">' +
            '<div class="canonical-left">' +
                '<span class="canonical-label">' + m.display + '</span>' +
                ' ' + sourceBadge(m.entry.source_type) +
            '</div>' +
            '<div class="canonical-right">' +
                '<span class="canonical-value">' + m.entry.value + '</span>' +
                '<span class="canonical-confidence" style="color:' + statusColor(m.status) + ';">' +
                    statusIcon(m.status) + ' ' + (m.conf * 100).toFixed(0) + '% ' + m.status +
                '</span>' +
            '</div>' +
        '</div>';
    }).join('');
    var hiddenRows = '';
    if (hidden.length > 0) {
        hiddenRows = '<details style="margin-top:8px;"><summary style="cursor:pointer;font-size:11px;color:#64748b;">' +
            hidden.length + ' low-confidence metric(s) hidden</summary>' +
            hidden.map(function(m) {
                return '<div class="canonical-row muted">' +
                    '<span class="canonical-label">' + m.display + '</span>' +
                    '<span class="canonical-value" style="color:#64748b;opacity:0.6;">' + m.entry.value + '</span>' +
                '</div>';
            }).join('') + '</details>';
    }
    return '<div class="card canonical-card">' +
        '<div class="card-header">📊 CANONICAL METRICS <span style="font-size:10px;color:#64748b;font-weight:400;">per-confidence tier</span></div>' +
        '<div class="card-body" style="padding:12px;">' + rows + hiddenRows + '</div>' +
    '</div>';
}

function renderAll(raw) {
    const d = normalizeInsightsResponse(raw);
    const reportDiv = document.getElementById("analysis-report");
    const health = d.pipeline_health;

    if (d.rag_status === "empty_rag" || d.rag_status === "error") {
        reportDiv.innerHTML = `
            <div style="background: rgba(239, 68, 68, 0.05); border-left: 2px solid #ef4444; padding: 16px; font-size: 13px; color: #fca5a5; margin-bottom: 15px; border-radius: 4px;">
                <div style="font-weight: 700; margin-bottom: 6px; color: #ef4444; display: flex; align-items: center; gap: 8px;">
                    <span data-lucide="alert-circle" style="width: 16px;"></span>
                    ANALYSIS GENERATION FAILED
                </div>
                <div style="opacity: 0.8; line-height: 1.5;">${d.summary || "The document structure prevented automated analysis."}</div>
            </div>
        `;
        lucide.createIcons();
        return;
    }

    const h = d.financial_highlights || {};
    const conf = d.confidence_by_section || {};
    const warnings = d.data_warnings || [];
    const canonical = d.canonical_metrics || {};
    window._lastFinancialHighlights = h;

    let html = `<div class="analyst-cards">`;
    if (warnings.length > 0) {
        html += '<div style="background: rgba(250, 204, 21, 0.05); border-left: 2px solid #facc15; padding: 8px; font-size: 11px; color: #facc15; margin-bottom: 4px; border-radius: 4px;">'
            + '⚠ Financials extracted from deck (not verified)</div>';
    }
    
    // Pipeline Health Card
    const infraConf = d._infra_confidence;
    const degradedStages = d._degraded_stages;
    if (infraConf !== undefined || (degradedStages && degradedStages.length > 0)) {
        const pct = Math.round((infraConf || 1.0) * 100);
        let healthColor = "#10b981";
        let healthLabel = "Healthy";
        if (pct < 50) { healthColor = "#ef4444"; healthLabel = "Critical"; }
        else if (pct < 70) { healthColor = "#f59e0b"; healthLabel = "Degraded"; }
        else if (pct < 90) { healthColor = "#facc15"; healthLabel = "Degraded"; }
        
        html += '<div class="card" style="border-left: 2px solid ' + healthColor + '; margin-bottom: 8px;">'
            + '<div class="card-header" style="font-size: 11px;">'
            + '<span style="color: ' + healthColor + ';">●</span> PIPELINE HEALTH: ' + healthLabel
            + ' <span style="font-size: 10px; color: #64748b;">(' + pct + '% infra confidence)</span>'
            + '</div>';
        if (degradedStages && degradedStages.length > 0) {
            html += '<div class="card-body" style="padding: 8px 12px; font-size: 11px;">'
                + degradedStages.map(function(s) {
                    return '<div style="display: flex; justify-content: space-between; padding: 2px 0; border-bottom: 1px solid rgba(255,255,255,0.04);">'
                        + '<span style="color: #f59e0b;">⚠ ' + (s.name || s.stage || 'unknown') + '</span>'
                        + '<span style="color: #94a3b8;">' + (s.status || 'degraded') + '</span>'
                        + '</div>';
                }).join('')
                + '</div>';
        }
        html += '</div>';
    }
    
    html += renderFinancialCard(h, conf);
    html += renderMarketCard(h);
    html += renderFundingCard(h);
    html += renderCanonicalMetricsCard(canonical);
    html += renderDataQualityCard(warnings);
    html += `</div>`;

    reportDiv.innerHTML = html;

    // Keep summary accessible for reference
    if (d.summary) {
        const detailDiv = document.createElement('details');
        detailDiv.style.marginTop = '12px';
        var summaryHtml = d.summary;
        try { 
            if (typeof marked !== 'undefined' && marked.parse) {
                summaryHtml = marked.parse(d.summary);
            }
        } catch(e) { 
            console.warn("Markdown parsing failed, using plain text:", e);
            summaryHtml = d.summary.replace(/\n/g, '<br>');
        }
        detailDiv.innerHTML = '<summary style="cursor:pointer;font-size:12px;color:var(--text-secondary);">Full Analysis Report</summary>'
            + '<div style="margin-top:8px;font-size:12px;line-height:1.6;color:var(--text-secondary);">' + summaryHtml + '</div>';
        reportDiv.appendChild(detailDiv);
    }

    try { lucide.createIcons(); } catch(e) { /* icon lib may not be loaded */ }
    try { extractAndRenderFinancials(d); } catch(e) { console.warn("Financial render error:", e); }
    
    // Update sidebar panels (intent, score, strategy, insights)
    const intentData = d.intent || {};
    const intent = intentData.intent || "neutral";
    const confidence = d.confidence || 0;
    const signals = intentData.signals ? intentData.signals.join(", ") : "None detected";
    
    const badge = document.getElementById("intent-badge");
    if (badge) {
        badge.innerText = intent.toUpperCase();
        badge.style.opacity = "1";
        badge.className = "status-pill " + (intent === "interested" ? "status-completed" : "status-processing");
    }
    
    const strategyData = d.strategy || {};
    const st = document.getElementById("strategy-text");
    if (st) {
        st.innerHTML = `
            <div style="font-size: 15px; margin-bottom: 4px;">${strategyData.next_step || "N/A"}</div>
            <div style="font-size: 11px; opacity: 0.6; font-weight: 400; line-height: 1.3;">Reason: ${strategyData.reason || "N/A"}</div>
        `;
    }
    
    const scoreElement = document.getElementById("score-text");
    if (scoreElement) {
        if (d.score === null || d.score === undefined) {
            scoreElement.innerText = "N/A";
            scoreElement.style.color = "#94a3b8";
            scoreElement.style.fontSize = "14px";
            scoreElement.title = "Insufficient data to compute score";
        } else {
            scoreElement.innerText = d.score;
            scoreElement.style.color = "white";
            scoreElement.style.fontSize = "18px";
        }
    }
    
    // Update agent insights
    const insightsDiv = document.getElementById("agent-insights");
    const extraInfo = document.getElementById("extra-agent-info") || document.createElement("div");
    extraInfo.id = "extra-agent-info";
    extraInfo.style.marginTop = "15px";
    extraInfo.style.paddingTop = "15px";
    extraInfo.style.borderTop = "1px solid rgba(255,255,255,0.05)";
    var ds = (d.status || d.deal_status || '').toUpperCase();
    var confPct = (confidence || 0);
    var ks = d.key_signal || 'N/A';
    var sigs = signals || 'None';
    extraInfo.innerHTML = 
        '<div style="display:flex;justify-content:space-between;margin-bottom:8px;">' +
        '<span style="font-size:11px;color:#94a3b8;">DEAL STATUS</span>' +
        '<span style="font-size:11px;color:#facc15;font-weight:700;">' + ds + '</span></div>' +
        '<div style="display:flex;justify-content:space-between;margin-bottom:8px;">' +
        '<span style="font-size:11px;color:#94a3b8;">CONFIDENCE</span>' +
        '<span style="font-size:11px;color:#e2e8f0;font-weight:600;">' + confPct + '%</span></div>' +
        '<div style="display:flex;justify-content:space-between;margin-bottom:8px;">' +
        '<span style="font-size:11px;color:#94a3b8;">KEY SIGNAL</span>' +
        '<span style="font-size:11px;color:#10b981;max-width:180px;text-align:right;">' + ks + '</span></div>' +
        '<div style="display:flex;justify-content:space-between;">' +
        '<span style="font-size:11px;color:#94a3b8;">SIGNALS</span>' +
        '<span style="font-size:11px;color:#e2e8f0;max-width:180px;text-align:right;">' + sigs + '</span></div>';
    if (insightsDiv && !document.getElementById("extra-agent-info")) {
        insightsDiv.appendChild(extraInfo);
    }
    
    // Update email draft
    const emailEl = document.getElementById("email-draft");
    if (emailEl && d.email) {
        emailEl.innerText = d.email;
    }
}

let financialData = {
    years: [],
    revenue: [],
    growth: [],
    orders: []
};

function parseRevenueToRaw(str) {
    if (!str) return 0;
    var s = String(str).replace(/[₹$,\s]/g, '');
    var num = parseFloat(s.replace(/[^0-9.]/g, ''));
    var lower = str.toLowerCase();
    if (isNaN(num)) return 0;
    if (lower.includes('bn') || lower.includes('billion')) return num * 1000000000;
    if (lower.includes('cr') || lower.includes('crore')) return num * 10000000;
    if (lower.includes('lakh') || lower.includes('lac')) return num * 100000;
    if (lower.includes('mn') || lower.includes('million')) return num * 1000000;
    if (lower.includes('k')) return num * 1000;
    return num;
}

function extractAndRenderFinancials(raw) {
    var d = normalizeInsightsResponse(raw);
    var years = [], revenue = [], growth = [], orders = [];
    var h = d.financial_highlights;
    var cd = d.chart_data;
    window._lastFinancialHighlights = h;

    // PRIMARY: structured chart_data from backend canonical registry
    // Include zero/null values for pre-revenue startups - don't filter out zeros
    if (Object.keys(cd).length > 0) {
        // Revenue - include all values including zeros (for pre-revenue startups)
        if (cd.revenue && Array.isArray(cd.revenue.data)) {
            cd.revenue.data.forEach(function(pt) {
                var v = pt.value;
                if (v !== null && v !== undefined && !isNaN(v)) {
                    revenue.push(v);
                    years.push(pt.period || pt.label || 'Current');
                }
            });
        }
        // Growth - include zeros but cap extreme outliers
        if (cd.growth && Array.isArray(cd.growth.data)) {
            cd.growth.data.forEach(function(pt) {
                var v = pt.value;
                if (v !== null && v !== undefined && !isNaN(v) && v <= 1000) growth.push(v);
            });
        }
        // Orders - include zeros
        if (cd.orders && Array.isArray(cd.orders.data)) {
            cd.orders.data.forEach(function(pt) {
                var v = pt.value;
                if (v !== null && v !== undefined && !isNaN(v)) orders.push(v);
            });
        }
        // Fallback: if no revenue but market data exists, show market as chart
        if (revenue.length === 0 && cd.market && Array.isArray(cd.market.data)) {
            cd.market.data.forEach(function(pt) {
                var v = pt.value;
                if (v !== null && v !== undefined && !isNaN(v)) revenue.push(v);
            });
            if (revenue.length > 0) years = cd.market.data.map(function(pt) { return pt.label; });
        }
    }

    // SECONDARY: financial_highlights fallback - include zero for pre-revenue
    if (revenue.length === 0 && h.current_revenue) {
        var currVal = parseRevenueToRaw(h.current_revenue);
        // Allow zero for pre-revenue startups
        if (!isNaN(currVal)) { years.push('Current'); revenue.push(currVal); }
    }

    if (growth.length === 0 && h.growth_rate) {
        var g = parseFloat(String(h.growth_rate).replace(/[^0-9.]/g, ''));
        if (!isNaN(g) && g > 0 && g < 1000) growth.push(g);
    }
    if (orders.length === 0 && h.orders) {
        var o = parseFloat(String(h.orders).replace(/[^0-9.]/g, ''));
        if (!isNaN(o) && o > 0) orders.push(o);
    }

    // TERTIARY: regex parse from summary text (existing fallback)
    if (revenue.length === 0 && d.summary) {
        var yrPat = /(FY\s*\d{2,4}|20\d{2}[-\s]?20\d{2})/gi, m;
        var yrM = d.summary.match(yrPat);
        if (yrM) yrM.slice(0,6).forEach(function(x) { years.push(x.trim().toUpperCase()); });

        var rPat = /(?:Revenue|ARR)[\s:]*₹?\s*(\d+(?:\.\d+)?)\s*(L|Lakhs?|Cr|Crores?|Million|Billion|Mn|Bn)?/gi;
        while ((m = rPat.exec(d.summary)) !== null && revenue.length < 6) {
            var v = parseFloat(m[1]), u = (m[2]||'').toLowerCase();
            if (u.startsWith('bn') || u === 'billion') v *= 1000000000;
            else if (u.startsWith('cr') || u === 'crores') v *= 10000000;
            else if (u.startsWith('l') || u === 'lakhs') v *= 100000;
            else if (u === 'mn' || u === 'million') v *= 1000000;
            if (!isNaN(v) && v > 0) revenue.push(v);
        }

        var oPat = /(?:Orders?|Bookings?)[\s:]*(\d+(?:,\d+)*(?:\+\d+)?)/gi;
        while ((m = oPat.exec(d.summary)) !== null && orders.length < 6) {
            var ov = parseFloat(m[1].replace(/,/g,'').replace(/\+/g,''));
            if (!isNaN(ov) && ov > 0) orders.push(ov);
        }

        var gPat = /(?:Growth|YoY)[\s:]*(\d+(?:\.\d+)?)\s*%/gi;
        while ((m = gPat.exec(d.summary)) !== null && growth.length < 6) {
            var gv = parseFloat(m[1]);
            if (!isNaN(gv) && gv > 0 && gv <= 200) growth.push(gv);
        }
    }

    if (years.length === 0 && revenue.length > 0) {
        var base = new Date().getFullYear();
        for (var i = revenue.length; i > 0; i--) years.push('FY' + (base - i).toString().slice(-2));
    }

    var maxLen = Math.max(years.length, revenue.length, 1);
    while (years.length < maxLen) years.push('Period');

    function cleanNum(arr) {
        return arr.filter(function(v) { return typeof v === 'number' && !isNaN(v) && isFinite(v) && v >= 0; });
    }
    financialData = {
        years: years.slice(0,6),
        revenue: cleanNum(revenue).slice(0,6),
        growth: cleanNum(growth).slice(0,6),
        orders: cleanNum(orders).slice(0,6)
    };

    var chartCard = document.getElementById('financial-graph-card');
    var revBtn = document.getElementById('btn-revenue');
    var grBtn = document.getElementById('btn-growth');
    var ordBtn = document.getElementById('btn-orders');
    if (revBtn) revBtn.style.display = revenue.length > 0 ? '' : 'none';
    if (grBtn) grBtn.style.display = growth.length > 0 ? '' : 'none';
    if (ordBtn) ordBtn.style.display = orders.length > 0 ? '' : 'none';

    if (revenue.length > 0) {
        chartCard.style.display = 'block';
        void chartCard.offsetHeight;
        renderFinancialChart('revenue');
    } else if (growth.length > 0) {
        chartCard.style.display = 'block';
        void chartCard.offsetHeight;
        renderFinancialChart('growth');
    } else if (orders.length > 0) {
        chartCard.style.display = 'block';
        void chartCard.offsetHeight;
        renderFinancialChart('orders');
    } else {
        chartCard.style.display = 'none';
    }

    // Render additional chart_data cards (market, funding) below the main chart
    renderStructuredChartDataCards(cd);
}

function renderStructuredChartDataCards(cd) {
    if (!cd || Object.keys(cd).length === 0) { return; }
    var container = document.getElementById('analysis-report');
    if (!container) return;

    // Remove any previous chart-data cards (don't duplicate)
    var existing = container.querySelectorAll('.chart-data-card');
    existing.forEach(function(el) { el.remove(); });

    var cardsHtml = '';
    Object.keys(cd).forEach(function(key) {
        var section = cd[key];
        if (!section || !Array.isArray(section.data) || section.data.length === 0) { return; }
        if (key === 'revenue') return; // revenue handled by main chart

        // KPI summary cards get a compact grid layout
        if (key === 'kpi_summary') {
            var kpiGrid = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:6px;margin-top:6px;">';
            section.data.forEach(function(pt) {
                var confBadge = pt.confidence >= 0.85 ? '<span style="color:#10b981;font-size:10px;">✓</span>'
                    : pt.confidence >= 0.65 ? '<span style="color:#f59e0b;font-size:10px;">~</span>'
                    : pt.confidence > 0 ? '<span style="color:#ef4444;font-size:10px;">!</span>'
                    : '';
                kpiGrid += '<div style="background:rgba(30,41,59,0.5);border:1px solid rgba(255,255,255,0.05);border-radius:4px;padding:6px 8px;">'
                    + '<div style="font-size:10px;color:var(--text-secondary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + (pt.label || '') + '</div>'
                    + '<div style="font-size:13px;font-weight:600;color:#e2e8f0;margin-top:2px;">' + (pt.display || pt.value || '') + ' ' + confBadge + '</div>'
                    + '</div>';
            });
            kpiGrid += '</div>';
            cardsHtml += '<div class="chart-data-card" style="background:rgba(15,23,42,0.6);border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:10px;margin-top:8px;">'
                + '<div style="font-size:11px;font-weight:700;color:var(--text-secondary);margin-bottom:2px;text-transform:uppercase;letter-spacing:0.5px;">'
                + (section.title || 'Key Metrics') + '</div>'
                + kpiGrid
                + '</div>';
            return;
        }

        var rows = section.data.map(function(pt) {
            var val = pt.display || (pt.value ? numShortFormat(pt.value) : '');
            var conf = pt.confidence ? '<span style="opacity:0.5;font-size:10px;">' + Math.round(pt.confidence*100) + '%</span>' : '';
            return '<div style="display:flex;justify-content:space-between;padding:2px 0;font-size:12px;border-bottom:1px solid rgba(255,255,255,0.04);">'
                + '<span>' + (pt.label || '') + '</span>'
                + '<span>' + val + ' ' + conf + '</span></div>';
        }).join('');

        cardsHtml += '<div class="chart-data-card" style="background:rgba(15,23,42,0.6);border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:10px;margin-top:8px;">'
            + '<div style="font-size:11px;font-weight:700;color:var(--text-secondary);margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px;">'
            + (section.title || key) + '</div>'
            + rows
            + (!section.calculated || Object.keys(section.calculated).length === 0 ? '' : renderChartCalculated(section.calculated))
            + '</div>';
    });

    if (cardsHtml) {
        container.insertAdjacentHTML('beforeend', cardsHtml);
    }
}

function renderChartCalculated(calc) {
    var items = [];
    if (calc.cagr && calc.cagr > 0) items.push('CAGR: ' + calc.cagr + '%');
    if (calc.yoy_growth && calc.yoy_growth.length > 0) items.push('YoY: ' + calc.yoy_growth[calc.yoy_growth.length-1] + '%');
    if (calc.latest_growth) items.push('Latest: ' + calc.latest_growth + '%');
    if (calc.average_growth) items.push('Avg: ' + calc.average_growth + '%');
    if (items.length === 0) return '';
    return '<div style="display:flex;gap:12px;margin-top:6px;font-size:11px;color:#8b5cf6;flex-wrap:wrap;">'
        + items.map(function(i) { return '<span>' + i + '</span>'; }).join('')
        + '</div>';
}

function numShortFormat(n) {
    if (n >= 10000000) return (n/10000000).toFixed(1) + ' Cr';
    if (n >= 100000) return (n/100000).toFixed(1) + ' Lakhs';
    if (n >= 1000) return (n/1000).toFixed(1) + ' K';
    return n.toString();
}

function switchChartType(type) {
    currentChartType = type;
    document.querySelectorAll('.chart-type-btn').forEach(btn => {
        btn.classList.remove('active');
        btn.style.background = '#1e293b';
        btn.style.color = '#94a3b8';
    });
    const activeBtn = document.getElementById('btn-' + type);
    if (activeBtn) {
        activeBtn.classList.add('active');
        activeBtn.style.background = '#8b5cf6';
        activeBtn.style.color = '#fff';
    }
    renderFinancialChart(currentMetric);
}

function renderFinancialChart(type) {
    currentMetric = type;
    
    // Check if there is ANY valid data to display
    let hasAnyData = false;
    if (typeof financialData === 'object' && financialData !== null) {
        hasAnyData = ['revenue', 'growth', 'orders'].some(key => 
            Array.isArray(financialData[key]) && financialData[key].some(v => typeof v === 'number' && v > 0)
        );
    }
    
    const card = document.getElementById('financial-graph-card');
    if (card) {
        if (!hasAnyData) {
            card.style.display = 'none';
            return;
        } else {
            card.style.display = 'block';
        }
    }
    
    const colors = {
        revenue: { fill: 'rgba(59, 130, 246, 0.3)', stroke: '#3b82f6', label: 'Revenue' },
        growth: { fill: 'rgba(16, 185, 129, 0.3)', stroke: '#10b981', label: 'Growth (%)' },
        orders: { fill: 'rgba(245, 158, 11, 0.3)', stroke: '#f59e0b', label: 'Orders' }
    };
    
    document.querySelectorAll('#btn-revenue, #btn-growth, #btn-orders').forEach(btn => {
        btn.style.background = '#1e293b';
        btn.style.color = '#94a3b8';
        btn.style.border = '1px solid #334155';
    });
    
    const activeBtn = document.getElementById('btn-' + type);
    if (activeBtn) {
        activeBtn.style.background = colors[type].stroke;
        activeBtn.style.color = '#fff';
        activeBtn.style.border = 'none';
    }
    
    switch(currentChartType) {
        case 'bar': renderBarChart(type, colors[type]); break;
        case 'pie': renderPieChart(type, colors[type]); break;
        default: renderBarChart(type, colors[type]);
    }
}

// ============ BAR CHART ============
function renderBarChart(type, color) {
    const canvas = document.getElementById('financial-chart');
    const ctx = canvas.getContext('2d');
    const data = financialData[type] || [];
    const labels = financialData.years;
    
    canvas.width = canvas.offsetWidth;
    canvas.height = 200;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    if (data.length === 0 || data.every(v => v === 0)) {
        ctx.fillStyle = '#64748b';
        ctx.font = '12px Inter';
        ctx.textAlign = 'center';
        ctx.fillText('No financial data available', canvas.width / 2, canvas.height / 2);
        return;
    }
    
    const maxVal = Math.max(...data.filter(v => v > 0), 1) * 1.2;
    const padding = 40;
    const chartWidth = canvas.width - padding * 2;
    const chartHeight = canvas.height - padding * 2;
    const barCount = data.length;
    const barSpacing = chartWidth / Math.max(barCount, 1);
    const barWidth = Math.min(barSpacing * 0.6, 50);
    
    // Grid lines
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
        const y = padding + (chartHeight / 4) * i;
        ctx.beginPath();
        ctx.moveTo(padding, y);
        ctx.lineTo(canvas.width - padding, y);
        ctx.stroke();
        
        ctx.fillStyle = '#475569';
        ctx.font = '9px Inter';
        ctx.textAlign = 'right';
        const labelVal = Math.round(maxVal * (1 - i / 4));
        ctx.fillText(formatValue(labelVal, type), padding - 5, y + 3);
    }
    
    // Bars
    data.forEach((val, i) => {
        if (val <= 0) return;
        const x = padding + i * barSpacing + (barSpacing - barWidth) / 2;
        const barHeight = (val / maxVal) * chartHeight;
        const y = canvas.height - padding - barHeight;
        const r = Math.min(barWidth * 0.15, 4);
        
        const gradient = ctx.createLinearGradient(x, y, x, canvas.height - padding);
        gradient.addColorStop(0, color.stroke);
        gradient.addColorStop(1, color.stroke + '66');
        ctx.fillStyle = gradient;
        
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.lineTo(x + barWidth - r, y);
        ctx.quadraticCurveTo(x + barWidth, y, x + barWidth, y + r);
        ctx.lineTo(x + barWidth, canvas.height - padding - r);
        ctx.quadraticCurveTo(x + barWidth, canvas.height - padding, x + barWidth - r, canvas.height - padding);
        ctx.lineTo(x + r, canvas.height - padding);
        ctx.quadraticCurveTo(x, canvas.height - padding, x, canvas.height - padding - r);
        ctx.lineTo(x, y + r);
        ctx.quadraticCurveTo(x, y, x + r, y);
        ctx.closePath();
        ctx.fill();
        
        // Value label on top
        ctx.fillStyle = '#f1f5f9';
        ctx.font = 'bold 9px Inter';
        ctx.textAlign = 'center';
        ctx.fillText(formatValue(val, type), x + barWidth / 2, y - 5);
        
        // Year label below
        if (labels[i]) {
            ctx.fillStyle = '#94a3b8';
            ctx.font = '10px Inter';
            ctx.fillText(labels[i], x + barWidth / 2, canvas.height - padding + 18);
        }
    });
    
    updateLegend(color, data);
}

// ============ PIE CHART ============
function renderPieChart(type, color) {
    const canvas = document.getElementById('financial-chart');
    const ctx = canvas.getContext('2d');
    const data = financialData[type] || [];
    const labels = financialData.years;
    
    canvas.width = canvas.offsetWidth;
    canvas.height = 200;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    if (data.length === 0 || data.every(v => v === 0)) {
        ctx.fillStyle = '#64748b';
        ctx.font = '12px Inter';
        ctx.textAlign = 'center';
        ctx.fillText('No financial data available', canvas.width / 2, canvas.height / 2);
        return;
    }
    
    const total = data.reduce((a, b) => a + b, 0);
    if (total === 0) return;
    
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    const radius = Math.min(centerX, centerY) - 40;
    
    const pieColors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'];
    let startAngle = -Math.PI / 2;
    
    const validData = data.map((val, i) => ({ val, i, label: labels[i] })).filter(d => d.val > 0);
    const legendItems = [];
    
    validData.forEach((d) => {
        const sliceAngle = (d.val / total) * Math.PI * 2;
        const endAngle = startAngle + sliceAngle;
        
        const gradient = ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, radius);
        gradient.addColorStop(0, pieColors[d.i % pieColors.length]);
        gradient.addColorStop(1, pieColors[d.i % pieColors.length] + 'cc');
        
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.arc(centerX, centerY, radius, startAngle, endAngle);
        ctx.closePath();
        ctx.fill();
        
        ctx.strokeStyle = '#0f172a';
        ctx.lineWidth = 2;
        ctx.stroke();
        
        const labelAngle = startAngle + sliceAngle / 2;
        const labelRadius = radius + 15;
        const labelX = centerX + labelRadius * Math.cos(labelAngle);
        const labelY = centerY + labelRadius * Math.sin(labelAngle);
        
        if (d.label) {
            const pct = Math.round((d.val / total) * 100);
            ctx.fillStyle = '#f1f5f9';
            ctx.font = 'bold 9px Inter';
            ctx.textAlign = labelX > centerX ? 'left' : 'right';
            ctx.fillText(`${d.label} (${pct}%)`, labelX, labelY);
            
            legendItems.push({ color: pieColors[d.i % pieColors.length], label: d.label, val: d.val, pct });
        }
        
        startAngle = endAngle;
    });
    
    const innerRadius = radius * 0.55;
    const innerGradient = ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, innerRadius);
    innerGradient.addColorStop(0, '#1e293b');
    innerGradient.addColorStop(1, '#0f172a');
    
    ctx.fillStyle = innerGradient;
    ctx.beginPath();
    ctx.arc(centerX, centerY, innerRadius, 0, Math.PI * 2);
    ctx.fill();
    
    ctx.fillStyle = '#fff';
    ctx.font = 'bold 12px Inter';
    ctx.textAlign = 'center';
    ctx.fillText('Total', centerX, centerY - 8);
    ctx.font = 'bold 16px Inter';
    ctx.fillText(formatValue(total, type), centerX, centerY + 10);
    
    document.getElementById('financial-legend').innerHTML = legendItems.map(item => 
        `<span style="color: ${item.color};">●</span> ${item.label}: ${formatValue(item.val, type)} (${item.pct}%)`
    ).join(' &nbsp;|&nbsp; ');
}

// ============ AREA CHART ============
function renderAreaChart(type, color) {
    const canvas = document.getElementById('financial-chart');
    const ctx = canvas.getContext('2d');
    const data = financialData[type] || [];
    const labels = financialData.years;
    
    canvas.width = canvas.offsetWidth;
    canvas.height = 200;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    if (data.length === 0 || data.every(v => v === 0)) {
        ctx.fillStyle = '#64748b';
        ctx.font = '12px Inter';
        ctx.textAlign = 'center';
        ctx.fillText('No financial data available', canvas.width / 2, canvas.height / 2);
        return;
    }
    
    const maxVal = Math.max(...data.filter(v => v > 0), 1) * 1.2;
    const padding = 40;
    const chartWidth = canvas.width - padding * 2;
    const chartHeight = canvas.height - padding * 2;
    
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
        const y = padding + (chartHeight / 4) * i;
        ctx.beginPath();
        ctx.moveTo(padding, y);
        ctx.lineTo(canvas.width - padding, y);
        ctx.stroke();
        
        ctx.fillStyle = '#475569';
        ctx.font = '9px Inter';
        ctx.textAlign = 'right';
        const labelVal = Math.round(maxVal * (1 - i / 4));
        ctx.fillText(type === 'revenue' ? (labelVal >= 1000 ? (labelVal/1000).toFixed(0) + 'k' : labelVal) : (type === 'growth' ? labelVal + '%' : labelVal), padding - 5, y + 3);
    }
    
    const validData = data.map((val, i) => ({ val, i })).filter(d => d.val > 0);
    
    if (validData.length > 0) {
        const areaGradient = ctx.createLinearGradient(0, padding, 0, canvas.height - padding);
        areaGradient.addColorStop(0, color.fill);
        areaGradient.addColorStop(1, withOpacity(color.fill, 0.2));
        
        ctx.fillStyle = areaGradient;
        ctx.beginPath();
        ctx.moveTo(padding, canvas.height - padding);
        
        validData.forEach((d) => {
            const x = padding + (d.i / Math.max(data.length - 1, 1)) * chartWidth;
            const y = canvas.height - padding - (d.val / maxVal) * chartHeight;
            ctx.lineTo(x, y);
        });
        
        const lastPoint = validData[validData.length - 1];
        ctx.lineTo(padding + (lastPoint.i / Math.max(data.length - 1, 1)) * chartWidth, canvas.height - padding);
        ctx.closePath();
        ctx.fill();
        
        ctx.strokeStyle = color.stroke;
        ctx.lineWidth = 2.5;
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        ctx.beginPath();
        validData.forEach((d, idx) => {
            const x = padding + (d.i / Math.max(data.length - 1, 1)) * chartWidth;
            const y = canvas.height - padding - (d.val / maxVal) * chartHeight;
            if (idx === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });
        ctx.stroke();
        
        validData.forEach((d) => {
            const x = padding + (d.i / Math.max(data.length - 1, 1)) * chartWidth;
            const y = canvas.height - padding - (d.val / maxVal) * chartHeight;
            
            if (labels[d.i]) {
                ctx.fillStyle = '#94a3b8';
                ctx.font = '10px Inter';
                ctx.textAlign = 'center';
                ctx.fillText(labels[d.i], x, canvas.height - padding + 18);
            }
            
            ctx.fillStyle = color.stroke;
            ctx.beginPath();
            ctx.arc(x, y, 4, 0, Math.PI * 2);
            ctx.fill();
            
            ctx.fillStyle = '#fff';
            ctx.beginPath();
            ctx.arc(x, y, 2, 0, Math.PI * 2);
            ctx.fill();
        });
    }
    
    updateLegend(color, data);
}

// ============ RADAR CHART ============
function renderRadarChart(type, color) {
    const canvas = document.getElementById('financial-chart');
    const ctx = canvas.getContext('2d');
    const data = financialData[type] || [];
    const labels = financialData.years;
    
    canvas.width = canvas.offsetWidth;
    canvas.height = 200;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    if (data.length === 0 || data.every(v => v === 0)) {
        ctx.fillStyle = '#64748b';
        ctx.font = '12px Inter';
        ctx.textAlign = 'center';
        ctx.fillText('No financial data available', canvas.width / 2, canvas.height / 2);
        return;
    }
    
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    const radius = Math.min(centerX, centerY) - 45;
    const maxVal = Math.max(...data.filter(v => v > 0), 1);
    const numPoints = data.filter(v => v > 0).length || 1;
    const angleStep = (Math.PI * 2) / numPoints;
    
    for (let i = 0; i < 5; i++) {
        const r = radius * (i / 4);
        ctx.strokeStyle = i === 4 ? '#475569' : '#1e293b';
        ctx.lineWidth = i === 4 ? 1.5 : 1;
        ctx.beginPath();
        for (let j = 0; j <= numPoints; j++) {
            const angle = j * angleStep - Math.PI / 2;
            const x = centerX + r * Math.cos(angle);
            const y = centerY + r * Math.sin(angle);
            if (j === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.closePath();
        ctx.stroke();
        
        if (i > 0) {
            ctx.fillStyle = '#64748b';
            ctx.font = '8px Inter';
            ctx.textAlign = 'center';
            const val = Math.round(maxVal * (i / 4));
            ctx.fillText(type === 'revenue' ? (val >= 1000 ? (val/1000).toFixed(0) + 'k' : val) : (type === 'growth' ? val + '%' : val), centerX, centerY - r + 3);
        }
    }
    
    const validData = data.map((v, i) => ({ val: v, label: labels[i] })).filter(d => d.val > 0);
    
    const gradient = ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, radius);
    gradient.addColorStop(0, color.fill);
    gradient.addColorStop(1, withOpacity(color.fill, 0.4));
    
    ctx.strokeStyle = color.stroke;
    ctx.lineWidth = 2.5;
    ctx.fillStyle = gradient;
    ctx.beginPath();
    validData.forEach((d, i) => {
        const angle = i * angleStep - Math.PI / 2;
        const r = (d.val / maxVal) * radius;
        const x = centerX + r * Math.cos(angle);
        const y = centerY + r * Math.sin(angle);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
    
    validData.forEach((d, i) => {
        const angle = i * angleStep - Math.PI / 2;
        const r = (d.val / maxVal) * radius;
        const x = centerX + r * Math.cos(angle);
        const y = centerY + r * Math.sin(angle);
        
        ctx.fillStyle = '#0f172a';
        ctx.beginPath();
        ctx.arc(x, y, 7, 0, Math.PI * 2);
        ctx.fill();
        
        ctx.fillStyle = color.stroke;
        ctx.beginPath();
        ctx.arc(x, y, 5, 0, Math.PI * 2);
        ctx.fill();
        
        ctx.fillStyle = '#fff';
        ctx.beginPath();
        ctx.arc(x, y, 2, 0, Math.PI * 2);
        ctx.fill();
        
        if (d.label) {
            const labelRadius = radius + 12;
            const labelX = centerX + labelRadius * Math.cos(angle);
            const labelY = centerY + labelRadius * Math.sin(angle);
            ctx.fillStyle = '#f1f5f9';
            ctx.font = 'bold 9px Inter';
            ctx.textAlign = labelX > centerX ? 'left' : 'right';
            ctx.fillText(d.label + ': ' + formatValue(d.val, type), labelX, labelY);
        }
    });
    
    updateLegend(color, validData.map(d => d.val));
}

// ============ FUNNEL CHART ============
function renderFunnelChart(type, color) {
    const canvas = document.getElementById('financial-chart');
    const ctx = canvas.getContext('2d');
    const data = financialData[type] || [];
    const labels = financialData.years;
    
    canvas.width = canvas.offsetWidth;
    canvas.height = 200;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    if (data.length === 0 || data.every(v => v === 0)) {
        ctx.fillStyle = '#64748b';
        ctx.font = '12px Inter';
        ctx.textAlign = 'center';
        ctx.fillText('No financial data available', canvas.width / 2, canvas.height / 2);
        return;
    }
    
    const maxVal = Math.max(...data.filter(v => v > 0), 1);
    const validData = data.map((v, i) => ({ val: v, label: labels[i] })).filter(d => d.val > 0);
    const padding = 20;
    const funnelWidth = canvas.width - padding * 2;
    const stageHeight = (canvas.height - padding * 2) / Math.min(validData.length, 6);
    
    const funnelColors = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#06b6d4', '#ef4444'];
    
    validData.slice(0, 6).forEach((d, i) => {
        const widthRatio = d.val / maxVal;
        const topWidth = funnelWidth * (1 - i / validData.length) * 0.8 + funnelWidth * 0.2;
        const bottomWidth = funnelWidth * (1 - (i + 1) / validData.length) * 0.8 + funnelWidth * 0.2;
        const y = padding + i * stageHeight;
        
        const gradient = ctx.createLinearGradient(canvas.width/2 - topWidth/2, y, canvas.width/2 + topWidth/2, y);
        gradient.addColorStop(0, funnelColors[i % funnelColors.length]);
        gradient.addColorStop(0.5, funnelColors[i % funnelColors.length] + 'dd');
        gradient.addColorStop(1, funnelColors[i % funnelColors.length]);
        
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.moveTo(canvas.width / 2 - topWidth / 2, y);
        ctx.lineTo(canvas.width / 2 + topWidth / 2, y);
        ctx.lineTo(canvas.width / 2 + bottomWidth / 2, y + stageHeight * 0.9);
        ctx.lineTo(canvas.width / 2 - bottomWidth / 2, y + stageHeight * 0.9);
        ctx.closePath();
        ctx.fill();
        
        ctx.strokeStyle = '#0f172a';
        ctx.lineWidth = 1;
        ctx.stroke();
        
        ctx.fillStyle = '#fff';
        ctx.font = 'bold 10px Inter';
        ctx.textAlign = 'center';
        ctx.fillText(d.label || `Stage ${i + 1}`, canvas.width / 2, y + stageHeight * 0.35);
        
        ctx.font = 'bold 12px Inter';
        ctx.fillText(formatValue(d.val, type), canvas.width / 2, y + stageHeight * 0.65);
        
        if (i > 0) {
            const prevVal = validData[i-1].val;
            const pctChange = prevVal > 0 ? Math.round(((d.val - prevVal) / prevVal) * 100) : 0;
            if (pctChange !== 0) {
                ctx.fillStyle = pctChange >= 0 ? '#10b981' : '#ef4444';
                ctx.font = '8px Inter';
                ctx.fillText((pctChange > 0 ? '↑' : '↓') + Math.abs(pctChange) + '%', canvas.width / 2, y + stageHeight * 0.85);
            }
        }
    });
    
    const legendHtml = validData.map((d, i) => 
        `<span style="color: ${funnelColors[i % funnelColors.length]};">●</span> ${d.label}: ${formatValue(d.val, type)}`
    ).join(' &nbsp;|&nbsp; ');
    document.getElementById('financial-legend').innerHTML = legendHtml;
}

// ============ KPI CARDS ============
function renderKPICards(type, color) {
    const canvas = document.getElementById('financial-chart');
    const ctx = canvas.getContext('2d');
    const data = financialData[type] || [];
    const labels = financialData.years;
    
    canvas.width = canvas.offsetWidth;
    canvas.height = 200;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    if (data.length === 0 || data.every(v => v === 0)) {
        ctx.fillStyle = '#64748b';
        ctx.font = '12px Inter';
        ctx.textAlign = 'center';
        ctx.fillText('No financial data available', canvas.width / 2, canvas.height / 2);
        return;
    }
    
    const maxVal = Math.max(...data.filter(v => v > 0), 1);
    const validData = data.map((v, i) => ({ val: v, label: labels[i] })).filter(d => d.val > 0);
    const numCards = Math.min(validData.length, 4);
    const cardWidth = (canvas.width - 20) / numCards;
    const cardHeight = canvas.height - 20;
    
    const cardGradient = ctx.createLinearGradient(0, 10, 0, cardHeight + 10);
    cardGradient.addColorStop(0, '#1e293b');
    cardGradient.addColorStop(1, '#0f172a');
    
    validData.slice(0, 4).forEach((d, i) => {
        const x = 10 + i * cardWidth;
        
        ctx.fillStyle = cardGradient;
        ctx.beginPath();
        ctx.roundRect(x, 10, cardWidth - 15, cardHeight - 15, 10);
        ctx.fill();
        
        ctx.strokeStyle = color.stroke + '40';
        ctx.lineWidth = 1;
        ctx.stroke();
        
        if (d.label) {
            ctx.fillStyle = '#64748b';
            ctx.font = 'bold 9px Inter';
            ctx.textAlign = 'center';
            ctx.fillText(d.label.toUpperCase(), x + (cardWidth - 15) / 2, 28);
        }
        
        ctx.fillStyle = '#f8fafc';
        ctx.font = 'bold 16px Inter';
        ctx.textAlign = 'center';
        ctx.fillText(formatValue(d.val, type), x + (cardWidth - 15) / 2, 52);
        
        const sparklineWidth = cardWidth - 40;
        const sparklineHeight = 50;
        const sparkY = 75;
        
        const sparkGradient = ctx.createLinearGradient(0, sparkY, 0, sparkY + sparklineHeight);
        sparkGradient.addColorStop(0, withOpacity(color.fill, 0.8));
        sparkGradient.addColorStop(1, withOpacity(color.fill, 0.1));
        
        ctx.fillStyle = sparkGradient;
        ctx.beginPath();
        ctx.moveTo(x + 20, sparkY + sparklineHeight);
        validData.slice(0, i + 1).forEach((sd, si) => {
            const sx = x + 20 + (si / Math.max(validData.length - 1, 1)) * sparklineWidth;
            const sy = sparkY + sparklineHeight - (sd.val / maxVal) * sparklineHeight;
            ctx.lineTo(sx, sy);
        });
        const lastX = x + 20 + (i / Math.max(validData.length - 1, 1)) * sparklineWidth;
        ctx.lineTo(lastX, sparkY + sparklineHeight);
        ctx.closePath();
        ctx.fill();
        
        ctx.strokeStyle = color.stroke;
        ctx.lineWidth = 2;
        ctx.lineCap = 'round';
        ctx.beginPath();
        validData.slice(0, i + 1).forEach((sd, si) => {
            const sx = x + 20 + (si / Math.max(validData.length - 1, 1)) * sparklineWidth;
            const sy = sparkY + sparklineHeight - (sd.val / maxVal) * sparklineHeight;
            if (si === 0) ctx.moveTo(sx, sy);
            else ctx.lineTo(sx, sy);
        });
        ctx.stroke();
        
        if (i > 0) {
            const change = ((d.val - validData[i-1].val) / validData[i-1].val) * 100;
            const isUp = change >= 0;
            ctx.fillStyle = isUp ? '#10b981' : '#ef4444';
            ctx.font = 'bold 9px Inter';
            ctx.textAlign = 'center';
            ctx.fillText((isUp ? '↑' : '↓') + Math.abs(change.toFixed(0)) + '%', x + (cardWidth - 15) / 2, cardHeight - 20);
        }
    });
    
    document.getElementById('financial-legend').innerHTML = `<span style="color: ${color.stroke};">●</span> KPI Summary - ${validData.length} periods | Max: ${formatValue(maxVal, type)}`;
}

function formatValue(val, type) {
    var num = parseFloat(val);
    if (isNaN(num)) return String(val);
    if (type === 'revenue') {
        if (num >= 10000000) return (num / 10000000).toFixed(1) + 'Cr';
        else if (num >= 100000) return (num / 100000).toFixed(1) + 'L';
        else return num.toFixed(0);
    } else if (type === 'growth') {
        return num.toFixed(0) + '%';
    } else {
        if (num >= 1000) return (num / 1000).toFixed(1) + 'k';
        else return num.toFixed(0);
    }
}

function updateLegend(color, data) {
    var validData = data.filter(function(v) { return v > 0; }).length;
    var h = window._lastFinancialHighlights || {};
    var extra = '';
    var label = color.label || '';
    if (label.indexOf('Revenue') !== -1 && h.current_revenue) {
        extra = ' | ' + h.current_revenue;
    } else if (label.indexOf('Order') !== -1 && h.orders) {
        extra = ' | ' + h.orders;
    }
    document.getElementById('financial-legend').innerHTML = validData > 0
        ? '<span style="color:' + color.stroke + ';">\u25cf</span> ' + label + extra
        : '<span style="color:#ef4444;">\u26a0\ufe0f No numeric data found</span>';
}

async function approveAndSend() {
  const body = document.getElementById("email-draft").innerText;
  if (body.includes("Draft will appear here")) return alert("Analyze a deck first");

  try {
    const res = await fetch(API + "/send-email", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        to: "investor@example.com",
        subject: "Re: Investment Discussion",
        body: body
      })
    });
    alert("Email Sent Successfully");
  } catch (e) {
    alert("Send Failed");
  }
}

// Canvas resize handler
var _resizeTimer;
window.addEventListener('resize', function() {
  clearTimeout(_resizeTimer);
  _resizeTimer = setTimeout(function() {
    if (window._lastFinancialHighlights && currentMetric) {
      renderFinancialChart(currentMetric);
    }
  }, 300);
});