const API_URL = "http://127.0.0.1:9000"; // Local FastAPI backend

// ============ AUTHENTICATION ============

// Check authentication on page load
function checkAuthentication() {
    const token = localStorage.getItem('access_token');
    if (!token) {
        // Not logged in - redirect to login
        window.location.href = 'login.html';
        return false;
    }
    
    // Update UI with user info
    updateUserUI();
    return true;
}

// Get auth headers for API calls
function getAuthHeaders() {
    const token = localStorage.getItem('access_token');
    return {
        'Authorization': `Bearer ${token}`,
        'X-API-KEY': 'finrag_at_2026'
    };
}

// Update UI with current user info
function updateUserUI() {
    const userStr = localStorage.getItem('user');
    if (userStr) {
        const user = JSON.parse(userStr);
        
        // Update avatar in header
        const avatarImg = document.querySelector('.header img');
        if (avatarImg && user.full_name) {
            avatarImg.src = `https://ui-avatars.com/api/?name=${encodeURIComponent(user.full_name)}&background=6366f1&color=fff`;
            avatarImg.title = user.full_name;
        }
        
        // Update user name in dropdown
        const userNameEl = document.getElementById('user-name');
        if (userNameEl && user.full_name) {
            userNameEl.textContent = user.full_name;
        }
        
        // Update user email in dropdown
        const userEmailEl = document.getElementById('user-email');
        if (userEmailEl && user.email) {
            userEmailEl.textContent = user.email;
        }
    }
}

// Toggle user dropdown menu
function toggleUserMenu() {
    const dropdown = document.getElementById('user-dropdown');
    if (dropdown) {
        dropdown.style.display = dropdown.style.display === 'none' ? 'block' : 'none';
    }
}

// Close user menu when clicking outside
document.addEventListener('click', (e) => {
    const userMenu = document.querySelector('.user-menu');
    const dropdown = document.getElementById('user-dropdown');
    if (userMenu && dropdown && !userMenu.contains(e.target)) {
        dropdown.style.display = 'none';
    }
});

// Logout function
function logout() {
    // Clear all auth data
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('token_type');
    localStorage.removeItem('user');
    
    // Redirect to login
    window.location.href = 'login.html';
}

// Refresh token if needed
async function refreshToken() {
    const refresh_token = localStorage.getItem('refresh_token');
    if (!refresh_token) {
        logout();
        return false;
    }
    
    try {
        const response = await fetch(`${API_URL}/auth/refresh`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ refresh_token })
        });
        
        if (response.ok) {
            const data = await response.json();
            localStorage.setItem('access_token', data.access_token);
            localStorage.setItem('refresh_token', data.refresh_token);
            return true;
        } else {
            logout();
            return false;
        }
    } catch (error) {
        console.error('Token refresh failed:', error);
        logout();
        return false;
    }
}

// Initialize auth on page load
document.addEventListener('DOMContentLoaded', () => {
    checkAuthentication();
});

// ============ UI STATE MANAGEMENT ============

function showSection(section) {
    const sections = ['analysis-section', 'drafts-section', 'library-section', 'integrations-section', 'settings-section'];
    sections.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = 'none';
    });
    
    document.querySelectorAll('.nav-item').forEach(btn => btn.classList.remove('active'));
    
    const activeSection = document.getElementById(`${section}-section`);
    if (activeSection) activeSection.style.display = 'block';
    
    // Find link and make active - updated to match HTML order
    const navItems = {
        'analysis': 0, 'drafts': 1, 'library': 2, 'integrations': 3, 'settings': 4
    };
    const targetIdx = navItems[section];
    if (targetIdx !== undefined) {
        document.querySelectorAll('.nav-item')[targetIdx].classList.add('active');
    }

    // Load section-specific data
    if (section === 'library') loadLibrary();
    if (section === 'drafts') loadDrafts();
}

// File Upload Logic
const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('file-input');
const processBtn = document.getElementById('process-btn');

dropzone.onclick = () => fileInput.click();

fileInput.onchange = (e) => {
    const files = e.target.files;
    dropzone.querySelector('p').innerText = `${files.length} file(s) selected`;
};

processBtn.onclick = async () => {
    const files = fileInput.files;

    if (files.length === 0) {
        alert("Please select at least one file to process.");
        return;
    }

    // Auto-derive company name from filename
    const company = files[0].name.split('.')[0].replace(/[-_]/g, ' ');

    processBtn.disabled = true;
    processBtn.innerText = "Processing deal flow...";
    
    const formData = new FormData();
    formData.append('company', company);
    for (let file of files) {
        formData.append('files', file);
    }

    try {
        const targetUrl = `${API_URL}/email-webhook`;
        console.log(`🚀 Dispatching Analysis to: ${targetUrl}`);
        const response = await fetch(targetUrl, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: formData
        });

        const text = await response.text();
        let data;
        try {
            data = JSON.parse(text);
        } catch (parseError) {
            console.error("Malformed Response:", text);
            throw new Error(`Server returned invalid JSON: ${text.substring(0, 50)}...`);
        }

        if (data.status === "error") {
            alert(`Analysis Error: ${data.message}`);
        } else {
            renderAnalysis(data);
        }
    } catch (err) {
        console.error(err);
        alert(`Processing failed: ${err.message}`);
    } finally {
        processBtn.disabled = false;
        processBtn.innerText = "Analyse Data & Generate Drafts";
    }
};
function renderAnalysis(data) {
    const analysisBox = document.getElementById('analysis-markdown');
    const emailBox = document.getElementById('email-draft');
    
    // Parse analysis - handle both string and JSON formats
    let analysisContent = data.analysis || '';
    
    // If analysis contains JSON, try to parse it
    if (analysisContent.startsWith('{') || analysisContent.startsWith('```json')) {
        try {
            // Remove markdown code blocks if present
            const cleanJson = analysisContent.replace(/```json/g, '').replace(/```/g, '').trim();
            const parsed = JSON.parse(cleanJson);
            if (parsed.analysis_markdown) {
                analysisContent = parsed.analysis_markdown;
            }
        } catch (e) {
            console.log('Could not parse JSON from analysis, using as-is');
        }
    }
    
    // Simple markdown to HTML conversion
    let htmlContent = analysisContent
        .replace(/^### (.*$)/gim, '<h3>$1</h3>')
        .replace(/^## (.*$)/gim, '<h2>$1</h2>')
        .replace(/^# (.*$)/gim, '<h1>$1</h1>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/^- (.*$)/gim, '<li>$1</li>')
        .replace(/\n/g, '<br>');
    
    analysisBox.innerHTML = `<h3>Report Summary</h3><div class="analysis-content">${htmlContent}</div>`;
    emailBox.innerText = data.draft_email;
    
    // Update Chart
    if (data.revenue_data && data.revenue_data.length > 0) {
        const labels = data.revenue_data.map(r => r.year);
        const revenues = data.revenue_data.map(r => r.revenue);
        updateRevenueChart(labels, revenues);

        const snapshot = document.getElementById('deal-snapshot');
        snapshot.innerHTML = `
            <div style="margin-top:1rem;">
                <p><strong>Revenue Trajectory:</strong></p>
                <h3 style="color:var(--accent-success)">$${(revenues[revenues.length-1]/1000000).toFixed(1)}M</h3>
                <p style="font-size:0.8rem; color:var(--text-muted);">Projected by ${labels[labels.length-1]}</p>
            </div>
        `;
    }
}

// Global Search (RAG)
const searchInput = document.getElementById('global-search');
searchInput.onkeypress = async (e) => {
    if (e.key === 'Enter') {
        const query = searchInput.value;
        const symMatch = query.match(/\$([A-Z]+)/);
        const symbol = symMatch ? symMatch[1] : "";
        
        searchInput.disabled = true;
        
        try {
            const response = await fetch(`${API_URL}/query?q=${encodeURIComponent(query)}&symbol=${symbol}`, {
                headers: { 'X-API-KEY': 'finrag_at_2026' }
            });
            const data = await response.json();
            renderIntel(data);
            showSection('intel');
        } catch (err) {
            console.error(err);
        } finally {
            searchInput.disabled = false;
        }
    }
};

function renderIntel(data) {
    const resultsContainer = document.getElementById('search-results');
    
    let html = `
        <div style="background: rgba(99, 102, 241, 0.1); padding:1.5rem; border-radius:12px; margin-bottom:2rem; border-left:4px solid var(--primary);">
            <h3 style="color:var(--primary); margin-bottom:0.5rem;">AI Insight</h3>
            <p>${data.analysis}</p>
        </div>
    `;

    if (data.projections && data.projections.length > 0) {
        html += `<h4>Financial Memory Found</h4><div style="display:flex; gap:1rem; margin:1rem 0;">`;
        data.projections.forEach(p => {
            html += `<div class="card" style="padding:1rem; border:1px solid #333;">
                <div style="font-size:0.8rem; color:var(--text-muted);">${p.period}</div>
                <div style="font-weight:bold; color:var(--primary);">${p.value}</div>
                <div style="font-size:0.75rem;">${p.metric}</div>
            </div>`;
        });
        html += `</div>`;
    }

    html += `<h4>Corpus Search Results</h4><div style="margin-top:1rem;">`;
    data.results.forEach(res => {
        html += `
            <div style="margin-bottom:1.5rem; border-bottom:1px solid #222; padding-bottom:1rem;">
                <div style="color:var(--secondary); font-size:0.8rem; font-weight:bold;">Source: ${res.type}</div>
                <div style="font-size:0.9rem; color:var(--text-muted);">${res.text.substring(0, 300)}...</div>
            </div>
        `;
    });
    html += `</div>`;
    
    resultsContainer.innerHTML = html;
}

// Chart Initializers
let revenueChart;
function updateRevenueChart(labels, data) {
    const ctx = document.getElementById('revenueChart').getContext('2d');
    if (revenueChart) revenueChart.destroy();
    
    revenueChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'ARR Projection ($)',
                data: data,
                borderColor: '#6366f1',
                backgroundColor: 'rgba(99, 102, 241, 0.1)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: { grid: { color: '#222' }, ticks: { color: '#94a3b8' } },
                x: { grid: { color: '#222' }, ticks: { color: '#94a3b8' } }
            },
            plugins: { legend: { display: false } }
        }
    });
}

// Market Ingest Logic
async function ingestMarketData() {
    const ticker = document.getElementById('ingest-ticker').value;
    const status = document.getElementById('ingest-status');
    if (!ticker) return;

    status.innerText = "⏳ Ingesting SEC Edgar & Yahoo Data...";
    
    try {
        const response = await fetch(`${API_URL}/fin/ingest?symbol=${ticker}`, {
            headers: { 'X-API-KEY': 'finrag_at_2026' }
        });
        const data = await response.json();
        if (data.status === "success") {
            status.innerText = `✅ ${data.message}`;
        } else {
            status.innerText = `❌ ${data.message}`;
        }
    } catch (err) {
        status.innerText = "❌ Ingest failed.";
    }
}


// Library Management
async function loadLibrary() {
    const tbody = document.getElementById('library-tbody');
    
    try {
        const response = await fetch(`${API_URL}/library`, {
            headers: getAuthHeaders()
        });
        const data = await response.json();
        
        if (data.status === 'success' && data.library.length > 0) {
            tbody.innerHTML = data.library.map(entry => `
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                    <td style="padding: 1rem;">
                        <div><strong>${entry.company}</strong></div>
                        <div style="font-size: 0.8rem; color: var(--text-muted);">${entry.file_name || 'Unknown file'}</div>
                    </td>
                    <td>${entry.date_uploaded || entry.date_processed || 'Unknown date'}</td>
                    <td>
                        <span class="badge badge-success">${entry.confidence}</span>
                        ${entry.file_size ? `<div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 0.2rem;">${formatFileSize(entry.file_size)}</div>` : ''}
                    </td>
                    <td>
                        <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                            ${entry.file_path ? `
                                <button class="nav-item" style="padding: 5px 10px; font-size: 0.7rem; background: var(--primary);" onclick="downloadLibraryFile('${entry.file_name}', '${entry.file_path}')">Download</button>
                            ` : ''}
                            <button class="nav-item" style="padding: 5px 10px; font-size: 0.7rem; background: #222;" onclick="alert('File: ${entry.file_name}')">Details</button>
                        </div>
                    </td>
                </tr>
            `).join('');
        } else {
            tbody.innerHTML = '<tr><td colspan="4" style="padding: 2rem; text-align: center; color: var(--text-muted);">No pitch deck PDFs in library yet. Upload and analyze pitch decks to see them here.</td></tr>';
        }
    } catch (err) {
        console.error('Failed to load library:', err);
        tbody.innerHTML = '<tr><td colspan="4" style="padding: 2rem; text-align: center; color: #ef4444;">Failed to load library</td></tr>';
    }
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function downloadLibraryFile(fileName, filePath) {
    // Create download link for the file
    const link = document.createElement('a');
    // Extract relative path from full path
    const relativePath = filePath.replace(/^.*[\\\/]/, '');
    link.href = `/static/data/library_files/${relativePath}`;
    link.download = fileName;
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}


// Drafts Management - BULLETPROOF VERSION
async function loadDrafts() {
    console.log('=== loadDrafts() START ===');
    const draftsList = document.getElementById('drafts-list');
    
    if (!draftsList) {
        console.error('ERROR: drafts-list element not found in DOM!');
        alert('Error: Drafts container not found. Please refresh the page.');
        return;
    }
    
    // Show loading state
    draftsList.innerHTML = '<div style="padding: 2rem; text-align: center; color: var(--text-muted);">Loading drafts...</div>';
    
    try {
        const response = await fetch(API_URL + '/drafts', {
            headers: getAuthHeaders()
        });
        
        if (!response.ok) {
            throw new Error('HTTP ' + response.status);
        }
        
        const text = await response.text();
        console.log('Raw response:', text.substring(0, 500));
        
        let data;
        try {
            data = JSON.parse(text);
        } catch (e) {
            throw new Error('Invalid JSON: ' + e.message);
        }
        
        console.log('Parsed data:', data);
        console.log('data.status:', data.status);
        console.log('data.drafts exists:', !!data.drafts);
        console.log('data.drafts length:', data.drafts ? data.drafts.length : 'N/A');
        
        // FORCE CHECK - use loose equality and explicit length check
        const hasStatus = data.status == 'success';
        const hasDrafts = data.drafts && Array.isArray(data.drafts) && data.drafts.length > 0;
        
        console.log('hasStatus:', hasStatus);
        console.log('hasDrafts:', hasDrafts);
        
        if (hasStatus && hasDrafts) {
            console.log('Rendering ' + data.drafts.length + ' drafts');
            
            let html = '';
            for (let i = 0; i < data.drafts.length; i++) {
                const draft = data.drafts[i];
                
                // Safe value extraction
                const company = (draft.company || 'Unknown Company').toString();
                const date = (draft.date || 'No date').toString();
                const status = (draft.status || 'Draft').toString();
                const confidence = (draft.confidence || 'N/A').toString();
                const analysis = draft.analysis ? draft.analysis.toString().substring(0, 300) : 'No analysis available';
                const draftId = draft.id || 0;
                
                // Escape for safe HTML attribute usage (use HTML entities)
                const safeCompany = company.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
                const safeAnalysis = (draft.analysis || '').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                const safeEmail = (draft.email_draft || '').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                
                // Build card HTML with data attributes
                html += '<div style="background: rgba(255,255,255,0.05); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; margin-bottom: 1rem;">';
                html += '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">';
                html += '<strong>' + company + '</strong>';
                html += '<span style="font-size: 0.8rem; color: var(--text-muted);">' + date + '</span>';
                html += '</div>';
                html += '<div style="display: flex; gap: 1rem; margin-bottom: 0.5rem;">';
                html += '<span class="badge badge-success">' + status + '</span>';
                html += '<span class="badge badge-info">' + confidence + '</span>';
                html += '</div>';
                html += '<div style="margin-bottom: 1rem;">';
                html += '<strong>Analysis Preview:</strong>';
                html += '<div style="background: rgba(0,0,0,0.2); padding: 0.5rem; border-radius: 4px; margin-top: 0.5rem; font-size: 0.9rem; max-height: 150px; overflow-y: auto;">';
                html += analysis + '...';
                html += '</div></div>';
                html += '<div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">';
                html += '<button class="nav-item view-analysis-btn" style="padding: 5px 10px; font-size: 0.7rem; background: var(--secondary);" data-company="' + safeCompany + '" data-analysis="' + safeAnalysis + '">View Full Analysis</button>';
                html += '<button class="nav-item view-email-btn" style="padding: 5px 10px; font-size: 0.7rem; background: var(--primary);" data-company="' + safeCompany + '" data-email="' + safeEmail + '">View Email Draft</button>';
                html += '<button class="nav-item" style="padding: 5px 10px; font-size: 0.7rem; background: #dc2626;" onclick="deleteDraft(' + draftId + ')">Delete</button>';
                html += '</div></div>';
            }
            
            draftsList.innerHTML = html;
            console.log('Successfully rendered ' + data.drafts.length + ' drafts');
            
            // Attach event listeners to buttons
            draftsList.querySelectorAll('.view-analysis-btn').forEach(btn => {
                btn.addEventListener('click', function() {
                    viewDraftAnalysis(this.dataset.company, this.dataset.analysis);
                });
            });
            draftsList.querySelectorAll('.view-email-btn').forEach(btn => {
                btn.addEventListener('click', function() {
                    viewDraftEmail(this.dataset.company, this.dataset.email);
                });
            });
            
        } else {
            console.log('CONDITION FAILED - hasStatus:' + hasStatus + ', hasDrafts:' + hasDrafts);
            draftsList.innerHTML = '<div style="padding: 2rem; text-align: center; color: var(--text-muted);">No drafts yet. Analyze pitch decks in the Revert Analysis tab to create drafts.</div>';
        }
        
    } catch (err) {
        console.error('CRITICAL ERROR:', err);
        draftsList.innerHTML = '<div style="padding: 2rem; text-align: center; color: #ef4444;">Error loading drafts: ' + err.message + '</div>';
    }
    
    console.log('=== loadDrafts() END ===');
}

// Helper to decode HTML entities
function decodeHtmlEntities(text) {
    if (!text) return '';
    const textarea = document.createElement('textarea');
    textarea.innerHTML = text;
    return textarea.value;
}

function viewDraftAnalysis(company, analysis) {
    // Decode HTML entities for display
    const decodedCompany = decodeHtmlEntities(company);
    const decodedAnalysis = decodeHtmlEntities(analysis);
    
    // Create modal to show full analysis
    const modal = document.createElement('div');
    modal.style.cssText = `
        position: fixed; top: 0; left: 0; width: 100%; height: 100%;
        background: rgba(0,0,0,0.8); display: flex; align-items: center; justify-content: center;
        z-index: 1000;
    `;
    modal.innerHTML = `
        <div style="background: var(--bg); padding: 2rem; border-radius: 8px; max-width: 800px; max-height: 80vh; overflow-y: auto;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                <h2>Analysis: ${decodedCompany}</h2>
                <button onclick="this.parentElement.parentElement.parentElement.remove()" style="background: var(--danger); color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer;">Close</button>
            </div>
            <div style="white-space: pre-wrap; font-family: monospace; font-size: 0.9rem; line-height: 1.4;">${decodedAnalysis}</div>
        </div>
    `;
    document.body.appendChild(modal);
}

function viewDraftEmail(company, emailDraft) {
    // Decode HTML entities for display
    const decodedCompany = decodeHtmlEntities(company);
    const decodedEmail = decodeHtmlEntities(emailDraft);
    
    // Create modal to show email draft
    const modal = document.createElement('div');
    modal.style.cssText = `
        position: fixed; top: 0; left: 0; width: 100%; height: 100%;
        background: rgba(0,0,0,0.8); display: flex; align-items: center; justify-content: center;
        z-index: 1000;
    `;
    modal.innerHTML = `
        <div style="background: var(--bg); padding: 2rem; border-radius: 8px; max-width: 800px; max-height: 80vh; overflow-y: auto;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                <h2>Email Draft: ${decodedCompany}</h2>
                <button onclick="this.parentElement.parentElement.parentElement.remove()" style="background: var(--danger); color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer;">Close</button>
            </div>
            <div style="white-space: pre-wrap; font-family: monospace; font-size: 0.9rem; line-height: 1.4;">${decodedEmail}</div>
            <div style="margin-top: 1rem;">
                <button onclick="copyToClipboard(this.dataset.email)" data-email="${decodedEmail.replace(/"/g, '&quot;')}" style="background: var(--primary); color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer;">Copy to Clipboard</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        alert('Email draft copied to clipboard!');
    }).catch(err => {
        console.error('Failed to copy:', err);
    });
}

// Memory Management
async function loadMemory() {
    try {
        // Load conversations
        const convResponse = await fetch(`${API_URL}/memory/conversations`, {
            headers: { 'X-API-KEY': 'finrag_at_2026' }
        });
        const convData = await convResponse.json();
        
        // Load stats
        const statsResponse = await fetch(`${API_URL}/memory/stats`, {
            headers: { 'X-API-KEY': 'finrag_at_2026' }
        });
        const statsData = await statsResponse.json();
        
        // Display conversations
        const convDiv = document.getElementById('memory-conversations');
        if (convData.status === 'success' && convData.conversations.length > 0) {
            convDiv.innerHTML = convData.conversations.map(conv => `
                <div style="background: rgba(255,255,255,0.05); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; margin-bottom: 1rem;">
                    <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.5rem;">${new Date(conv.timestamp).toLocaleString()}</div>
                    <div style="margin-bottom: 0.5rem;">
                        <strong>Query:</strong> ${conv.query}
                    </div>
                    <div>
                        <strong>Response:</strong> ${conv.response}
                    </div>
                </div>
            `).join('');
        } else {
            convDiv.innerHTML = '<div style="padding: 2rem; text-align: center; color: var(--text-muted);">No conversations in memory yet.</div>';
        }
        
        // Display stats
        const statsDiv = document.getElementById('memory-stats');
        if (statsData.status === 'success') {
            statsDiv.innerHTML = `
                <div class="card">
                    <h5>Total Conversations</h5>
                    <div style="font-size: 2rem; font-weight: bold;">${statsData.total_conversations}</div>
                </div>
                <div class="card">
                    <h5>Total Vectors</h5>
                    <div style="font-size: 2rem; font-weight: bold;">${statsData.total_vectors}</div>
                </div>
            `;
        }
    } catch (err) {
        console.error('Failed to load memory:', err);
    }
}

async function searchMemory() {
    const query = document.getElementById('memory-search').value;
    if (!query) return;
    
    try {
        const response = await fetch(`${API_URL}/memory/search?query=${encodeURIComponent(query)}`, {
            headers: { 'X-API-KEY': 'finrag_at_2026' }
        });
        const data = await response.json();
        
        if (data.status === 'success' && data.results.length > 0) {
            const convDiv = document.getElementById('memory-conversations');
            convDiv.innerHTML = `
                <div style="background: rgba(255,255,255,0.1); border: 1px solid var(--primary); border-radius: 8px; padding: 1rem; margin-bottom: 1rem;">
                    <h4>Search Results for "${query}"</h4>
                    ${data.results.map(result => `
                        <div style="background: rgba(255,255,255,0.05); border-radius: 8px; padding: 1rem; margin-top: 0.5rem;">
                            <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.5rem;">
                                Distance: ${result.distance.toFixed(4)} | ${new Date(result.conversation.timestamp).toLocaleString()}
                            </div>
                            <div style="margin-bottom: 0.5rem;">
                                <strong>Query:</strong> ${result.conversation.query}
                            </div>
                            <div>
                                <strong>Response:</strong> ${result.conversation.response}
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;
        } else {
            alert('No results found for your search query.');
        }
    } catch (err) {
        console.error('Search failed:', err);
        alert('Search failed. Please try again.');
    }
}

async function addMemory() {
    const query = document.getElementById('memory-query').value;
    const response = document.getElementById('memory-response').value;
    
    if (!query || !response) {
        alert('Please enter both query and response.');
        return;
    }
    
    try {
        const res = await fetch(`${API_URL}/memory/conversations`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-API-KEY': 'finrag_at_2026'
            },
            body: JSON.stringify({
                query: query,
                response: response,
                context: ''
            })
        });
        
        if (res.ok) {
            // Clear form
            document.getElementById('memory-query').value = '';
            document.getElementById('memory-response').value = '';
            
            // Reload memory
            loadMemory();
            alert('Conversation added to memory!');
        } else {
            alert('Failed to add conversation to memory.');
        }
    } catch (err) {
        console.error('Add memory failed:', err);
        alert('Failed to add conversation to memory.');
    }
}

async function deleteDraft(draftId) {
    if (!confirm('Are you sure you want to delete this draft?')) return;
    
    try {
        const response = await fetch(`${API_URL}/drafts/${draftId}`, {
            method: 'DELETE',
            headers: { 'X-API-KEY': 'finrag_at_2026' }
        });
        
        if (response.ok) {
            loadDrafts();
        } else {
            alert('Failed to delete draft');
        }
    } catch (err) {
        console.error('Failed to delete draft:', err);
        alert('Failed to delete draft');
    }
}

// Dashboard Analytics
async function loadDashboard() {
    try {
        // Load dashboard analytics
        const analyticsResponse = await fetch(`${API_URL}/analytics/dashboard`, {
            headers: { 'X-API-KEY': 'finrag_at_2026' }
        });
        const analyticsData = await analyticsResponse.json();
        
        // Load performance metrics
        const performanceResponse = await fetch(`${API_URL}/analytics/performance`, {
            headers: { 'X-API-KEY': 'finrag_at_2026' }
        });
        const performanceData = await performanceResponse.json();
        
        if (analyticsData.status === 'success') {
            // Update summary cards
            document.getElementById('dashboard-total-drafts').textContent = analyticsData.summary.total_drafts;
            document.getElementById('dashboard-recent-drafts').textContent = analyticsData.summary.recent_drafts;
            document.getElementById('dashboard-total-library').textContent = analyticsData.summary.total_library;
            document.getElementById('dashboard-recent-library').textContent = analyticsData.summary.recent_library;
            document.getElementById('dashboard-total-conversations').textContent = analyticsData.summary.total_conversations;
            document.getElementById('dashboard-recent-conversations').textContent = analyticsData.summary.recent_conversations;
            document.getElementById('dashboard-total-memories').textContent = analyticsData.summary.total_memories;
            
            // Update top companies
            const topCompaniesDiv = document.getElementById('top-companies');
            if (analyticsData.top_companies.length > 0) {
                topCompaniesDiv.innerHTML = analyticsData.top_companies.map(company => `
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.5rem; border-bottom: 1px solid var(--border);">
                        <span>${company.company}</span>
                        <span class="badge badge-info">${company.count}</span>
                    </div>
                `).join('');
            } else {
                topCompaniesDiv.innerHTML = '<div style="padding: 1rem; text-align: center; color: var(--text-muted);">No data available</div>';
            }
            
            // Draw activity timeline chart
            drawActivityChart(analyticsData.activity_timeline);
            
            // Draw confidence distribution chart
            drawConfidenceChart(analyticsData.confidence_distribution);
        }
        
        if (performanceData.status === 'success') {
            // Update performance stats
            const performanceDiv = document.getElementById('performance-stats');
            performanceDiv.innerHTML = `
                <div class="card">
                    <h5>Database</h5>
                    <div style="font-size: 1.2rem; font-weight: bold;">${performanceData.database.drafts + performanceData.database.library + performanceData.database.conversations}</div>
                    <div style="color: var(--text-muted); font-size: 0.8rem;">Total records</div>
                </div>
                <div class="card">
                    <h5>Storage</h5>
                    <div style="font-size: 1.2rem; font-weight: bold;">${performanceData.storage.total_size_mb} MB</div>
                    <div style="color: var(--text-muted); font-size: 0.8rem;">${performanceData.storage.total_files} files</div>
                </div>
                <div class="card">
                    <h5>Hourly Activity</h5>
                    <div style="font-size: 1.2rem; font-weight: bold;">${performanceData.activity.hourly_drafts + performanceData.activity.hourly_conversations}</div>
                    <div style="color: var(--text-muted); font-size: 0.8rem;">Last hour</div>
                </div>
                <div class="card">
                    <h5>Daily Activity</h5>
                    <div style="font-size: 1.2rem; font-weight: bold;">${performanceData.activity.daily_drafts + performanceData.activity.daily_conversations}</div>
                    <div style="color: var(--text-muted); font-size: 0.8rem;">Last 24h</div>
                </div>
            `;
        }
    } catch (err) {
        console.error('Failed to load dashboard:', err);
    }
}

function drawActivityChart(activityData) {
    const ctx = document.getElementById('activity-chart').getContext('2d');
    
    const labels = activityData.map(item => {
        const date = new Date(item.date);
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    });
    
    const draftsData = activityData.map(item => item.drafts);
    const conversationsData = activityData.map(item => item.conversations);
    const libraryData = activityData.map(item => item.library);
    
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Drafts',
                    data: draftsData,
                    borderColor: '#6366f1',
                    backgroundColor: 'rgba(99, 102, 241, 0.1)',
                    tension: 0.4
                },
                {
                    label: 'Conversations',
                    data: conversationsData,
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    tension: 0.4
                },
                {
                    label: 'Library Files',
                    data: libraryData,
                    borderColor: '#f59e0b',
                    backgroundColor: 'rgba(245, 158, 11, 0.1)',
                    tension: 0.4
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#94a3b8' }
                }
            },
            scales: {
                x: {
                    ticks: { color: '#94a3b8' },
                    grid: { color: 'rgba(255,255,255,0.1)' }
                },
                y: {
                    ticks: { color: '#94a3b8' },
                    grid: { color: 'rgba(255,255,255,0.1)' }
                }
            }
        }
    });
}

function drawConfidenceChart(confidenceData) {
    const ctx = document.getElementById('confidence-chart').getContext('2d');
    
    const labels = confidenceData.map(item => item.confidence);
    const data = confidenceData.map(item => item.count);
    
    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: ['#6366f1', '#10b981', '#f59e0b', '#ef4444'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#94a3b8' }
                }
            }
        }
    });
}


// Compliance Management
async function loadCompliance() {
    try {
        const response = await fetch(`${API_URL}/compliance/esg`, {
            headers: { 'X-API-KEY': 'finrag_at_2026' }
        });
        const data = await response.json();
        
        if (data.status === 'success') {
            const esg = data.esg_report;
            // Update compliance display
            const complianceSection = document.getElementById('compliance-section');
            if (complianceSection) {
                const cards = complianceSection.querySelectorAll('.card > div');
                cards.forEach(card => {
                    if (card.innerHTML.includes('Carbon Footprint')) {
                        card.innerHTML = `<strong>Carbon Footprint Impact:</strong> ${esg.carbon_footprint.impact} (Tier ${esg.carbon_footprint.tier})`;
                    }
                    if (card.innerHTML.includes('Mandate Check')) {
                        const statusColor = esg.mandate_check.status === 'warning' ? 'var(--accent-warning)' : 'var(--accent-success)';
                        const borderColor = esg.mandate_check.status === 'warning' ? 'var(--accent-warning)' : 'var(--accent-success)';
                        card.style.borderLeftColor = borderColor;
                        card.innerHTML = `<strong>Mandate Check:</strong> ${esg.mandate_check.status} - ${esg.mandate_check.issues.join(', ')}`;
                    }
                });
            }
        }
    } catch (err) {
        console.error('Failed to load compliance data:', err);
    }
}

// Integrations Management
async function loadIntegrations() {
    try {
        const response = await fetch(`${API_URL}/integrations`, {
            headers: { 'X-API-KEY': 'finrag_at_2026' }
        });
        const data = await response.json();
        
        if (data.status === 'success') {
            const integrations = data.integrations;
            
            // Update each integration card
            Object.keys(integrations).forEach(name => {
                const card = document.querySelector(`.integration-card[data-integration="${name}"]`);
                if (card) {
                    const status = integrations[name].status;
                    const badge = card.querySelector('.integration-status .badge');
                    const connectBtn = card.querySelector('.connect-btn');
                    const disconnectBtn = card.querySelector('.disconnect-btn');
                    
                    if (status === 'connected') {
                        badge.textContent = 'Connected';
                        badge.className = 'badge badge-success';
                        badge.style.background = 'var(--success)';
                        connectBtn.style.display = 'none';
                        disconnectBtn.style.display = 'flex';
                        
                        // Add or show settings button
                        let settingsBtn = card.querySelector('.settings-btn');
                        if (!settingsBtn) {
                            settingsBtn = document.createElement('button');
                            settingsBtn.className = 'nav-item settings-btn';
                            settingsBtn.style.cssText = 'width: 100%; justify-content: center; background: var(--secondary); color: white; border: none; margin-top: 0.5rem;';
                            settingsBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 0.5rem;"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg> Settings';
                            settingsBtn.onclick = () => showIntegrationSettings(name);
                            card.appendChild(settingsBtn);
                        }
                        settingsBtn.style.display = 'flex';
                    } else {
                        badge.textContent = 'Disconnected';
                        badge.className = 'badge badge-risk';
                        badge.style.background = 'transparent';
                        connectBtn.style.display = 'flex';
                        disconnectBtn.style.display = 'none';
                        
                        // Hide settings button
                        const settingsBtn = card.querySelector('.settings-btn');
                        if (settingsBtn) {
                            settingsBtn.style.display = 'none';
                        }
                    }
                }
            });
        }
    } catch (err) {
        console.error('Failed to load integrations:', err);
    }
}

// Integration connection configs
const INTEGRATION_CONFIGS = {
    hubspot: {
        name: 'HubSpot',
        fields: [
            { id: 'api_key', label: 'HubSpot API Key', type: 'password', placeholder: 'Enter your HubSpot API key' },
            { id: 'portal_id', label: 'Portal ID', type: 'text', placeholder: 'Your HubSpot Portal ID' }
        ],
        oauth: true,
        oauthUrl: 'https://app.hubspot.com/oauth/authorize'
    },
    salesforce: {
        name: 'Salesforce',
        fields: [
            { id: 'username', label: 'Username', type: 'text', placeholder: 'your@email.com' },
            { id: 'password', label: 'Password', type: 'password', placeholder: 'Password' },
            { id: 'security_token', label: 'Security Token', type: 'password', placeholder: 'Optional' }
        ],
        oauth: true,
        oauthUrl: 'https://login.salesforce.com/services/oauth2/authorize'
    },
    slack: {
        name: 'Slack',
        fields: [
            { id: 'webhook_url', label: 'Webhook URL', type: 'text', placeholder: 'https://hooks.slack.com/services/...' }
        ],
        oauth: true,
        oauthUrl: 'https://slack.com/oauth/v2/authorize'
    },
    gmail: {
        name: 'Gmail',
        fields: [
            { id: 'email', label: 'Email Address', type: 'email', placeholder: 'your@gmail.com' },
            { id: 'app_password', label: 'App Password', type: 'password', placeholder: '16-character app password' }
        ],
        oauth: true,
        oauthUrl: 'https://accounts.google.com/o/oauth2/v2/auth'
    },
    github: {
        name: 'GitHub',
        fields: [
            { id: 'token', label: 'Personal Access Token', type: 'password', placeholder: 'ghp_xxxxxxxxxxxx' }
        ],
        oauth: true,
        oauthUrl: 'https://github.com/login/oauth/authorize'
    }
};

function showConnectModal(integration) {
    const config = INTEGRATION_CONFIGS[integration];
    if (!config) return;
    
    const modal = document.getElementById('connect-modal');
    const title = document.getElementById('connect-modal-title');
    const content = document.getElementById('connect-modal-content');
    
    title.textContent = 'Connect ' + config.name;
    
    let html = '';
    
    html += '<div style="margin-bottom: 1.5rem;">';
    html += '<p style="color: var(--text-muted); margin-bottom: 1rem;">Choose your connection method:</p>';
    html += '<button onclick="connectViaOAuth(\'' + integration + '\')" class="nav-item" style="width: 100%; justify-content: center; background: var(--primary); color: white; border: none; margin-bottom: 1rem;">';
    html += '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 0.5rem;"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>';
    html += 'Connect with OAuth (Recommended)';
    html += '</button>';
    html += '</div>';
    
    html += '<div style="display: flex; align-items: center; margin-bottom: 1.5rem;">';
    html += '<div style="flex: 1; height: 1px; background: var(--border);"></div>';
    html += '<span style="padding: 0 1rem; color: var(--text-muted); font-size: 0.8rem;">or use API credentials</span>';
    html += '<div style="flex: 1; height: 1px; background: var(--border);"></div>';
    html += '</div>';
    
    html += '<form onsubmit="connectViaApi(event, \'' + integration + '\')">';
    config.fields.forEach(field => {
        html += '<div style="margin-bottom: 1rem;">';
        html += '<label style="display: block; font-size: 0.8rem; margin-bottom: 0.5rem; color: var(--text-muted);">' + field.label + '</label>';
        html += '<input type="' + field.type + '" id="conn-' + field.id + '" placeholder="' + field.placeholder + '" required style="width: 100%; background: #111; border: 1px solid var(--border); padding: 0.8rem; border-radius: 8px; color: white;">';
        html += '</div>';
    });
    html += '<button type="submit" class="nav-item" style="width: 100%; justify-content: center; background: var(--secondary); color: white; border: none; margin-top: 1rem;">Connect with API</button>';
    html += '</form>';
    
    content.innerHTML = html;
    modal.style.display = 'flex';
}

function closeConnectModal() {
    const modal = document.getElementById('connect-modal');
    modal.style.display = 'none';
}

async function connectViaOAuth(integration) {
    alert('OAuth flow for ' + integration + ' would open in a new window.\n\nIn production, this redirects to the OAuth provider.');
    closeConnectModal();
}

async function connectViaApi(event, integration) {
    event.preventDefault();
    
    const config = INTEGRATION_CONFIGS[integration];
    const credentials = {};
    config.fields.forEach(field => {
        credentials[field.id] = document.getElementById('conn-' + field.id).value;
    });
    
    // Show loading
    const submitBtn = event.target.querySelector('button[type="submit"]');
    const originalText = submitBtn.textContent;
    submitBtn.textContent = 'Connecting...';
    submitBtn.disabled = true;
    
    try {
        const response = await fetch(API_URL + '/integrations/' + integration + '/connect', {
            method: 'POST',
            headers: { 
                'X-API-KEY': 'finrag_at_2026',
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ credentials: credentials })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            alert(config.name + ' connected successfully!');
            closeConnectModal();
            loadIntegrations();
        } else {
            alert('Connection failed: ' + (data.message || 'Unknown error'));
        }
    } catch (err) {
        alert('Connection error: ' + err.message);
    } finally {
        submitBtn.textContent = originalText;
        submitBtn.disabled = false;
    }
}

// Full OAuth flow handler with themed sign-in pages
async function connectViaOAuth(integration) {
    const config = INTEGRATION_CONFIGS[integration];
    
    try {
        const redirectUri = window.location.origin + '/oauth-callback.html';
        const response = await fetch(API_URL + '/integrations/' + integration + '/oauth/initiate?redirect_uri=' + encodeURIComponent(redirectUri), {
            headers: { 'X-API-KEY': 'finrag_at_2026' }
        });
        
        const data = await response.json();
        
        if (data.status === 'success' && data.oauth_url) {
            // Store state for callback verification
            localStorage.setItem('oauth_state', data.state);
            localStorage.setItem('oauth_integration', integration);
            
            // Calculate popup position (center of screen)
            const width = 500;
            const height = 700;
            const left = (screen.width - width) / 2;
            const top = (screen.height - height) / 2;
            
            // Open OAuth popup to the themed sign-in page
            const popup = window.open(
                data.oauth_url,
                'oauth_' + integration,
                'width=' + width + ',height=' + height + ',left=' + left + ',top=' + top + ',toolbar=no,menubar=no,scrollbars=yes'
            );
            
            if (!popup) {
                alert('Popup blocked! Please allow popups for this site.');
                return;
            }
            
            // Listen for message from popup
            const messageHandler = async (event) => {
                if (event.data && event.data.type === 'oauth-success') {
                    window.removeEventListener('message', messageHandler);
                    
                    // Close popup if still open
                    if (popup && !popup.closed) {
                        popup.close();
                    }
                    
                    alert(config.name + ' connected successfully via OAuth!');
                    closeConnectModal();
                    loadIntegrations();
                    
                    // Check token status
                    checkOAuthStatus(integration);
                } else if (event.data && event.data.type === 'oauth-error') {
                    window.removeEventListener('message', messageHandler);
                    
                    if (popup && !popup.closed) {
                        popup.close();
                    }
                    
                    alert('OAuth failed: ' + (event.data.error || 'Unknown error'));
                }
            };
            
            window.addEventListener('message', messageHandler);
            
            // Also poll for popup closure
            const pollInterval = setInterval(() => {
                if (popup.closed) {
                    clearInterval(pollInterval);
                    window.removeEventListener('message', messageHandler);
                    
                    // Check if actually connected
                    setTimeout(() => loadIntegrations(), 500);
                }
            }, 500);
        }
    } catch (err) {
        alert('OAuth initiation failed: ' + err.message);
    }
}

// Check OAuth token status
async function checkOAuthStatus(integration) {
    try {
        const response = await fetch(API_URL + '/integrations/' + integration + '/oauth/status', {
            headers: { 'X-API-KEY': 'finrag_at_2026' }
        });
        
        const data = await response.json();
        
        if (data.auth_type === 'oauth') {
            console.log('OAuth status for ' + integration + ':', data);
            
            if (data.is_expired && data.refresh_token_available) {
                console.log('Token expired, auto-refreshing...');
                await refreshOAuthToken(integration);
            } else if (data.is_expired) {
                alert('Your ' + integration + ' connection has expired. Please reconnect.');
            }
        }
    } catch (err) {
        console.error('Failed to check OAuth status:', err);
    }
}

// Refresh OAuth token
async function refreshOAuthToken(integration) {
    try {
        const response = await fetch(API_URL + '/integrations/' + integration + '/oauth/refresh', {
            method: 'POST',
            headers: { 'X-API-KEY': 'finrag_at_2026' }
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            console.log('Token refreshed for ' + integration);
            return true;
        } else {
            console.error('Token refresh failed:', data.message);
            return false;
        }
    } catch (err) {
        console.error('Token refresh error:', err);
        return false;
    }
}

async function disconnectIntegration(integration) {
    const config = INTEGRATION_CONFIGS[integration];
    if (!confirm('Are you sure you want to disconnect ' + (config?.name || integration) + '?')) {
        return;
    }
    
    try {
        const response = await fetch(API_URL + '/integrations/' + integration + '/disconnect', {
            method: 'POST',
            headers: { 'X-API-KEY': 'finrag_at_2026' }
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            loadIntegrations();
        } else {
            alert('Disconnect failed: ' + (data.message || 'Unknown error'));
        }
    } catch (err) {
        alert('Disconnect error: ' + err.message);
    }
}

// Test integration connection
async function testIntegrationConnection(integration) {
    try {
        const response = await fetch(API_URL + '/integrations/' + integration + '/test', {
            headers: { 'X-API-KEY': 'finrag_at_2026' }
        });
        
        const data = await response.json();
        
        if (data.connected) {
            alert('Connection test successful! ' + data.message);
        } else {
            alert('Connection test failed: ' + data.message);
        }
    } catch (err) {
        alert('Test error: ' + err.message);
    }
}

// Trigger manual sync
async function syncIntegration(integration) {
    try {
        const response = await fetch(API_URL + '/integrations/' + integration + '/sync', {
            method: 'POST',
            headers: { 'X-API-KEY': 'finrag_at_2026' }
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            alert('Sync triggered! Last sync: ' + data.last_sync);
            loadIntegrations();
        } else {
            alert('Sync failed: ' + data.message);
        }
    } catch (err) {
        alert('Sync error: ' + err.message);
    }
}

// Show integration settings modal
async function showIntegrationSettings(integration) {
    const config = INTEGRATION_CONFIGS[integration];
    
    try {
        // Load both settings and OAuth status in parallel
        const [settingsResp, oauthResp] = await Promise.all([
            fetch(API_URL + '/integrations/' + integration + '/settings', {
                headers: { 'X-API-KEY': 'finrag_at_2026' }
            }),
            fetch(API_URL + '/integrations/' + integration + '/oauth/status', {
                headers: { 'X-API-KEY': 'finrag_at_2026' }
            }).catch(() => ({ json: () => ({}) })) // OAuth status might fail for API-key integrations
        ]);
        
        const settingsData = await settingsResp.json();
        const oauthData = await oauthResp.json();
        
        const currentSettings = settingsData.settings || {};
        const syncEnabled = settingsData.sync_enabled || false;
        const isOAuth = oauthData.auth_type === 'oauth';
        
        const modal = document.getElementById('connect-modal');
        const title = document.getElementById('connect-modal-title');
        const content = document.getElementById('connect-modal-content');
        
        title.textContent = config.name + ' Settings';
        
        let html = '<form onsubmit="saveIntegrationSettings(event, \'' + integration + '\')">';
        
        // OAuth Status Section
        if (isOAuth && oauthData.status === 'success') {
            const isExpired = oauthData.is_expired;
            const expiresIn = oauthData.expires_in;
            const hoursLeft = Math.floor(expiresIn / 3600);
            const minutesLeft = Math.floor((expiresIn % 3600) / 60);
            
            html += '<div style="margin-bottom: 1.5rem; padding: 1rem; background: rgba(255,255,255,0.05); border-radius: 8px; border-left: 4px solid ' + (isExpired ? '#ef4444' : '#10b981') + ';">';
            html += '<div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;">';
            html += '<span style="font-weight: 600;">OAuth Status</span>';
            html += '<span style="font-size: 0.8rem; padding: 0.25rem 0.5rem; border-radius: 4px; background: ' + (isExpired ? '#ef4444' : '#10b981') + ';">' + (isExpired ? 'EXPIRED' : 'ACTIVE') + '</span>';
            html += '</div>';
            
            if (!isExpired) {
                html += '<p style="font-size: 0.8rem; color: var(--text-muted);">Token expires in ' + hoursLeft + 'h ' + minutesLeft + 'm</p>';
            } else if (oauthData.refresh_token_available) {
                html += '<p style="font-size: 0.8rem; color: #ef4444; margin-bottom: 0.5rem;">Token has expired but can be refreshed.</p>';
                html += '<button type="button" onclick="refreshOAuthToken(\'' + integration + '\').then(() => { alert(\'Token refreshed!\'); showIntegrationSettings(\'' + integration + '\'); })" class="nav-item" style="width: 100%; justify-content: center; background: var(--warning); color: white; border: none; font-size: 0.8rem;">Refresh Token</button>';
            }
            
            html += '<div style="margin-top: 0.5rem; font-size: 0.75rem; color: var(--text-muted);">';
            html += '<div>Scope: ' + (oauthData.scope || 'N/A') + '</div>';
            html += '</div>';
            html += '</div>';
        } else if (settingsData.credentials_configured) {
            html += '<div style="margin-bottom: 1.5rem; padding: 1rem; background: rgba(255,255,255,0.05); border-radius: 8px; border-left: 4px solid #6366f1;">';
            html += '<div style="display: flex; align-items: center; justify-content: space-between;">';
            html += '<span style="font-weight: 600;">Auth Type</span>';
            html += '<span style="font-size: 0.8rem; padding: 0.25rem 0.5rem; border-radius: 4px; background: #6366f1;">API KEY</span>';
            html += '</div>';
            html += '<p style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.5rem;">Connected using API credentials</p>';
            html += '</div>';
        }
        
        // Sync toggle
        html += '<div style="margin-bottom: 1.5rem; padding: 1rem; background: rgba(255,255,255,0.05); border-radius: 8px;">';
        html += '<label style="display: flex; align-items: center; cursor: pointer;">';
        html += '<input type="checkbox" id="setting-sync-enabled" ' + (syncEnabled ? 'checked' : '') + ' style="margin-right: 0.5rem;">';
        html += '<span>Enable automatic sync</span>';
        html += '</label>';
        html += '<p style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.5rem; margin-left: 1.5rem;">Automatically sync data with ' + config.name + '</p>';
        html += '</div>';
        
        // Integration-specific settings
        if (integration === 'slack') {
            html += '<div style="margin-bottom: 1rem;">';
            html += '<label style="display: block; font-size: 0.8rem; margin-bottom: 0.5rem; color: var(--text-muted);">Default Channel</label>';
            html += '<input type="text" id="setting-channel" value="' + (currentSettings.default_channel || '#general') + '" placeholder="#general" style="width: 100%; background: #111; border: 1px solid var(--border); padding: 0.8rem; border-radius: 8px; color: white;">';
            html += '</div>';
        } else if (integration === 'hubspot' || integration === 'salesforce') {
            html += '<div style="margin-bottom: 1rem;">';
            html += '<label style="display: block; font-size: 0.8rem; margin-bottom: 0.5rem; color: var(--text-muted);">Sync Direction</label>';
            html += '<select id="setting-sync-direction" style="width: 100%; background: #111; border: 1px solid var(--border); padding: 0.8rem; border-radius: 8px; color: white;">';
            html += '<option value="bidirectional" ' + (currentSettings.sync_direction === 'bidirectional' ? 'selected' : '') + '>Bidirectional</option>';
            html += '<option value="to_crm" ' + (currentSettings.sync_direction === 'to_crm' ? 'selected' : '') + '>To CRM only</option>';
            html += '<option value="from_crm" ' + (currentSettings.sync_direction === 'from_crm' ? 'selected' : '') + '>From CRM only</option>';
            html += '</select>';
            html += '</div>';
        } else if (integration === 'gmail') {
            html += '<div style="margin-bottom: 1rem;">';
            html += '<label style="display: block; font-size: 0.8rem; margin-bottom: 0.5rem; color: var(--text-muted);">Default Signature</label>';
            html += '<textarea id="setting-signature" placeholder="Your email signature..." style="width: 100%; background: #111; border: 1px solid var(--border); padding: 0.8rem; border-radius: 8px; color: white; height: 80px;">' + (currentSettings.signature || '') + '</textarea>';
            html += '</div>';
        }
        
        html += '<div style="display: flex; gap: 0.5rem; margin-top: 1.5rem;">';
        html += '<button type="button" onclick="testIntegrationConnection(\'' + integration + '\')" class="nav-item" style="flex: 1; justify-content: center; background: var(--secondary); color: white; border: none;">Test Connection</button>';
        html += '<button type="button" onclick="syncIntegration(\'' + integration + '\')" class="nav-item" style="flex: 1; justify-content: center; background: var(--info); color: white; border: none;">Sync Now</button>';
        html += '</div>';
        
        html += '<button type="submit" class="nav-item" style="width: 100%; justify-content: center; background: var(--primary); color: white; border: none; margin-top: 1rem;">Save Settings</button>';
        html += '</form>';
        
        content.innerHTML = html;
        modal.style.display = 'flex';
        
    } catch (err) {
        alert('Failed to load settings: ' + err.message);
    }
}

// Save integration settings
async function saveIntegrationSettings(event, integration) {
    event.preventDefault();
    
    const syncEnabled = document.getElementById('setting-sync-enabled').checked;
    const settings = {};
    
    // Collect integration-specific settings
    if (document.getElementById('setting-channel')) {
        settings.default_channel = document.getElementById('setting-channel').value;
    }
    if (document.getElementById('setting-sync-direction')) {
        settings.sync_direction = document.getElementById('setting-sync-direction').value;
    }
    if (document.getElementById('setting-signature')) {
        settings.signature = document.getElementById('setting-signature').value;
    }
    
    try {
        const response = await fetch(API_URL + '/integrations/' + integration + '/settings', {
            method: 'POST',
            headers: { 
                'X-API-KEY': 'finrag_at_2026',
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                sync_enabled: syncEnabled,
                settings: settings
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            alert('Settings saved!');
            closeConnectModal();
        } else {
            alert('Failed to save settings: ' + data.message);
        }
    } catch (err) {
        alert('Error saving settings: ' + err.message);
    }
}

// Export Analysis as Markdown file
function exportAnalysis() {
    const analysisBox = document.getElementById('analysis-markdown');
    const analysisContent = analysisBox.innerText || analysisBox.textContent;
    
    if (!analysisContent || analysisContent.includes('Report will populate here')) {
        alert('No analysis available to export. Please upload and process a document first.');
        return;
    }
    
    const blob = new Blob([analysisContent], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `analysis_${new Date().toISOString().split('T')[0]}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// Export Email Draft as text file
function exportEmail() {
    const emailBox = document.getElementById('email-draft');
    const emailContent = emailBox.innerText || emailBox.textContent;
    
    if (!emailContent || emailContent.includes('Select a revert to view draft.')) {
        alert('No email draft available to export. Please upload and process a document first.');
        return;
    }
    
    const blob = new Blob([emailContent], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `email_draft_${new Date().toISOString().split('T')[0]}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// Copy Email to clipboard
function copyEmail() {
    const emailBox = document.getElementById('email-draft');
    const emailContent = emailBox.innerText || emailBox.textContent;
    
    if (!emailContent || emailContent.includes('Select a revert to view draft.')) {
        alert('No email draft available to copy. Please upload and process a document first.');
        return;
    }
    
    navigator.clipboard.writeText(emailContent).then(() => {
        alert('Email draft copied to clipboard!');
    }).catch(err => {
        alert('Failed to copy: ' + err);
    });
}

// Update section loading to include new functions
const originalShowSection = showSection;
showSection = function(section) {
    originalShowSection(section);
    
    if (section === 'drafts') {
        loadDrafts();
    }
    if (section === 'compliance') {
        loadCompliance();
    }
    if (section === 'integrations') {
        loadIntegrations();
    }
};
