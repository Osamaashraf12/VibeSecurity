// --- CONFIGURATION (Centralized Tool Definitions) ---
// NOTE: IDs must match snake_case keys in backend/orchestration.py
let TOOLS_CONFIG = null;

async function fetchToolsConfig() {
    try {
        const response = await fetch('/api/config/tools');
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        TOOLS_CONFIG = await response.json();
        console.log("Loaded dynamic tools config:", TOOLS_CONFIG);
        if (typeof renderAllTools === 'function') {
            renderAllTools();
        }
    } catch (e) {
        console.error("Failed to load tools config", e);
    }
}
fetchToolsConfig();

const FILES_CONFIG = [
  { id: "n0kovo_subdomains_huge.txt", name: "n0kovo Subdomains Huge", description: "~3M from global TLS certs", scanMode: "massive", type: "file" },
  { id: "all.txt", name: "jhaddix all.txt", description: "~86K curated subdomains", scanMode: "normal", type: "file" },
  { id: "subdomains-top1million-110000.txt", name: "SecLists Top 110K", description: "Top 110K real subdomains", scanMode: "normal", type: "file" },
  { id: "subdomains-top1million-5000.txt", name: "SecLists Top 5K", description: "Top 5K common subdomains", scanMode: "light", type: "file" },
  { id: "deepmagic-prefixes-top500.txt", name: "deepmagic Top 500 Prefixes", description: "Top 500 prefixes", scanMode: "light", type: "file" }
];

// --- SESSION STATE ---
let SESSION_SCAN_DATA = {
    isActive: false,
    findings: [] 
};

// --- MOCK DATA FACTORY (Visual Fallback) ---
const MOCK_VULN_DB = [
    {
        title: "SQL Injection in Login Parameter",
        severity: "Critical",
        cvss: 9.8,
        category: "Injection",
        location: "/api/login",
        description: "The 'username' parameter in the login API is vulnerable to SQL injection.",
        remediation: "Use parameterized queries (Prepared Statements)."
    }
];

// --- HELPER FUNCTIONS ---
function animateGridItems() {
    const items = document.querySelectorAll('.grid-item');
    if (items.length === 0) return;
    setInterval(() => {
        items.forEach(item => item.classList.remove('active'));
        const count = Math.floor(Math.random() * 2) + 2;
        const selected = [];
        while (selected.length < count) {
            const index = Math.floor(Math.random() * items.length);
            if (!selected.includes(index)) selected.push(index);
        }
        selected.forEach(i => items[i].classList.add('active'));
    }, 3000);
}

function typeWriter(el, text, speed) {
    el.textContent = '';
    [...text].forEach((ch, i) => setTimeout(() => el.textContent += ch, i * speed));
}

function createParticles(container) {
    if (!container) return;
    for (let i = 0; i < 100; i++) {
        const p = document.createElement('div');
        p.className = 'particle';
        p.style.cssText = `position:fixed;width:2px;height:2px;background:rgba(0,212,255,.5);border-radius:50%;pointer-events:none;left:${Math.random() * 100}%;top:${Math.random() * 100}%;animation:float ${Math.random() * 3 + 2}s ease-in-out infinite;`;
        container.appendChild(p);
    }
}
if (!document.querySelector('style[data-particles]')) {
    const style = document.createElement('style');
    style.setAttribute('data-particles', 'true');
    style.textContent = `@keyframes float{0%,100%{transform:translateY(0);opacity:.5}50%{transform:translateY(-20px);opacity:1}}`;
    document.head.appendChild(style);
}