function initApp() {
    console.log('[App] Initializing VibeSecurity...');
    
    try {
        try {
            if (typeof renderAllTools === 'function') renderAllTools();
        } catch (e) {
            console.warn('[App] renderAllTools failed (likely config not ready):', e);
        }

        try {
            if (typeof animateGridItems === 'function') animateGridItems();
        } catch (e) {
            console.warn('[App] animateGridItems failed:', e);
        }
        
        const particlesContainer = document.querySelector('.particles');
        if (particlesContainer && typeof createParticles === 'function') {
            try {
                createParticles(particlesContainer);
            } catch (e) {
                console.warn('[App] createParticles failed:', e);
            }
        }

        // Offline Mode Indicator
        try {
            if (typeof isOffline === 'function' && isOffline()) {
                const brand = document.querySelector('.nav__brand');
                if (brand) {
                    const badge = document.createElement('span');
                    badge.id = 'offline-badge';
                    badge.textContent = 'OFFLINE MODE';
                    badge.style.cssText = 'margin-left: 12px; padding: 2px 8px; background: #ffa502; color: #0a0e1a; border-radius: 4px; font-size: 0.65rem; font-weight: 800; border: 1px solid rgba(0,0,0,0.1);';
                    brand.appendChild(badge);
                }
            }
        } catch (e) {
            console.warn('[App] Offline indicator failed:', e);
        }
        
        initNavigation();
        initChat();
        initScan();
        initModuleButtons();
        initSubmoduleCheckboxes(); 
        initFlowBuilder(); 
        initTrafficAnalyzer();
        initWorkflowStatusTracking();
        initHunterAgent();
        
        if (typeof initRecipeUI === 'function') {
            try {
                initRecipeUI();
            } catch (e) {
                console.warn('[App] initRecipeUI failed:', e);
            }
        }
        
        // Final sync for initial view
        const activeView = document.querySelector('.view.active');
        if (activeView) {
            const viewId = activeView.id.replace('view-', '');
            console.log(`[App] Initial view detected: ${viewId}`);
            syncNavButtons(viewId);
        }

        console.log('[App] Initialization complete');
    } catch (err) {
        console.error('[App] Initialization failed:', err);
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initApp);
} else {
    initApp();
}

window.addEventListener('load', () => {
    console.log('[App] Window loaded');
    const title = document.querySelector('.hero__title');
    if (title && typeof typeWriter === 'function') {
        setTimeout(() => typeWriter(title, title.textContent, 50), 500);
    }
    window.scrollTo(0, 0);
});

function syncNavButtons(viewId) {
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.target === viewId) btn.classList.add('active');
    });
}

// --- Navigation Functions ---
function initNavigation() {
    console.log('[Navigation] Initializing listeners...');
    const navButtons = document.querySelectorAll('.nav-btn');
    console.log(`[Navigation] Found ${navButtons.length} navigation buttons`);
    
    navButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            console.log(`[Navigation] Button clicked: ${btn.dataset.target || btn.innerText}`);
            if(!btn.classList.contains('dropdown-trigger')) {
                e.preventDefault();
                const targetId = btn.dataset.target;
                if (targetId) {
                    switchView(targetId);
                    
                    // Hook: If Reporting view is clicked, trigger re-render
                    if (targetId === 'reporting') {
                        if (typeof initReporting === 'function') initReporting();
                    }
                } else {
                    console.warn('[Navigation] Button has no data-target');
                }
            } else {
                console.log('[Navigation] Dropdown trigger clicked (skipping switchView)');
            }
        });
    });
    
    const heroStartBtn = document.getElementById("startScanningBtn");
    if(heroStartBtn) {
        heroStartBtn.addEventListener("click", function () {
            console.log('[Navigation] Hero Start Button clicked');
            document.getElementById("scrolling-to-scan").scrollIntoView({ behavior: "smooth" });
        });
    }
    
    const cardNavIds = ["nav-recon", "nav-vuln", "nav-AI"];
    cardNavIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener("click", () => {
                const targetMap = { "nav-recon": "recon-asset", "nav-vuln": "vulnerability", "nav-AI": "ai-assistant" };
                console.log(`[Navigation] Card button clicked: ${id}`);
                switchView(targetMap[id]);
            });
        }
    });
}

function switchView(viewId) {
    console.log(`[Navigation] Switching to view: ${viewId}`);
    
    // Hide all views explicitly
    const allViews = document.querySelectorAll('.view');
    console.log(`[Navigation] Found ${allViews.length} views`);
    
    allViews.forEach(view => {
        view.classList.remove('active');
        view.style.setProperty('display', 'none', 'important');
    });
    
    // Show the target view
    const targetView = document.getElementById(`view-${viewId}`);
    if (targetView) {
        console.log(`[Navigation] Showing target view: view-${viewId}`);
        targetView.classList.add('active');
        targetView.style.setProperty('display', 'block', 'important');
    } else {
        console.error(`[Navigation] Target view not found: view-${viewId}`);
    }
    
    // Sync navigation buttons
    const navButtons = document.querySelectorAll('.nav-btn');
    navButtons.forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.target === viewId) btn.classList.add('active');
    });
    
    window.scrollTo(0, 0);
}

// --- Workflow Integration & State Tracking ---
function initWorkflowStatusTracking() {
    window.trackWorkflowChain = async function(workflowId, chainId) {
        console.log(`[Workflow] Tracking chain for ${workflowId} via tail task: ${chainId}`);
        const statusContainer = document.getElementById('workflow-status-container') || createStatusContainer();
        
        updateWorkflowUI(statusContainer, workflowId, `Workflow is Running...`);
        
        const pollInterval = 3000;
        
        while (true) {
            try {
                const res = await fetch(`/status/chain/${chainId}`);
                if (!res.ok) throw new Error(`Polling failed: ${res.status}`);
                
                const statusData = await res.json();
                
                if (statusData.state === 'SUCCESS') {
                    updateWorkflowUI(statusContainer, workflowId, "Workflow Complete!");
                    setTimeout(() => statusContainer.style.display = 'none', 5000);
                    return 'SUCCESS';
                } else if (statusData.state === 'FAILURE') {
                    updateWorkflowUI(statusContainer, workflowId, `Workflow Failed! Chain Stopped.`, true);
                    return 'FAILURE';
                }
                
                await new Promise(resolve => setTimeout(resolve, pollInterval));
            } catch (err) {
                console.error(`[Chain Polling Error]`, err);
                updateWorkflowUI(statusContainer, workflowId, `Error polling status!`, true);
                return 'ERROR';
            }
        }
    };
}

function createStatusContainer() {
    const container = document.createElement('div');
    container.id = 'workflow-status-container';
    container.style.position = 'fixed';
    container.style.bottom = '20px';
    container.style.right = '20px';
    container.style.padding = '15px';
    container.style.background = '#1e1e1e';
    container.style.border = '1px solid #00ff9d';
    container.style.borderRadius = '8px';
    container.style.zIndex = '9999';
    container.style.color = '#fff';
    document.body.appendChild(container);
    return container;
}

function updateWorkflowUI(container, workflowId, message, isError = false) {
    container.style.display = 'block';
    container.innerHTML = `
        <h4 style="margin: 0 0 5px 0; color: ${isError ? '#ff4d4d' : '#00ff9d'};">Workflow: ${workflowId}</h4>
        <p style="margin: 0; font-size: 0.9rem;">Status: ${message}</p>
    `;
}
