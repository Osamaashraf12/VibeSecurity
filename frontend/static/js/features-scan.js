console.log('[Features] Loading features-scan.js...');

// --- SCANNING & MODULE LOGIC ---

/**
 * Generic helper to execute a tool via its backend endpoint.
 * Handles both immediate responses and long-running Celery tasks.
 */
async function executeTool(toolKey, target, options = {}, progressCallback = null) {
    const endpoint = TOOL_API_MAP[toolKey];
    if (!endpoint) {
        console.warn(`[API] No endpoint mapped for tool: ${toolKey}`);
        return { status: "skipped", reason: "no_endpoint" };
    }

    if (isOffline()) {
        console.warn(`[Offline] Skipping ${toolKey} execution. Server required.`);
        return { status: "error", message: "This feature requires the VibeSecurity server to be running." };
    }

    console.log(`[API] POST ${endpoint} | Target: ${target}`);

    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target: target, options: options })
        });

        if (!response.ok) throw new Error(`HTTP ${response.status} - ${response.statusText}`);
        const data = await response.json();

        if (data.task_id) {
            console.log(`[API] Task dispatched with ID: ${data.task_id}. Beginning polling...`);
            return await pollTaskStatus(data.task_id, progressCallback);
        }

        return data;
    } catch (e) {
        console.error(`[API] Failed to run ${toolKey}:`, e);
        return { status: "error", error: e.message };
    }
}

/**
 * Polls the /status/{taskId} endpoint until a SUCCESS or FAILURE state is reached.
 */
async function pollTaskStatus(taskId, progressCallback = null) {
    const pollInterval = 3000;

    while (true) {
        try {
            const res = await fetch(`/status/${taskId}`);
            if (!res.ok) throw new Error(`Polling failed: ${res.status}`);

            const statusData = await res.json();
            console.log(`[Task ${taskId}] Status: ${statusData.state}`);

            if (progressCallback) {
                progressCallback(statusData.state);
            }

            if (statusData.state === 'SUCCESS') {
                return { status: "success", message: statusData.result };
            } else if (statusData.state === 'FAILURE') {
                return { status: "error", message: statusData.error || "Task failed internally." };
            }

            await new Promise(resolve => setTimeout(resolve, pollInterval));
        } catch (err) {
            console.error(`[Task Polling Error]`, err);
            return { status: "error", message: err.message };
        }
    }
}

/**
 * Handles intent parsing and scan triggering for the main dashboard and recon views.
 */
function initScan() {
    const scanButtons = ['.start-scan', '#start-full-scan'];

    document.body.addEventListener('click', async function (e) {
        if (!e.target.matches(scanButtons.join(','))) return;

        const btn = e.target;
        const container = btn.closest('.config-form');
        const inputField = container ? container.querySelector('input[type="text"]') : null;

        if (!inputField || !inputField.value.trim()) {
            alert("Please enter a target or a scan instruction.");
            return;
        }

        const userIntent = inputField.value.trim();
        const view = btn.closest('.view') || document.querySelector('#view-dashboard');
        const resultContainer = view.querySelector('.scan-results');

        const checkedBoxes = view.querySelectorAll('.submodule-checkbox input:checked');
        if (checkedBoxes.length > 0) {
            let selectedTools = Array.from(checkedBoxes).map(cb => cb.value);
            selectedTools = sortToolsByDependency(selectedTools);

            const toolsSteps = [];
            selectedTools.forEach(moduleId => {
                const container = view.querySelector(`input[id="${moduleId}"]`).closest('.submodule-container');
                const subToolsChecked = container ? container.querySelectorAll(`input[data-subtool]:checked`) : [];
                let selectedSubTools = Array.from(subToolsChecked).map(cb => cb.value);

                let args = {};
                if (selectedSubTools.length > 0) {
                    args.tools = selectedSubTools;
                }

                toolsSteps.push({
                    tool_name: moduleId,
                    arguments: args
                });
            });

            const manualPlan = {
                target: userIntent,
                action: "scan",
                source: "manual_selection",
                steps: toolsSteps
            };

            if (resultContainer) {
                resultContainer.classList.remove('hidden');
                displayParsedPlan(resultContainer.querySelector('.results-grid'), JSON.stringify(manualPlan), "Manual Selection (Checkboxes)");
            }
            return;
        }

        // AI MODE
        const originalText = btn.textContent;
        btn.textContent = "AI Parsing...";
        btn.disabled = true;

        if (resultContainer) {
            resultContainer.classList.remove('hidden');
            resultContainer.querySelector('.results-grid').innerHTML = `
                <div class="result-card loading">
                    <h4>Analyzing Intent...</h4>
                    <p>Contacting Language Model...</p>
                </div>`;
        }

        if (isOffline()) {
            setTimeout(() => {
                if (resultContainer) {
                    resultContainer.querySelector('.results-grid').innerHTML = `
                        <div class="result-card warning">
                            <h4>Offline Mode</h4>
                            <p>AI Parsing is unavailable. Please start the server to use natural language scanning.</p>
                        </div>`;
                }
                btn.textContent = originalText;
                btn.disabled = false;
            }, 500);
            return;
        }

        try {
            const response = await fetch('/api/parser_user', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: userIntent })
            });

            if (!response.ok) throw new Error(`Server Error: ${response.status}`);

            const data = await response.json();

            if (resultContainer) {
                displayParsedPlan(resultContainer.querySelector('.results-grid'), data.response, userIntent);
            }

        } catch (error) {
            console.error("Scan Error:", error);
            if (resultContainer) {
                resultContainer.querySelector('.results-grid').innerHTML = `
                    <div class="result-card error">
                        <h4>Connection Failed</h4>
                        <p>${error.message}</p>
                    </div>`;
            }
        } finally {
            btn.textContent = originalText;
            btn.disabled = false;
        }
    });
}

/**
 * Displays the AI-generated or manually selected plan for approval.
 */
function displayParsedPlan(container, jsonString, originalPrompt) {
    let jsonObj = {};
    try {
        jsonObj = JSON.parse(jsonString);
    } catch (e) {
        jsonObj = { error: "Failed to parse JSON" };
    }

    container.innerHTML = `
        <div class="result-card" style="grid-column: span 3; border-left: 4px solid var(--color-primary);">
            <div class="card-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <h4 style="margin: 0;">Scan Configuration</h4>
                <span style="font-size: 0.8rem; color: #888;">Source: ${jsonObj.source || 'AI Parser'}</span>
            </div>

            <div style="margin-bottom: 15px;">
                <strong>Input:</strong>
                <span style="color: #fff; font-style: italic;">"${originalPrompt}"</span>
            </div>

            <div class="json-viewer">
                <strong>Execution Plan:</strong>
                <pre style="background: #1a1a1a; padding: 15px; border-radius: 8px; overflow-x: auto; color: #00ff9d;">${JSON.stringify(jsonObj, null, 2)}</pre>
            </div>

            <div style="margin-top: 15px; display: flex; gap: 10px;">
                <button class="btn btn--primary btn--sm btn-execute-plan">Approve & Execute</button>
                <button class="btn btn--secondary btn--sm" onclick="alert('Editor not implemented yet')">Edit Config</button>
            </div>
        </div>
    `;

    // Target the specific button inside this container to avoid duplicate ID issues
    const execBtn = container.querySelector('.btn-execute-plan');
    if (execBtn && !jsonObj.error) {
        execBtn.addEventListener('click', () => runExecutionPlan(jsonObj, execBtn));
    }
}

/**
 * Consolidates the tool chain into a single OrchestrationPayload and dispatches it.
 */
async function runExecutionPlan(plan, btnElement) {
    if (!plan.target) {
        alert("Error: No target specified in plan.");
        return;
    }

    let tools = plan.tools || [];
    if (!plan.steps && !tools.length && plan.action === 'scan') {
        tools = ['sub_enumer', 'sub_crawler', 'tech_detector'];
    }

    if (tools.length > 0) tools = sortToolsByDependency(tools);
    console.log("Plan Execution:", plan);

    btnElement.textContent = "Validating & Dispatching...";
    btnElement.disabled = true;

    // Construct the unified OrchestrationPayload
    const payload = {
        workflow_id: 'orch_' + Date.now(),
        target: plan.target,
        source: plan.source || 'ai_parser',
        steps: plan.steps || tools.map(tool => {
            const mappedKey = Object.keys(TOOL_API_MAP).find(k => tool.includes(k)) || tool;
            return {
                tool_name: mappedKey,
                arguments: plan.options || {}
            };
        })
    };

    if (isOffline()) {
        alert("Execution Error: The VibeSecurity server is not running. Scans cannot be dispatched in Offline Mode.");
        btnElement.textContent = "Approve & Execute";
        btnElement.disabled = false;
        return;
    }

    try {
        const response = await fetch('/workflow/execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || `Server Error: ${response.status}`);
        }

        console.log(`[Orchestration] Dispatched successfully. Chain ID: ${data.chain_id}`);

        if (data.chain_id && typeof window.trackWorkflowChain === 'function') {
            btnElement.textContent = "Running...";
            const finalStatus = await window.trackWorkflowChain(data.workflow_id, data.chain_id);
            btnElement.textContent = finalStatus === 'SUCCESS' ? "Completed" : "Failed";
        } else {
            btnElement.textContent = "Dispatched";
            alert(`Orchestration dispatched!\nID: ${data.workflow_id}`);
        }

    } catch (error) {
        console.error("Orchestration Error:", error);
        alert(`Failed to start orchestration: ${error.message}`);
        btnElement.textContent = "Approve & Execute";
        btnElement.disabled = false;
    }
}

/**
 * Analyzes HTTP request/response traffic via the Thinker Agent.
 */
function initTrafficAnalyzer() {
    const analyzeBtn = document.getElementById('analyze-traffic-btn');
    if (!analyzeBtn) return;

    analyzeBtn.addEventListener('click', async () => {
        const reqText = document.getElementById('http-request-input').value.trim();
        const resText = document.getElementById('http-response-input').value.trim();
        const resultContainer = document.querySelector('#view-http-request-scan .scan-results');

        if (!reqText || !resText) {
            alert("Please provide both the HTTP Request and Response for analysis.");
            return;
        }

        analyzeBtn.textContent = "Analyzing Logic...";
        analyzeBtn.disabled = true;
        resultContainer.classList.remove('hidden');
        resultContainer.querySelector('.results-grid').innerHTML = `
            <div class="result-card loading" style="grid-column: span 3;">
                
            </div>`;

        if (isOffline()) {
            setTimeout(() => {
                resultContainer.querySelector('.results-grid').innerHTML = `
                    <div class="result-card warning" style="grid-column: span 3;">
                        <h4>Offline Mode</h4>
                        <p>Traffic Analysis (Thinker Agent) requires the VibeSecurity server.</p>
                    </div>`;
                analyzeBtn.textContent = "Analyze Traffic";
                analyzeBtn.disabled = false;
            }, 500);
            return;
        }

        try {
            const response = await fetch('/api/analyze_traffic', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ http_request: reqText, http_response: resText })
            });

            if (!response.ok) throw new Error(`Server Error: ${response.status}`);

            const data = await response.json();
            let formattedResponse;
            try {
                formattedResponse = typeof marked !== 'undefined'
                    ? marked.parse(data.response)
                    : data.response.replace(/\n/g, '<br>');
            } catch (mdErr) {
                console.warn('[marked] Markdown parse failed, using plain text fallback:', mdErr);
                formattedResponse = `<pre style="white-space:pre-wrap;word-break:break-word;">${data.response.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre>`;
            }

            // Detect completion marker injected by the system prompt
            const isComplete = data.response.trimEnd().endsWith('Done!');
            const statusBadge = isComplete
                ? `<span style="background:#16a34a;color:#fff;padding:2px 10px;border-radius:12px;font-size:0.75rem;font-weight:600;letter-spacing:0.05em;">✅ Complete</span>`
                : `<span style="background:#b45309;color:#fff;padding:2px 10px;border-radius:12px;font-size:0.75rem;font-weight:600;letter-spacing:0.05em;" title="The model did not finish its answer — output may be cut off.">⚠️ Please rerun</span>`;

            // Strip the "Done!" sentinel before rendering so it doesn't appear in the report body
            const cleanResponse = data.response.trimEnd().replace(/Done!\s*$/, '').trimEnd();
            let formattedClean;
            try {
                formattedClean = typeof marked !== 'undefined'
                    ? marked.parse(cleanResponse)
                    : cleanResponse.replace(/\n/g, '<br>');
            } catch (_) {
                formattedClean = `<pre style="white-space:pre-wrap;word-break:break-word;">${cleanResponse.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre>`;
            }

            resultContainer.querySelector('.results-grid').innerHTML = `
                <div class="result-card markdown-container" style="grid-column: span 3; border-left: 4px solid var(--color-primary);">
                    <div class="ai-report" style="line-height: 1.6; color: var(--color-text);">
                        ${formattedClean}
                    </div>
                </div>
                ${data.http_report_generated ? `
                <div class="result-card" style="grid-column: span 3; border-left: 4px solid #0ea5e9; background: rgba(14, 165, 233, 0.05); margin-top: 12px;">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <span style="font-size: 1.3rem;">📊</span>
                        <div>
                            <strong style="color: #0ea5e9;">Structured Report Generated</strong>
                            <p style="margin: 4px 0 0; font-size: 0.85rem; color: var(--color-text-muted);">
                                http_report.json has been saved. View it in the
                                <a href="#" onclick="event.preventDefault(); document.querySelector('[data-target=\\'reporting\\']').click();" style="color: #0ea5e9; text-decoration: underline;">Reporting Dashboard</a>.
                            </p>
                        </div>
                    </div>
                </div>` : ''}`;
        } catch (error) {
            console.error("Traffic Analysis Error:", error);
            resultContainer.querySelector('.results-grid').innerHTML = `
                <div class="result-card error" style="grid-column: span 3;">
                    <h4>❌ Analysis Failed</h4>
                    <p>${error.message}</p>
                </div>`;
        } finally {
            analyzeBtn.textContent = "Analyze Traffic";
            analyzeBtn.disabled = false;
        }
    });
}
