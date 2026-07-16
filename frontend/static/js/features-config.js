console.log('[Features] Loading features-config.js...');

function isOffline() {
    return window.location.protocol === 'file:';
}

// --- CONFIGURATION: API MAPPING ---
// Maps internal tool IDs (from AI or Logic) to Backend API Endpoints
const TOOL_API_MAP = {
    // Asset Discovery
    "root_hunter": "/recon/asset/root-hunter",
    "sub_enumer": "/recon/asset/subdomain-enum",
    "sub_bforcer": "/recon/asset/subdomain-brute",
    "sub_checker": "/recon/asset/subdomain-check",
    "sub_permuter": "/recon/asset/subdomain-permute",

    // Content Discovery
    "tech_detector": "/recon/content/tech-detect",
    "sub_crawler": "/recon/content/crawl",
    "js_analyzer": "/recon/content/js-analyze",
    "link_analyzer": "/recon/content/link-analyze",
    "git_hunter": "/recon/content/git-leaks",
    "param_reflector": "/recon/content/param-reflect",

    // Vulnerability (Placeholders)
    "vuln_scan": "/exploit/vuln-scan",

    // Exploitation
    "ai_hacker": "/exploit/ai-hacker"
};

// --- STRICT EXECUTION ORDER ---
// This defines the dependency chain. Tools will ALWAYS run in this order,
// regardless of how they are selected or how the AI lists them.
const MASTER_EXECUTION_ORDER = [
    "root_hunter",      // 1. Find root domains
    "sub_enumer",       // 2. Find subdomains (passive)
    "sub_bforcer",      // 3. Brute force subdomains
    "sub_permuter",     // 4. Generate permutations (needs output from 2 & 3)
    "sub_checker",      // 5. Verify live hosts (needs output from 2, 3, 4)
    "sub_crawler",      // 6. Crawl live hosts (needs output from 5)
    "js_analyzer",      // 7. Analyze JS files (needs output from 6)
    "link_analyzer",    // 8. Analyze links (needs output from 6 & 7)
    "tech_detector",    // 9. Detect tech stack (runs last to tag everything)
    "ai_hacker",        // 10. AI Hacker (consumes traffic)
    "vuln_scan"         // 11. Exploit
];

/**
 * Sorts an array of tool IDs based on the MASTER_EXECUTION_ORDER.
 */
function sortToolsByDependency(toolsArray) {
    return toolsArray.sort((a, b) => {
        const indexA = MASTER_EXECUTION_ORDER.indexOf(a);
        const indexB = MASTER_EXECUTION_ORDER.indexOf(b);
        // If a tool isn't in the master list, put it at the end
        return (indexA === -1 ? 999 : indexA) - (indexB === -1 ? 999 : indexB);
    });
}

const delay = ms => new Promise(res => setTimeout(res, ms));
