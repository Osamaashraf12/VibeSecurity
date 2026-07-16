console.log('[Features] Loading features-ui.js...');

// --- DYNAMIC CONTENT GENERATION ---

/**
 * Renders all tool-related UI components based on global configurations.
 */
function renderAllTools() {
    if (TOOLS_CONFIG) {
        renderCheckboxes('asset-tools-container', TOOLS_CONFIG.assetDiscovery);
        renderCheckboxes('content-tools-container', TOOLS_CONFIG.contentDiscovery);
        renderCheckboxes('vuln-tools-container', TOOLS_CONFIG.vulnerabilityScanning);
        renderFlowSidebar('flow-tools-container');
    }
    if (typeof FILES_CONFIG !== 'undefined' && FILES_CONFIG !== null) {
        renderFlowFiles('flow-files-container');
    }
}

function renderCheckboxes(containerId, tools) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = tools.map(tool => {
        const availableToolsHtml = tool.availableTools ? tool.availableTools.map((t, index) => `
            <label class="sub-tool-checkbox" style="display: block; margin-left: 36px; font-size: 0.85rem; margin-top: 6px; color: var(--color-text-muted); cursor: pointer;">
                <input type="checkbox" data-subtool="${t.id}" value="${t.id}" ${index === 0 ? 'checked' : ''} style="margin-right: 8px; transform: scale(0.9); accent-color: var(--color-primary);">
                ${t.name}
            </label>
        `).join('') : '';

        return `
        <div class="submodule-container" style="margin-bottom: 20px;">
            <div class="submodule-checkbox" style="margin-bottom: 8px;">
                <input type="checkbox" id="${tool.id}" value="${tool.id}">
                <span class="checkmark"></span>
                <div class="submodule-info">
                    <h4>${tool.name}</h4>
                    <p>${tool.description}</p>
                </div>
            </div>
            <div class="available-tools">
                ${availableToolsHtml}
            </div>
        </div>
        `;
    }).join('');
}

function renderFlowSidebar(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    if (!TOOLS_CONFIG) return;
    const allCategories = [
        ...TOOLS_CONFIG.inputs,
        ...TOOLS_CONFIG.assetDiscovery,
        ...TOOLS_CONFIG.contentDiscovery,
        ...TOOLS_CONFIG.vulnerabilityScanning
    ];
    let html = '';
    allCategories.forEach(tool => {
        const availTools = tool.availableTools && tool.availableTools.length > 1
            ? encodeURIComponent(JSON.stringify(tool.availableTools))
            : '';
        html += `
            <div class="tool-card" draggable="true"
                 data-type="tool"
                 data-tool-id="${tool.id}"
                 data-tool-type="${tool.type}"
                 data-flow-meta="${tool.flowMeta}"
                 data-available-tools="${availTools}">
                <span class="tool-name">${tool.name}</span>
                <span class="tool-meta">${tool.description}</span>
            </div>
        `;
    });
    container.innerHTML = html;
}

function renderFlowFiles(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    let html = '';
    FILES_CONFIG.forEach(file => {
        html += `
            <div class="tool-card file-card" draggable="true"
                 data-type="file"
                 data-tool-id="${file.id}"
                 data-tool-type="file"
                 data-flow-meta="Out: Wordlist">
                <span class="tool-name">${file.name}</span>
                <span class="tool-meta">${file.description}</span>
            </div>
        `;
    });
    container.innerHTML = html;
}

/**
 * Wires up submodule checkbox click-to-toggle behavior.
 */
function initSubmoduleCheckboxes() {
    document.body.addEventListener('click', function (event) {
        const div = event.target.closest('.submodule-checkbox');
        if (div) {
            const checkbox = div.querySelector('input[type="checkbox"]');
            if (event.target !== checkbox && checkbox) {
                checkbox.checked = !checkbox.checked;
            }
        }

        const subLabel = event.target.closest('.sub-tool-checkbox');
        if (subLabel) {
            const checkbox = subLabel.querySelector('input[type="checkbox"]');
            if (event.target !== checkbox && checkbox) {
                checkbox.checked = !checkbox.checked;
            }
        }
    });
}

function initModuleButtons() { }
