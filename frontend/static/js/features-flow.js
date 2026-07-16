console.log('[Features] Loading features-flow.js...');

// --- BUILD FLOW (WORKFLOW ENGINE) ---

let workflowConnections = [];
let tempConnection = null;
let isConnecting = false;

function initFlowBuilder() {
    const canvas = document.getElementById('flow-canvas');
    const clearBtn = document.getElementById('flow-clear-btn');
    const startBtn = document.getElementById('flow-start-btn');
    if (!canvas) return;

    let svgLayer = document.getElementById('flow-svg-layer');
    if (!svgLayer) {
        svgLayer = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svgLayer.id = 'flow-svg-layer';
        svgLayer.style.position = 'absolute';
        svgLayer.style.top = '0';
        svgLayer.style.left = '0';
        svgLayer.style.width = '100%';
        svgLayer.style.height = '100%';
        svgLayer.style.pointerEvents = 'none';
        svgLayer.style.zIndex = '1';
        canvas.appendChild(svgLayer);
    }

    canvas.addEventListener('mousemove', (e) => {
        if (isConnecting && tempConnection) updateTempConnection(e, canvas);
    });

    canvas.addEventListener('mouseup', () => {
        if (isConnecting) cancelConnection();
    });

    document.body.addEventListener('dragstart', (e) => {
        const tool = e.target.closest('.tool-card');
        if (!tool) return;
        const isFile = tool.dataset.type === 'file';
        const rawAvail = tool.dataset.availableTools || '';
        let availableTools = [];
        try { if (rawAvail) availableTools = JSON.parse(decodeURIComponent(rawAvail)); } catch(_) {}
        e.dataTransfer.setData('text/plain', JSON.stringify({
            type: isFile ? 'new-file' : 'new-tool',
            id: tool.dataset.toolId,
            name: tool.querySelector('.tool-name').innerText,
            meta: tool.dataset.flowMeta,
            toolType: tool.dataset.toolType,
            availableTools: availableTools
        }));
    });

    canvas.addEventListener('dragover', (e) => e.preventDefault());

    canvas.addEventListener('drop', (e) => {
        e.preventDefault();
        const dataStr = e.dataTransfer.getData('text/plain');
        if (!dataStr) return;
        const data = JSON.parse(dataStr);
        const rect = canvas.getBoundingClientRect();
        const x = e.clientX - rect.left + canvas.scrollLeft - 80;
        const y = e.clientY - rect.top + canvas.scrollTop - 30;
        createFlowNode(data.name, data.meta, data.toolType, x, y, data.id, data.availableTools || []);
    });

    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            canvas.querySelectorAll('.flow-node').forEach(n => n.remove());
            workflowConnections = [];
            drawConnections();
        });
    }

    if (startBtn) {
        startBtn.addEventListener('click', executeSerializedWorkflow);
    }

    // --- WORKFLOW TEMPLATES ---
    const WORKFLOW_TEMPLATES = {
        quick: {
            label: 'Quick Scan',
            tools: [
                { id: 'sub_enumer',  name: 'Passive Enumeration',     meta: 'In: Target | Out: Subdomains' },
                { id: 'sub_checker', name: 'Live Host Verification',  meta: 'In: Subdomains | Out: Live Hosts' },
                { id: 'sub_crawler', name: 'Spidering',               meta: 'In: Live Hosts | Out: URLs' },
            ]
        },
        deep: {
            label: 'Full Deep Scan',
            tools: [
                { id: 'sub_enumer',    name: 'Passive Enumeration',        meta: 'In: Target | Out: Subdomains' },
                { id: 'sub_bforcer',   name: 'Active Bruteforcing',        meta: 'In: Target, Wordlist | Out: Subdomains' },
                { id: 'sub_checker',   name: 'Live Host Verification',     meta: 'In: Subdomains | Out: Live Hosts' },
                { id: 'sub_crawler',   name: 'Spidering',                  meta: 'In: Live Hosts | Out: URLs' },
                { id: 'js_analyzer',   name: 'JS Secret Scanner',          meta: 'In: URLs | Out: JS Secrets' },
                { id: 'link_analyzer', name: 'Pattern Matcher',            meta: 'In: URLs, JS Data | Out: Patterns' },
                { id: 'tech_detector', name: 'Tech Stack Fingerprinter',   meta: 'In: URLs | Out: Tech Stack' },
                { id: 'vuln_scan',     name: 'Vulnerability Scanner',      meta: 'In: URLs, Tech Stack | Out: Vulns' },
                { id: 'active_verifiers', name: 'Active Vulnerability Verifiers', meta: 'In: Patterns, Tech Stack | Out: Verified Vulns' },
                { id: 'logic_probers', name: 'Logic Probers',              meta: 'In: URLs | Out: Logic Flaws' },
            ]
        }
    };

    function getToolConfigById(toolId) {
        if (!TOOLS_CONFIG) return null;
        const groups = [
            ...(TOOLS_CONFIG.inputs || []),
            ...(TOOLS_CONFIG.assetDiscovery || []),
            ...(TOOLS_CONFIG.contentDiscovery || []),
            ...(TOOLS_CONFIG.vulnerabilityScanning || [])
        ];
        return groups.find(tool => tool.id === toolId) || null;
    }

    document.querySelectorAll('.template-item').forEach(item => {
        item.addEventListener('click', () => {
            const templateKey = item.dataset.template;
            const template = WORKFLOW_TEMPLATES[templateKey];
            if (!template) return;

            // Clear existing nodes and connections
            canvas.querySelectorAll('.flow-node').forEach(n => n.remove());
            workflowConnections = [];
            drawConnections();

            // Layout config
            const startX = 30;
            const startY = 40;
            const nodeWidth = 180;
            const gapX = 60;
            const gapY = 0;

            // Create input node first
            createFlowNode('User input', 'Out: Target', 'input', startX, startY + 30, 'target_input');

            const createdNodeIds = [];
            const inputNodeEl = canvas.querySelector('.flow-node');
            const inputNodeId = inputNodeEl ? inputNodeEl.id : null;

            // Create tool nodes in a horizontal chain
            template.tools.forEach((tool, idx) => {
                const x = startX + (idx + 1) * (nodeWidth + gapX);
                const y = startY + gapY;
                const toolConfig = getToolConfigById(tool.id);
                createFlowNode(
                    toolConfig?.name || tool.name,
                    toolConfig?.flowMeta || tool.meta,
                    toolConfig?.type || 'recon',
                    x,
                    y,
                    tool.id,
                    toolConfig?.availableTools || []
                );

                // Find the node we just created (it's the last .flow-node in canvas)
                const allNodes = canvas.querySelectorAll('.flow-node');
                const newNode = allNodes[allNodes.length - 1];
                createdNodeIds.push(newNode.id);
            });

            // Wire connections: input → first tool, then each tool → next tool
            if (inputNodeId && createdNodeIds.length > 0) {
                workflowConnections.push({
                    fromNode: inputNodeId, fromPort: 'out-0',
                    toNode: createdNodeIds[0], toPort: 'in-0'
                });
            }
            for (let i = 0; i < createdNodeIds.length - 1; i++) {
                workflowConnections.push({
                    fromNode: createdNodeIds[i], fromPort: 'out-0',
                    toNode: createdNodeIds[i + 1], toPort: 'in-0'
                });
            }

            drawConnections();
            console.log(`[Flow] Template "${template.label}" loaded with ${template.tools.length} tools.`);
        });
    });
}

// --- WORKFLOW SERIALIZATION LOGIC ---

function serializeWorkflow() {
    const inputNode = document.querySelector('.flow-node[data-node-type="input"]');
    if (!inputNode) {
        alert("Workflow must contain an Input node.");
        return null;
    }

    const targetInput = inputNode.querySelector('input[type="text"]');
    const target = targetInput ? targetInput.value.trim() : "";
    if (!target) {
        alert("Please specify a target in the Input node.");
        return null;
    }

    const steps = [];
    const visited = new Set();
    let queue = [inputNode.id];

    while (queue.length > 0) {
        const currentId = queue.shift();
        if (visited.has(currentId)) continue;
        visited.add(currentId);

        const nodeEl = document.getElementById(currentId);
        if (!nodeEl) continue;

        const nodeType = nodeEl.dataset.nodeType;

        if (nodeType !== 'input' && nodeType !== 'file' && nodeType !== 'new-file') {
            const toolName = nodeEl.dataset.toolId;
            if (toolName) {
                const args = { target: target };

                const incomingConns = workflowConnections.filter(c => c.toNode === currentId);
                incomingConns.forEach(conn => {
                    const sourceNode = document.getElementById(conn.fromNode);
                    if (sourceNode && (sourceNode.dataset.nodeType === 'file' || sourceNode.dataset.nodeType === 'new-file')) {
                        args['wordlist'] = sourceNode.dataset.toolId;
                    }
                });

                // Collect selected sub-tools from the node dropdown
                const checkedSubtools = nodeEl.querySelectorAll('.node-subtool-cb:checked');
                if (checkedSubtools.length > 0) {
                    args['tools'] = Array.from(checkedSubtools).map(cb => cb.value);
                }

                const payloadToggle = nodeEl.querySelector('.node-generate-payload-cb');
                if (payloadToggle && payloadToggle.checked) {
                    args['generate_payload'] = true;
                    const payloadPrompt = nodeEl.querySelector('.node-payload-prompt');
                    const promptText = payloadPrompt ? payloadPrompt.value.trim() : '';
                    if (promptText) args['payload_prompt'] = promptText;
                }

                steps.push({ tool_name: toolName, arguments: args });
            }
        }

        const outgoingConns = workflowConnections.filter(c => c.fromNode === currentId);
        outgoingConns.forEach(conn => {
            if (!visited.has(conn.toNode)) queue.push(conn.toNode);
        });
    }

    if (steps.length === 0) {
        alert("Please connect at least one tool to the Input node.");
        return null;
    }

    return {
        workflow_id: 'wf_' + Date.now(),
        target: target,
        source: 'workflow_builder',
        steps: steps
    };
}

async function executeSerializedWorkflow() {
    const payload = serializeWorkflow();
    if (!payload) return;

    const btn = document.getElementById('flow-start-btn');
    if (btn) { btn.textContent = "Executing..."; btn.disabled = true; }

    try {
        const response = await fetch('/workflow/execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) throw new Error(`HTTP Error: ${response.status}`);
        const data = await response.json();

        if (data.chain_id && typeof window.trackWorkflowChain === 'function') {
            window.trackWorkflowChain(data.workflow_id, data.chain_id);
        } else {
            alert(`Workflow dispatched! ID: ${data.workflow_id}`);
        }

    } catch (error) {
        console.error("Workflow execution failed:", error);
        alert("Failed to execute workflow.");
    } finally {
        if (btn) { btn.textContent = "Start Scan"; btn.disabled = false; }
    }
}

function createFlowNode(name, meta, type, x, y, toolId = '', availableTools = []) {
    const canvas = document.getElementById('flow-canvas');
    const nodeId = 'node-' + Date.now() + Math.floor(Math.random() * 1000);
    const node = document.createElement('div');
    node.className = 'flow-node';
    node.id = nodeId;
    node.dataset.nodeType = type;
    if (toolId) node.dataset.toolId = toolId;
    node.style.left = `${Math.max(0, x)}px`;
    node.style.top = `${Math.max(0, y)}px`;

    // Build sub-tool dropdown HTML (only when >1 available tools)
    let dropdownHtml = '';
    if (availableTools && availableTools.length > 1) {
        const panelId = `panel-${nodeId}`;
        const checkboxes = availableTools.map(t =>
            `<label class="node-subtool-label"><input type="checkbox" class="node-subtool-cb" value="${t.id}" checked> ${t.name}</label>`
        ).join('');
        dropdownHtml = `
            <div class="node-tools-dropdown" onclick="this.nextElementSibling.classList.toggle('open');this.classList.toggle('open')">
                ▾ Tools (${availableTools.length})
            </div>
            <div class="node-tools-panel" id="${panelId}">${checkboxes}</div>
        `;
    }

    const supportsPayloadGeneration = type === 'vuln' && toolId !== 'vuln_scan';
    const payloadControlsHtml = supportsPayloadGeneration ? `
        <div class="node-payload-generation">
            <label class="node-toggle-row">
                <span>Generate Payload</span>
                <input type="checkbox" class="node-generate-payload-cb">
                <span class="node-toggle-slider"></span>
            </label>
            <textarea class="node-payload-prompt" rows="3"
                placeholder="Optional prompt: tailor payloads to the discovered app, parameters, and tech stack."
                disabled></textarea>
        </div>
    ` : '';

    let bodyContent = '';
    if (type === 'input') {
        bodyContent = `
            <div class="node-input-container" style="padding: 10px;">
                <input type="text" placeholder="example.com"
                       style="width: 100%; background: var(--color-background); color: var(--color-text); border: 1px solid var(--color-border); border-radius: 4px; padding: 4px; font-size: 11px;">
            </div>
            <div class="node-port output" data-port-id="out-0" data-port-type="output">
                <span>Target</span>
                <div class="port-circle" onmousedown="startConnection(event, '${nodeId}', 'out-0')"></div>
            </div>
        `;
    } else {
        const hasInput = meta.includes('In:');
        if (hasInput) {
            const parts = meta.split('|');
            const inTextRaw = parts[0] ? parts[0].trim().replace('In: ', '') : '';
            const outTextRaw = parts[1] ? parts[1].trim().replace('Out: ', '') : '';
            inTextRaw.split(',').forEach((inputName, idx) => {
                const portId = `in-${idx}`;
                bodyContent += `<div class="node-port input" data-port-id="${portId}" data-port-type="input">
                    <div class="port-circle" onmouseup="endConnection(event, '${nodeId}', '${portId}')"></div>
                    <span>${inputName.trim()}</span>
                </div>`;
            });
            bodyContent += dropdownHtml;
            bodyContent += payloadControlsHtml;
            if (outTextRaw) {
                bodyContent += `<div class="node-port output" data-port-id="out-0" data-port-type="output">
                    <span>${outTextRaw}</span>
                    <div class="port-circle" onmousedown="startConnection(event, '${nodeId}', 'out-0')"></div>
                </div>`;
            }
        } else {
            const outText = meta.replace('Out: ', '');
            bodyContent += dropdownHtml;
            bodyContent += payloadControlsHtml;
            bodyContent += `<div class="node-port output" data-port-id="out-0" data-port-type="output">
                <span>${outText}</span>
                <div class="port-circle" onmousedown="startConnection(event, '${nodeId}', 'out-0')"></div>
            </div>`;
        }
    }

    node.innerHTML = `
        <div class="flow-node-header"><span>${name}</span><button class="node-remove-btn">x</button></div>
        <div class="flow-node-body">${bodyContent}</div>
    `;
    makeNodeDraggable(node);
    node.querySelector('.node-remove-btn').addEventListener('click', (e) => {
        e.stopPropagation();
        workflowConnections = workflowConnections.filter(c => c.fromNode !== nodeId && c.toNode !== nodeId);
        drawConnections();
        node.remove();
    });

    const payloadToggle = node.querySelector('.node-generate-payload-cb');
    const payloadPrompt = node.querySelector('.node-payload-prompt');
    if (payloadToggle && payloadPrompt) {
        payloadToggle.addEventListener('change', () => {
            payloadPrompt.disabled = !payloadToggle.checked;
            if (payloadToggle.checked) {
                payloadPrompt.focus();
            }
        });
    }

    canvas.appendChild(node);
}

function startConnection(event, nodeId, portId) {
    event.stopPropagation();
    event.preventDefault();
    isConnecting = true;
    const canvas = document.getElementById('flow-canvas');
    const rect = canvas.getBoundingClientRect();
    const startX = event.clientX - rect.left + canvas.scrollLeft;
    const startY = event.clientY - rect.top + canvas.scrollTop;
    tempConnection = { fromNode: nodeId, fromPort: portId, startX, startY, line: document.createElementNS('http://www.w3.org/2000/svg', 'line') };
    tempConnection.line.setAttribute('x1', startX);
    tempConnection.line.setAttribute('y1', startY);
    tempConnection.line.setAttribute('x2', startX);
    tempConnection.line.setAttribute('y2', startY);
    tempConnection.line.setAttribute('stroke', 'var(--color-primary)');
    tempConnection.line.setAttribute('stroke-width', '2');
    tempConnection.line.setAttribute('stroke-dasharray', '5,5');
    document.getElementById('flow-svg-layer').appendChild(tempConnection.line);
}

function updateTempConnection(event, canvas) {
    if (!tempConnection) return;
    const rect = canvas.getBoundingClientRect();
    tempConnection.line.setAttribute('x2', event.clientX - rect.left + canvas.scrollLeft);
    tempConnection.line.setAttribute('y2', event.clientY - rect.top + canvas.scrollTop);
}

window.endConnection = function (event, nodeId, portId) {
    if (!isConnecting || !tempConnection) return;
    event.stopPropagation();
    if (tempConnection.fromNode === nodeId) { cancelConnection(); return; }
    workflowConnections.push({ id: 'conn-' + Date.now(), fromNode: tempConnection.fromNode, fromPort: tempConnection.fromPort, toNode: nodeId, toPort: portId });
    cancelConnection();
    drawConnections();
};

function cancelConnection() {
    isConnecting = false;
    if (tempConnection?.line) tempConnection.line.remove();
    tempConnection = null;
}

function drawConnections() {
    const svg = document.getElementById('flow-svg-layer');
    if (!svg) return;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    workflowConnections.forEach(conn => {
        const fromNode = document.getElementById(conn.fromNode);
        const toNode = document.getElementById(conn.toNode);
        if (!fromNode || !toNode) return;
        const fromPortEl = fromNode.querySelector(`[data-port-id="${conn.fromPort}"] .port-circle`);
        const toPortEl = toNode.querySelector(`[data-port-id="${conn.toPort}"] .port-circle`);
        if (!fromPortEl || !toPortEl) return;
        const canvas = document.getElementById('flow-canvas');
        const cr = canvas.getBoundingClientRect();
        const fR = fromPortEl.getBoundingClientRect();
        const tR = toPortEl.getBoundingClientRect();
        const x1 = fR.left + fR.width / 2 - cr.left + canvas.scrollLeft;
        const y1 = fR.top + fR.height / 2 - cr.top + canvas.scrollTop;
        const x2 = tR.left + tR.width / 2 - cr.left + canvas.scrollLeft;
        const y2 = tR.top + tR.height / 2 - cr.top + canvas.scrollTop;
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        const cp1x = x1 + Math.abs(x2 - x1) / 2;
        const cp2x = x2 - Math.abs(x2 - x1) / 2;
        path.setAttribute('d', `M ${x1} ${y1} C ${cp1x} ${y1}, ${cp2x} ${y2}, ${x2} ${y2}`);
        path.setAttribute('class', 'connection-line');
        path.addEventListener('click', () => {
            if (confirm('Delete connection?')) {
                workflowConnections = workflowConnections.filter(c => c.id !== conn.id);
                drawConnections();
            }
        });
        svg.appendChild(path);
    });
}

function makeNodeDraggable(node) {
    let isDragging = false;
    let sX, sY, iL, iT;
    node.addEventListener('mousedown', (e) => {
        if (e.target.closest('.node-remove-btn') || e.target.closest('.port-circle') || e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'LABEL' || e.target.closest('.node-payload-generation') || e.target.closest('.node-tools-panel') || e.target.closest('.node-tools-dropdown')) return;
        isDragging = true;
        sX = e.clientX; sY = e.clientY;
        iL = parseInt(node.style.left || 0); iT = parseInt(node.style.top || 0);
        node.style.zIndex = 100;
        e.preventDefault();
    });
    window.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        node.style.left = `${iL + (e.clientX - sX)}px`;
        node.style.top = `${iT + (e.clientY - sY)}px`;
        requestAnimationFrame(drawConnections);
    });
    window.addEventListener('mouseup', () => {
        if (isDragging) { isDragging = false; node.style.zIndex = 2; drawConnections(); }
    });
}
