console.log('[Features] Loading features-reporting.js...');





// --- REPORTING MODULE LOGIC ---





// Track which report is currently being displayed


let _activeReportType = null; // 'report', 'http', or 'hunter'





/**


 * Initializes the reporting view by loading artifacts and selecting a report.


 */


async function initReporting() {


 const emptyState = document.getElementById('report-empty-state');


 const reportingLayout = document.getElementById('reporting-layout');





 // Default: show empty state


 if (emptyState) emptyState.classList.remove('hidden');


 if (reportingLayout) reportingLayout.classList.add('hidden');





 // Load artifacts sidebar


 const hasArtifacts = await loadArtifacts();





 if (hasArtifacts) {


 if (emptyState) emptyState.classList.add('hidden');


 if (reportingLayout) reportingLayout.classList.remove('hidden');





 // Auto-select: prefer the last active, then hunter_report, then http_report, then report


 if (!_activeReportType) {


 const hunterExists = document.querySelector('.artifact-item[data-report-type="hunter"]');


 const httpExists = document.querySelector('.artifact-item[data-report-type="http"]');


 const scanExists = document.querySelector('.artifact-item[data-report-type="report"]');





 if (hunterExists) {


 selectReport('hunter');


 } else if (httpExists) {


 selectReport('http');


 } else if (scanExists) {


 selectReport('report');


 }


 } else {


 selectReport(_activeReportType);


 }


 }





 // --- Generate Report Button ---


 const genBtn = document.getElementById('generate-report-btn');


 const genInput = document.getElementById('report-target-input');


 if (genBtn && genInput) {


 genBtn.addEventListener('click', async () => {


 const target = genInput.value.trim();


 if (!target) {


 alert('Please enter a target domain.');


 return;


 }





 genBtn.disabled = true;


 genBtn.textContent = 'Generating...';





 try {


 const response = await fetch('/report/generate', {


 method: 'POST',


 headers: { 'Content-Type': 'application/json' },


 body: JSON.stringify({ target: target })


 });


 const data = await response.json();





 if (!response.ok) throw new Error(data.detail || 'Report generation failed');





 const findingsCount = data.report?.findings?.length || 0;


 alert(`Report generated with ${findingsCount} finding(s).`);


 initReporting();


 } catch (e) {


 alert('Error generating report: ' + e.message);


 } finally {


 genBtn.disabled = false;


 genBtn.textContent = 'Generate Report';


 }


 });


 }


}





/**


 * Fetches the artifacts list from the backend and populates the sidebar.


 * Returns true if at least one report file exists.


 */


async function loadArtifacts() {


 if (typeof isOffline !== 'undefined' && isOffline()) return false;





 try {


 const response = await fetch('/api/report/artifacts');


 if (!response.ok) return false;





 const data = await response.json();


 const artifacts = data.artifacts || [];





 // Split into reports vs data files


 const reports = artifacts.filter(a => a.clickable);


 const dataFiles = artifacts.filter(a => !a.clickable);





 // Update count badge


 const countEl = document.getElementById('artifacts-count');


 if (countEl) countEl.textContent = `${artifacts.length} file${artifacts.length !== 1 ? 's' : ''}`;





 // Render reports section


 const reportsContainer = document.getElementById('artifacts-reports-list');


 if (reportsContainer) {


 if (reports.length === 0) {


 reportsContainer.innerHTML = '<div class="artifact-placeholder">No reports available</div>';


 } else {


 reportsContainer.innerHTML = reports.map(artifact => {


 // Properly map the report types


 let reportType = 'report';


 let icon = '';


 let displayName = 'Scan Report';





 if (artifact.name === 'http_report.json') {


 reportType = 'http';


 icon = '';


 displayName = 'HTTP Analysis Report';


 } else if (artifact.name === 'hunter_report.json') {


 reportType = 'hunter';


 icon = '';


 displayName = 'Hunter Agent Report';


 }





 const isActive = _activeReportType === reportType;





 return `


 <div class="artifact-item clickable ${isActive ? 'active' : ''}"


 data-report-type="${reportType}"


 onclick="selectReport('${reportType}')">


 <span class="artifact-icon">${icon}</span>


 <div class="artifact-info">


 <span class="artifact-name">${displayName}</span>


 <span class="artifact-size">${artifact.name} ${formatFileSize(artifact.size)}</span>


 </div>


 <button class="artifact-download-btn" title="Download"


 onclick="event.stopPropagation(); downloadArtifact('${artifact.path}')"></button>


 </div>


 `;


 }).join('');


 }


 }





 // Render data files section


 const dataContainer = document.getElementById('artifacts-data-list');


 if (dataContainer) {


 if (dataFiles.length === 0) {


 dataContainer.innerHTML = '<div class="artifact-placeholder">No data files</div>';


 } else {


 dataContainer.innerHTML = dataFiles.map(artifact => {


 const icon = artifact.name.endsWith('.json') ? '' : '';


 return `


 <div class="artifact-item" data-artifact-name="${artifact.name}">


 <span class="artifact-icon">${icon}</span>


 <div class="artifact-info">


 <span class="artifact-name">${artifact.name}</span>


 <span class="artifact-size">${formatFileSize(artifact.size)}</span>


 </div>


 <button class="artifact-download-btn" title="Download" style="opacity:1;"


 onclick="downloadArtifact('${artifact.path}')"></button>


 </div>


 `;


 }).join('');


 }


 }





 return reports.length > 0;


 } catch (e) {


 console.error('Failed to load artifacts:', e);


 return false;


 }


}





/**


 * Selects and loads a report into the dashboard.


 * @param {'report' | 'http' | 'hunter'} reportType


 */


async function selectReport(reportType) {


 // Map to the correct backend endpoint


 let endpoint = '/api/report';


 if (reportType === 'http') endpoint = '/api/report/http';


 if (reportType === 'hunter') endpoint = '/api/report/hunter';





 try {


 const response = await fetch(endpoint);


 if (!response.ok) {


 console.warn(`[Report] Failed to load ${reportType}: ${response.status}`);


 return;


 }





 const reportData = await response.json();


 renderReportDashboard(reportData);


 _activeReportType = reportType;





 // Update sidebar active state


 document.querySelectorAll('.artifact-item.clickable').forEach(item => {


 item.classList.toggle('active', item.dataset.reportType === reportType);


 });





 // Update the source badge in the report header


 const badge = document.getElementById('report-source-badge');


 if (badge) {


 if (reportType === 'http') {


 badge.textContent = 'HTTP Analysis';


 badge.style.background = '#0ea5e9';


 } else if (reportType === 'hunter') {


 badge.textContent = 'Hunter Agent';


 badge.style.background = '#e11d48'; // A distinct red/pink color


 } else {


 badge.textContent = 'Scan Report';


 badge.style.background = '#8b5cf6';


 }


 badge.style.display = 'inline-block';


 badge.style.color = '#fff';


 }





 // Update the date


 const dateEl = document.querySelector('.report-date');


 if (dateEl && reportData.meta?.timestamp) {


 dateEl.textContent = `Generated: ${new Date(reportData.meta.timestamp).toLocaleString()}`;


 }





 console.log(`[Report] Loaded ${reportType} report`);


 } catch (e) {


 console.error(`[Report] Error loading ${reportType}:`, e);


 }


}





/**


 * Downloads an artifact file.


 */


function downloadArtifact(filepath) {


 const url = `/api/report/download/${filepath}`;


 const a = document.createElement('a');


 a.href = url;


 a.download = filepath.split('/').pop();


 document.body.appendChild(a);


 a.click();


 document.body.removeChild(a);


}





/**


 * Formats bytes into human-readable file size.


 */


function formatFileSize(bytes) {


 if (!bytes || bytes === 0) return '0 B';


 const units = ['B', 'KB', 'MB', 'GB'];


 let i = 0;


 let size = bytes;


 while (size >= 1024 && i < units.length - 1) {


 size /= 1024;


 i++;


 }


 return `${size.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;


}





// Expose globally for onclick handlers


window.selectReport = selectReport;


window.downloadArtifact = downloadArtifact;





/**


 * Exports the currently loaded report as a fully self-contained, interactive HTML file.


 * The exported file includes embedded data, Chart.js charts, and full interactivity.


 */


function exportReportAsHTML() {


 if (!window.CURRENT_REPORT_DATA || window.CURRENT_REPORT_DATA.length === 0) {


 alert('No report data loaded. Please select a report first.');


 return;


 }





 const findings = window.CURRENT_REPORT_DATA;


 const riskScore = document.getElementById('risk-score-display')?.textContent || '0.0';


 const summaryText = document.getElementById('ai-summary-text')?.innerHTML || '';


 const reportDate = document.querySelector('.report-date')?.textContent || 'Generated: Export';


 const sourceBadge = document.getElementById('report-source-badge');


 const badgeText = sourceBadge?.textContent || '';


 const badgeBg = sourceBadge?.style?.background || '#8b5cf6';





 // Severity counts for chart


 const counts = { Critical: 0, High: 0, Medium: 0, Low: 0 };


 findings.forEach(f => { if (counts[f.severity] !== undefined) counts[f.severity]++; });





 // Category counts for chart


 const catMap = {};


 findings.forEach(f => { catMap[f.category] = (catMap[f.category] || 0) + 1; });





 const findingsJson = JSON.stringify(findings);





 const badgeHtml = badgeText ? '<span class="badge" style="background:' + badgeBg + '">' + badgeText + '</span>' : '';





 const htmlParts = [


 '<!DOCTYPE html>',


 '<html lang="en">',


 '<head>',


 '<meta charset="UTF-8">',


 '<meta name="viewport" content="width=device-width, initial-scale=1.0">',


 '<title>VibeSecurity Report</title>',


 '<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>',


 '<style>',


 ' *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }',


 ' body { font-family: "Segoe UI", system-ui, sans-serif; background: #f8fafc; color: #1e293b; min-height: 100vh; }',


 ' .report-wrapper { max-width: 1200px; margin: 0 auto; padding: 32px 24px; }',


 ' .report-top-bar { display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 12px; margin-bottom: 28px; padding-bottom: 20px; border-bottom: 1px solid #e2e8f0; }',


 ' .report-meta h3 { font-size: 1.5rem; font-weight: 700; color: #0f172a; }',


 ' .report-date { font-size: 0.82rem; color: #64748b; margin-top: 4px; display: block; }',


 ' .badge { display: inline-block; padding: 2px 12px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; color: #fff; margin-top: 6px; }',


 ' .watermark { font-size: 0.8rem; color: #94a3b8; letter-spacing: 1px; text-transform: uppercase; font-weight: 600; }',


 ' .dashboard-row { display: grid; grid-template-columns: 180px 1fr 1fr; gap: 20px; margin-bottom: 24px; }',


 ' @media (max-width: 768px) { .dashboard-row { grid-template-columns: 1fr; } }',


 ' .card { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }',


 ' .score-card { text-align: center; }',


 ' .score-card h4 { font-size: 0.85rem; color: #64748b; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; }',


 ' .big-score { font-size: 3rem; font-weight: 800; background: linear-gradient(135deg, #0ea5e9, #8b5cf6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }',


 ' .score-label { font-size: 0.75rem; color: #94a3b8; display: block; margin-top: 4px; }',


 ' .card h4 { font-size: 0.9rem; color: #64748b; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 16px; }',


 ' .canvas-container { height: 180px; position: relative; }',


 ' .summary-section { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }',


 ' .summary-section h4 { font-size: 0.9rem; color: #64748b; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; }',


 ' .summary-section p { line-height: 1.7; color: #334155; }',


 ' .split-view { display: grid; grid-template-columns: 320px 1fr; gap: 20px; }',


 ' @media (max-width: 860px) { .split-view { grid-template-columns: 1fr; } }',


 ' .vuln-sidebar { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; display: flex; flex-direction: column; max-height: 70vh; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }',


 ' .list-header { padding: 16px; border-bottom: 1px solid #e2e8f0; display: flex; flex-direction: column; gap: 8px; background: #f8fafc; }',


 ' .list-header h4 { font-size: 0.9rem; color: #64748b; text-transform: uppercase; letter-spacing: 1px; }',


 ' .filter-input { width: 100%; padding: 7px 12px; border-radius: 6px; border: 1px solid #cbd5e1; background: #ffffff; color: #0f172a; font-size: 0.85rem; outline: none; }',


 ' .filter-input:focus { border-color: #8b5cf6; box-shadow: 0 0 0 2px rgba(139,92,246,0.2); }',


 ' .vuln-items { overflow-y: auto; flex: 1; }',


 ' .vuln-item { padding: 12px 16px; border-bottom: 1px solid #f1f5f9; cursor: pointer; transition: background 0.15s; }',


 ' .vuln-item:hover, .vuln-item.active { background: #f1f5f9; }',


 ' .vuln-item-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }',


 ' .vuln-title { font-size: 0.875rem; font-weight: 600; color: #0f172a; }',


 ' .sev-badge { font-size: 0.75rem; font-weight: 700; white-space: nowrap; }',


 ' .vuln-sub { font-size: 0.78rem; color: #64748b; margin-top: 4px; }',


 ' .details-panel { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 24px; overflow-y: auto; max-height: 70vh; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }',


 ' .details-empty { color: #94a3b8; text-align: center; padding: 60px 20px; }',


 ' .detail-title { font-size: 1.2rem; font-weight: 700; color: #0f172a; margin-bottom: 16px; }',


 ' .detail-tags { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px; }',


 ' .tag { padding: 4px 12px; border-radius: 4px; font-size: 0.82rem; font-weight: 600; }',


 ' .detail-section { margin-bottom: 20px; }',


 ' .detail-section h5 { font-size: 0.82rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }',


 ' .detail-code { display: block; background: #f8fafc; border: 1px solid #e2e8f0; padding: 10px 14px; border-radius: 6px; font-family: monospace; font-size: 0.82rem; color: #0369a1; word-break: break-all; }',


 ' .detail-text { line-height: 1.7; color: #334155; font-size: 0.9rem; }',


 ' .remediation-box { background: #f0fdf4; padding: 16px; border-left: 4px solid #22c55e; border-radius: 0 8px 8px 0; border-top: 1px solid #dcfce7; border-right: 1px solid #dcfce7; border-bottom: 1px solid #dcfce7; }',


 ' .footer { text-align: center; padding: 40px 0 20px; color: #94a3b8; font-size: 0.8rem; }',


 ' ::-webkit-scrollbar { width: 6px; } ::-webkit-scrollbar-track { background: transparent; } ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }',


 '</style>',


 '</head>',


 '<body>',


 '<div class="report-wrapper">',


 ' <div class="report-top-bar">',


 ' <div class="report-meta">',


 ' <h3>VibeSecurity Security Report</h3>',


 ' <span class="report-date">' + reportDate + '</span>',


 ' ' + badgeHtml,


 ' </div>',


 ' <span class="watermark">VibeSecurity</span>',


 ' </div>',


 ' <div class="dashboard-row">',


 ' <div class="card score-card">',


 ' <h4>Risk Score</h4>',


 ' <div class="big-score">' + riskScore + '</div>',


 ' <span class="score-label">CVSS Average</span>',


 ' </div>',


 ' <div class="card">',


 ' <h4>Severity Breakdown</h4>',


 ' <div class="canvas-container"><canvas id="chart-severity"></canvas></div>',


 ' </div>',


 ' <div class="card">',


 ' <h4>Vulnerability Categories</h4>',


 ' <div class="canvas-container"><canvas id="chart-categories"></canvas></div>',


 ' </div>',


 ' </div>',


 ' <div class="summary-section">',


 ' <h4>AI Assessment</h4>',


 ' <p>' + summaryText + '</p>',


 ' </div>',


 ' <div class="split-view">',


 ' <div class="vuln-sidebar">',


 ' <div class="list-header">',


 ' <h4>Findings List</h4>',


 ' <input type="text" class="filter-input" id="filter-input" placeholder="Filter findings..." oninput="applyFilter(this.value)">',


 ' </div>',


 ' <div class="vuln-items" id="vuln-items"></div>',


 ' </div>',


 ' <div class="details-panel" id="details-panel">',


 ' <div class="details-empty">Select a vulnerability from the left to view details.</div>',


 ' </div>',


 ' </div>',


 ' <div class="footer">Exported by VibeSecurity &middot; ' + new Date().toLocaleString() + ' &middot; For authorized security use only</div>',


 '</div>',


 '<script>',


 'const FINDINGS = ' + findingsJson + ';',


 'const SCOUNT = ' + JSON.stringify(counts) + ';',


 'const CMAP = ' + JSON.stringify(catMap) + ';',


 'function getSevColor(s) { return ({Critical:"#ef4444",High:"#f97316",Medium:"#eab308",Low:"#3b82f6"})[s]||"#3b82f6"; }',


 'function renderList(items) {',


 ' const container = document.getElementById("vuln-items");',


 ' if (!items.length) { container.innerHTML = "<div style=\\"padding:20px;color:#94a3b8;text-align:center\\">No findings match filter</div>"; return; }',


 ' let html = "";',


 ' for (let i=0; i<items.length; i++) {',


 ' let f = items[i];',


 ' let sub = (f.category||"") + (f.location ? " &middot; " + f.location : "");',


 ' html += "<div class=\\"vuln-item\\" data-id=\\"" + f.id + "\\" onclick=\\"showDetail(\'" + f.id + "\')\\">";',


 ' html += " <div class=\\"vuln-item-top\\">";',


 ' html += " <span class=\\"vuln-title\\">" + (f.title||"") + "</span>";',


 ' html += " <span class=\\"sev-badge\\" style=\\"color:" + getSevColor(f.severity) + "\\">" + (f.severity||"") + "</span>";',


 ' html += " </div>";',


 ' html += " <div class=\\"vuln-sub\\">" + sub + "</div>";',


 ' html += "</div>";',


 ' }',


 ' container.innerHTML = html;',


 '}',


 'function showDetail(id) {',


 ' const f = FINDINGS.find(function(x) { return x.id === id; });',


 ' if (!f) return;',


 ' document.querySelectorAll(".vuln-item").forEach(function(el) { el.classList.remove("active"); });',


 ' const el = document.querySelector(".vuln-item[data-id=\\"" + id + "\\"]");',


 ' if (el) el.classList.add("active");',


 ' let tagsHtml = "<span class=\\"tag\\" style=\\"background:" + getSevColor(f.severity) + ";color:#fff\\">" + (f.severity||"") + "</span>";',


 ' tagsHtml += "<span class=\\"tag\\" style=\\"background:#f1f5f9;color:#475569;border:1px solid #e2e8f0\\">CVSS: " + (f.cvss||"N/A") + "</span>";',


 ' if (f.category) tagsHtml += "<span class=\\"tag\\" style=\\"background:#e0e7ff;color:#4338ca\\">" + f.category + "</span>";',


 ' let detHtml = "<div class=\\"detail-title\\">" + (f.title||"") + "</div>";',


 ' detHtml += "<div class=\\"detail-tags\\">" + tagsHtml + "</div>";',


 ' detHtml += "<div class=\\"detail-section\\"><h5>Location</h5><code class=\\"detail-code\\">" + (f.location||"N/A") + "</code></div>";',


 ' detHtml += "<div class=\\"detail-section\\"><h5>Description</h5><p class=\\"detail-text\\">" + (f.description||"No description available.") + "</p></div>";',


 ' detHtml += "<div class=\\"detail-section\\"><h5>Remediation</h5><div class=\\"remediation-box\\"><p class=\\"detail-text\\">" + (f.remediation||"No remediation guidance available.") + "</p></div></div>";',


 ' document.getElementById("details-panel").innerHTML = detHtml;',


 '}',


 'function applyFilter(q) {',


 ' q = q.toLowerCase();',


 ' const filtered = FINDINGS.filter(function(f) {',


 ' return (f.title||"").toLowerCase().includes(q) || (f.category||"").toLowerCase().includes(q) || (f.severity||"").toLowerCase().includes(q);',


 ' });',


 ' renderList(filtered);',


 '}',


 'renderList(FINDINGS);',


 'if (typeof Chart !== "undefined") {',


 ' new Chart(document.getElementById("chart-severity"), {',


 ' type: "doughnut",',


 ' data: {',


 ' labels: ["Critical","High","Medium","Low"],',


 ' datasets: [{ data: [SCOUNT.Critical,SCOUNT.High,SCOUNT.Medium,SCOUNT.Low], backgroundColor: ["#ef4444","#f97316","#eab308","#3b82f6"], borderWidth: 2, borderColor: "#ffffff" }]',


 ' },',


 ' options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "right", labels: { color: "#475569", font: { family: "system-ui" } } } }, cutout: "65%" }',


 ' });',


 ' new Chart(document.getElementById("chart-categories"), {',


 ' type: "bar",',


 ' data: {',


 ' labels: Object.keys(CMAP),',


 ' datasets: [{ label: "Findings", data: Object.values(CMAP), backgroundColor: "#8b5cf6", borderRadius: 4 }]',


 ' },',


 ' options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true, ticks: { color: "#64748b" }, grid: { color: "#f1f5f9" } }, x: { ticks: { color: "#64748b" }, grid: { display: false } } }, plugins: { legend: { display: false } } }',


 ' });',


 '}',


 '</script>',


 '</body>',


 '</html>'


 ];





 const finalHtml = htmlParts.join('\n');





 // Trigger download


 const blob = new Blob([finalHtml], { type: 'text/html;charset=utf-8' });


 const url = URL.createObjectURL(blob);


 const a = document.createElement('a');


 const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);


 a.href = url;


 a.download = 'vibesecurity-report-' + timestamp + '.html';


 document.body.appendChild(a);


 a.click();


 document.body.removeChild(a);


 URL.revokeObjectURL(url);


}





window.exportReportAsHTML = exportReportAsHTML;





function renderReportDashboard(data) {


 if (!data || !data.findings) return;





 const findings = data.findings;


 // Auto-assign unique IDs if the backend didn't provide them


 findings.forEach((f, i) => { if (!f.id) f.id = `finding-${i}`; });





 const avgRisk = data.summary?.risk_score || 0;





 const riskEl = document.getElementById('risk-score-display');


 if (riskEl) riskEl.textContent = avgRisk;





 renderSeverityChart(findings);


 renderCategoryChart(findings);





 const summaryText = data.summary?.executive_text || generateFallbackSummary(findings, avgRisk);


 const summaryEl = document.getElementById('ai-summary-text');


 if (summaryEl) summaryEl.innerHTML = summaryText;





 renderVulnList(findings);


 window.CURRENT_REPORT_DATA = findings;





 // Wire up the filter input


 const filterInput = document.querySelector('.report-split-container .paper-input');


 if (filterInput) {


 filterInput.addEventListener('input', () => {


 const q = filterInput.value.toLowerCase();


 const filtered = findings.filter(f =>


 (f.title || '').toLowerCase().includes(q) ||


 (f.category || '').toLowerCase().includes(q) ||


 (f.severity || '').toLowerCase().includes(q)


 );


 renderVulnList(filtered);


 });


 }


}





let severityChartInstance = null;


let categoryChartInstance = null;





function renderSeverityChart(findings) {


 const canvas = document.getElementById('chart-severity');


 if (!canvas) return;


 const ctx = canvas.getContext('2d');





 const counts = { Critical: 0, High: 0, Medium: 0, Low: 0 };


 findings.forEach(f => { if (counts[f.severity] !== undefined) counts[f.severity]++; });





 // Destroy existing chart if present (assumes Chart.js is loaded in the DOM)


 if (severityChartInstance) severityChartInstance.destroy();





 // Prevent errors if Chart is not defined globally yet


 if (typeof Chart === 'undefined') return;





 severityChartInstance = new Chart(ctx, {


 type: 'doughnut',


 data: {


 labels: ['Critical', 'High', 'Medium', 'Low'],


 datasets: [{


 data: [counts.Critical, counts.High, counts.Medium, counts.Low],


 backgroundColor: ['#c0392b', '#e67e22', '#f1c40f', '#3498db'],


 borderWidth: 1


 }]


 },


 options: {


 responsive: true,


 maintainAspectRatio: false,


 plugins: { legend: { position: 'right' } }


 }


 });


}





function renderCategoryChart(findings) {


 const canvas = document.getElementById('chart-categories');


 if (!canvas) return;


 const ctx = canvas.getContext('2d');





 const catMap = {};


 findings.forEach(f => { catMap[f.category] = (catMap[f.category] || 0) + 1; });





 if (categoryChartInstance) categoryChartInstance.destroy();


 


 // Prevent errors if Chart is not defined globally yet


 if (typeof Chart === 'undefined') return;





 categoryChartInstance = new Chart(ctx, {


 type: 'bar',


 data: {


 labels: Object.keys(catMap),


 datasets: [{


 label: 'Findings',


 data: Object.values(catMap),


 backgroundColor: '#2c3e50'


 }]


 },


 options: {


 responsive: true,


 maintainAspectRatio: false,


 scales: { y: { beginAtZero: true } }


 }


 });


}





function generateFallbackSummary(findings, avgRisk) {


 return `Analysis complete. Risk Score: <strong>${avgRisk}</strong>. Identified <strong>${findings.length}</strong> unique vulnerabilities.`;


}





function renderVulnList(findings) {


 const listContainer = document.getElementById('vuln-list-items');


 if (!listContainer) return;





 if (findings.length === 0) {


 listContainer.innerHTML = '<div class="vuln-item-placeholder">No findings match filter</div>';


 return;


 }





 listContainer.innerHTML = findings.map(f => `


 <div class="vuln-list-item" data-finding-id="${f.id}" onclick="viewVulnDetails('${f.id}')"


 style="padding: 12px 15px; border-bottom: 1px solid #ecf0f1; cursor: pointer; transition: background 0.15s ease;"


 onmouseover="this.style.background='#f0f4f8'" onmouseout="if(!this.classList.contains('active-finding'))this.style.background=''">


 <div style="display:flex; justify-content:space-between; align-items:center;">


 <strong style="font-size: 0.9rem;">${f.title}</strong>


 <span style="color: ${getSeverityColor(f.severity)}; font-size: 0.8rem; font-weight: 600; white-space: nowrap; margin-left: 8px;">${f.severity}</span>


 </div>


 <div style="font-size: 0.78rem; color: #7f8c8d; margin-top: 4px;">${f.category}${f.location ? ' ' + f.location : ''}</div>


 </div>


 `).join('');


}





function getSeverityColor(sev) {


 switch (sev) {


 case 'Critical': return '#c0392b';


 case 'High': return '#e67e22';


 case 'Medium': return '#f1c40f';


 default: return '#3498db';


 }


}





window.viewVulnDetails = function (id) {


 if (!window.CURRENT_REPORT_DATA) return;


 const finding = window.CURRENT_REPORT_DATA.find(f => f.id === id);


 if (!finding) return;





 // Highlight active item in the list


 document.querySelectorAll('.vuln-list-item').forEach(el => {


 el.classList.remove('active-finding');


 el.style.background = '';


 });


 const activeEl = document.querySelector(`.vuln-list-item[data-finding-id="${id}"]`);


 if (activeEl) {


 activeEl.classList.add('active-finding');


 activeEl.style.background = '#e8f4fd';


 }





 const detailsPanel = document.getElementById('vuln-details-content');


 if (!detailsPanel) return;





 detailsPanel.innerHTML = `


 <h3 style="margin-top:0;">${finding.title}</h3>


 <div style="display:flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap;">


 <span style="background:${getSeverityColor(finding.severity)}; color:white; padding: 4px 12px; border-radius:4px; font-weight: 600; font-size: 0.85rem;">${finding.severity}</span>


 <span style="background:#ecf0f1; padding: 4px 12px; border-radius:4px; font-size: 0.85rem;">CVSS: ${finding.cvss || 'N/A'}</span>


 ${finding.category ? `<span style="background:#eef2ff; color:#4338ca; padding: 4px 12px; border-radius:4px; font-size: 0.85rem;">${finding.category}</span>` : ''}


 </div>


 <h5 style="color:#2c3e50; margin-bottom:8px;">Location</h5>


 <code style="display:block; background:#f8f9fa; padding:10px; border-radius:4px; margin-bottom:20px; word-break:break-all; font-size:0.85rem;">${finding.location || 'N/A'}</code>


 <h5 style="color:#2c3e50; margin-bottom:8px;">Description</h5>


 <p style="margin-bottom:20px; line-height:1.6; color:#34495e;">${finding.description || 'No description available.'}</p>


 <h5 style="color:#2c3e50; margin-bottom:8px;">Remediation</h5>


 <div style="background:#e8f6f3; padding:15px; border-left: 4px solid #27ae60; border-radius: 0 4px 4px 0;">


 <p style="margin:0; line-height:1.6; color:#2c3e50;">${finding.remediation || 'No remediation guidance available.'}</p>


 </div>


 `;


};


