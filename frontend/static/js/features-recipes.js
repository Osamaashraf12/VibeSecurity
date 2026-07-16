console.log('[Features] Loading features-recipes.js...');

// --- CUSTOM RECIPES LOGIC ---
let savedRecipes = [];

async function loadRecipes() {
    if (isOffline()) {
        console.warn('[Offline] loadRecipes skipped.');
        return;
    }
    try {
        const response = await fetch('/recipes/list');
        if (!response.ok) throw new Error('Failed to load recipes');
        savedRecipes = await response.json();

        // Update Dashboard Dropdown
        const select = document.getElementById('dashboard-recipe-select');
        if (select) {
            select.innerHTML = '<option value="">-- Select Saved Recipe --</option>' +
                savedRecipes.map(r => `<option value="${r.recipe_id}">${r.recipe_name}</option>`).join('');
        }

        // Update Manager Modal List
        const listContainer = document.getElementById('recipe-list-container');
        if (listContainer) {
            if (savedRecipes.length === 0) {
                listContainer.innerHTML = '<p style="color:var(--color-text-muted);">No saved recipes found.</p>';
            } else {
                listContainer.innerHTML = savedRecipes.map(r => `
                    <div style="background:var(--color-background); padding: 15px; border-radius: 8px; border: 1px solid var(--color-border); display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <h4 style="margin:0 0 5px 0;">${r.recipe_name}</h4>
                            <p style="margin:0; font-size:0.85rem; color:var(--color-text-muted);">${r.description || 'No description'}</p>
                            <small style="color:var(--color-primary);">${r.steps.length} tool(s)</small>
                        </div>
                        <button class="btn btn--error btn--sm" onclick="deleteRecipe('${r.recipe_id}')">Delete</button>
                    </div>
                `).join('');
            }
        }
    } catch (e) {
        console.error('Error loading recipes:', e);
    }
}

async function saveRecipe(name, description, steps) {
    if (isOffline()) {
        alert("Cannot save recipes in Offline Mode. Please start the VibeSecurity server.");
        return;
    }
    try {
        const response = await fetch('/recipes/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                recipe_name: name,
                description: description,
                steps: steps
            })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Failed to save recipe');
        alert('Recipe saved successfully!');
        loadRecipes();
    } catch (e) {
        alert('Error saving recipe: ' + e.message);
    }
}

window.deleteRecipe = async function (id) {
    if (isOffline()) {
        alert("Cannot delete recipes in Offline Mode.");
        return;
    }
    if (!confirm("Are you sure you want to delete this recipe?")) return;
    try {
        const response = await fetch(`/recipes/${id}`, { method: 'DELETE' });
        if (!response.ok) throw new Error('Failed to delete');
        loadRecipes();
    } catch (e) {
        alert('Error deleting recipe: ' + e.message);
    }
};

function initRecipeUI() {
    loadRecipes();

    // Save from Workflow Builder
    const saveFlowBtn = document.getElementById('flow-save-recipe-btn');
    if (saveFlowBtn) {
        saveFlowBtn.addEventListener('click', () => {
            const payload = serializeWorkflow();
            if (!payload || !payload.steps || payload.steps.length === 0) return;
            const name = prompt("Enter a name for this Custom Recipe:");
            if (!name) return;
            const desc = prompt("Enter an optional description:");
            saveRecipe(name, desc || "", payload.steps);
        });
    }

    // Save from Manual Modules (Checkboxes)
    document.querySelectorAll('.save-recipe-manual').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const view = btn.closest('.view');
            const checkedBoxes = view.querySelectorAll('.submodule-checkbox input:checked');
            if (checkedBoxes.length === 0) {
                alert("Please select at least one module to save as a recipe.");
                return;
            }
            let selectedTools = Array.from(checkedBoxes).map(cb => cb.value);
            selectedTools = sortToolsByDependency(selectedTools);
            const targetInput = view.querySelector('.config-form input[type="text"]');
            const target = targetInput ? targetInput.value.trim() : "";

            const steps = selectedTools.map(tool => {
                const mappedKey = Object.keys(TOOL_API_MAP).find(k => tool.includes(k)) || tool;

                const container = view.querySelector(`input[id="${tool}"]`).closest('.submodule-container');
                const subToolsChecked = container ? container.querySelectorAll(`input[data-subtool]:checked`) : [];
                const selectedSubTools = Array.from(subToolsChecked).map(cb => cb.value);

                let args = target ? { target: target } : {};
                if (selectedSubTools.length > 0) args.tools = selectedSubTools;

                return {
                    tool_name: mappedKey,
                    arguments: args
                };
            });

            const name = prompt("Enter a name for this Custom Recipe:");
            if (!name) return;
            const desc = prompt("Enter an optional description:");
            saveRecipe(name, desc || "", steps);
        });
    });

    // Run from Dashboard
    const runBtn = document.getElementById('run-recipe-btn');
    const select = document.getElementById('dashboard-recipe-select');
    const targetInput = document.getElementById('full-scan-target');
    if (runBtn && select && targetInput) {
        runBtn.addEventListener('click', async () => {
            const recipeId = select.value;
            const target = targetInput.value.trim();
            if (!recipeId) {
                alert("Please select a recipe from the dropdown.");
                return;
            }
            if (!target) {
                alert("Please enter a target.");
                return;
            }

            runBtn.disabled = true;
            runBtn.textContent = "Dispatching...";

            try {
                const response = await fetch(`/recipes/execute/${recipeId}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ target: target })
                });
                const data = await response.json();
                if (!response.ok) throw new Error(data.detail || 'Execution failed');

                alert(`Recipe dispatched successfully!\nWorkflow ID: ${data.workflow_id}`);

                // Show in Activity/Results
                const resultContainer = document.querySelector('#view-dashboard .scan-results');
                if (resultContainer) {
                    resultContainer.classList.remove('hidden');
                    resultContainer.querySelector('.results-grid').innerHTML = `
                        <div class="result-card" style="grid-column: span 3; border-left: 4px solid var(--color-primary);">
                            <div class="card-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                                <h4 style="margin: 0;">Recipe Dispatched</h4>
                                <span style="font-size: 0.8rem; color: #888;">Workflow ID: ${data.workflow_id}</span>
                            </div>
                            <p>Target: <strong>${target}</strong></p>
                            <p>${data.message}</p>
                        </div>
                    `;
                }
            } catch (e) {
                alert("Error executing recipe: " + e.message);
            } finally {
                runBtn.disabled = false;
                runBtn.textContent = "Run Recipe";
            }
        });
    }

    // Modal Manager
    const manageBtn = document.getElementById('manage-recipes-btn');
    const modal = document.getElementById('recipe-manager-modal');
    const closeBtn = document.getElementById('close-recipe-modal');

    if (manageBtn && modal && closeBtn) {
        manageBtn.addEventListener('click', () => {
            loadRecipes();
            modal.style.display = 'flex';
        });
        closeBtn.addEventListener('click', () => {
            modal.style.display = 'none';
        });
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.style.display = 'none';
        });
    }
}
