from dataclasses import dataclass
from typing import List, Optional

@dataclass
class ToolMetadata:
    key: str
    name: str
    module_path: str   # Python import path (e.g., 'backend.modules...')
    entry_point: str   # Function name to call (e.g., 'run')
    category: str      # 'asset', 'content', 'exploitation'
    output_ext: str    # 'txt' or 'json'
    available_tools: Optional[dict] = None # Dict mapping tool_id to Tool Display Name
    requires: Optional[List[str]] = None  # List of tool_keys this tool depends on
    description: str = ""

# --- THE MASTER REGISTRY ---
TOOL_REGISTRY = {
    # === ASSET DISCOVERY ===
    "sub_enumer": ToolMetadata(
        key="sub_enumer",
        name="Passive Enumeration",
        module_path="backend.modules.recon.asset.sub_enumer",
        entry_point="run",
        category="asset",
        output_ext="txt",
        # CRITICAL CHANGE: Updated to only expose Subfinder and Findomain
        available_tools={"subfinder": "Subfinder", "findomain": "Findomain"},
        description="Passive subdomain discovery."
    ),
    "sub_bforcer": ToolMetadata(
        key="sub_bforcer",
        name="Active Bruteforcing",
        module_path="backend.modules.recon.asset.sub_bforcer",
        entry_point="run",
        category="asset",
        output_ext="txt",
        available_tools={"puredns": "PureDNS", "ffuf": "ffuf", "gobuster": "gobuster"},
        description="Active subdomain bruteforcing."
    ),
    "sub_permuter": ToolMetadata(
        key="sub_permuter",
        name="Subdomain Permutation",
        module_path="backend.modules.recon.asset.sub_permuter",
        entry_point="run",
        category="asset",
        output_ext="txt",
        available_tools={"alterx": "AlterX"},
        description="Generating subdomain permutations."
    ),
    "sub_checker": ToolMetadata(
        key="sub_checker",
        name="Live Host Verification",
        module_path="backend.modules.recon.asset.sub_checker",
        entry_point="run",
        category="asset",
        output_ext="json",
        available_tools={"dnsx_httpx": "DNSX/HTTPX"},
        requires=["sub_enumer", "sub_bforcer", "sub_permuter"], # Aggregates all
        description="Verifies DNS and HTTP status of discovered assets."
    ),
    "sub_Vhost": ToolMetadata(
        key="sub_Vhost",
        name="Virtual Host Enumeration",
        module_path="backend.modules.recon.asset.vhost_enumer_wrapper",
        entry_point="run",
        category="asset",
        output_ext="txt",
        available_tools={"ffuf_vhost": "ffuf VHost"},
        requires=["sub_checker"],
        description="Virtual host enumeration using ffuf to discover internal or hidden sites."
    ),

    # === CONTENT DISCOVERY ===
    "sub_crawler": ToolMetadata(
        key="sub_crawler",
        name="Spidering",
        module_path="backend.modules.recon.content.sub_crawler",
        entry_point="run",
        category="content",
        output_ext="json",
        available_tools={"katana": "Katana", "gau": "GAU"},
        requires=["sub_checker"], # Needs live hosts
        description="Active crawling for web structure."
    ),
    "js_analyzer": ToolMetadata(
        key="js_analyzer",
        name="JS Secret Scanner",
        module_path="backend.modules.recon.content.js_analyzer",
        entry_point="run",
        category="content",
        output_ext="json", 
        available_tools={"trufflehog": "Trufflehog", "trufflehog3": "Trufflehog3"},
        requires=["sub_crawler"], # Needs JS URLs
        description="Static analysis of JavaScript files for secrets."
    ),
    "link_analyzer": ToolMetadata(
        key="link_analyzer",
        name="Pattern Matcher",
        module_path="backend.modules.recon.content.link_analyzer",
        entry_point="run",
        category="content",
        output_ext="txt", 
        available_tools={"gf": "GF Pattern Matcher"},
        requires=["sub_crawler", "js_analyzer"],
        description="GF pattern matching and deduplication."
    ),
    "tech_detector": ToolMetadata(
        key="tech_detector",
        name="Tech Stack Fingerprinter",
        module_path="backend.modules.recon.content.tech_detector",
        entry_point="run",
        category="content",
        output_ext="json",
        available_tools={"httpx": "HTTPX"},
        requires=["sub_crawler"], 
        description="Identifies technologies (CMS, Frameworks) using HTTPX."
    ),
    # === AI ANALYSIS ===
    "ai_hacker": ToolMetadata(
        key="ai_hacker",
        name="AI Hacker (HTTP Request Scanning)",
        module_path="backend.modules.exploitation.ai_hacker", 
        entry_point="run",
        category="exploitation",
        output_ext="json",
        available_tools={"openrouter": "OpenRouter GPT-OSS"},
        requires=["sub_crawler"],
        description="Deep HTTP traffic analysis via OpenRouter for business logic flaws, IDOR, and injection vulnerabilities."
    ),
    # === VULNERABILITY SCANNING (Nuclei) ===
    "vuln_scan": ToolMetadata(
        key="vuln_scan",
        name="Vulnerability Scanner (Nuclei)",
        module_path="backend.modules.exploitation.nuclei",
        entry_point="run",
        category="exploitation",
        output_ext="json",
        available_tools={},  # Populated dynamically by loader from @vibe_tool decorators
        requires=["tech_detector", "sub_crawler", "sub_enumer"],
        description="Nuclei-powered vulnerability scanning suite: CVE, tech, panels, takeover, misconfigs, default creds, cloud exposure."
    ),
    "active_verifiers": ToolMetadata(
        key="active_verifiers",
        name="Active Vulnerability Verifiers",
        module_path="backend.modules.exploitation.active_verifiers",
        entry_point="run",
        category="exploitation",
        output_ext="json",
        available_tools={},  # Populated dynamically by loader
        requires=["link_analyzer", "tech_detector", "sub_crawler"],
        description="Active payload injection verifiers for XSS, SQLi, SSTI, LFI, SSRF, etc."
    ),
    "logic_probers": ToolMetadata(
        key="logic_probers",
        name="Logic Probers",
        module_path="backend.modules.exploitation.logic_probers",
        entry_point="run",
        category="exploitation",
        output_ext="json",
        available_tools={},  # Populated dynamically by loader
        requires=["sub_crawler"],
        description="Advanced logic vulnerability scanners: Rate limiting, IDOR, Authentication Bypass, and Parameter Pollution."
    ),
}

def validate_recipe_steps(steps: List[dict]) -> bool:
    """
    Strictly checks if a list of steps is valid against the registry.
    """
    if not steps:
        raise ValueError("Recipe must contain at least one step.")
    
    for step in steps:
        tool_name = step.get("tool_name")
        if not tool_name:
            raise ValueError("Every step must have a 'tool_name'.")
        
        if tool_name not in TOOL_REGISTRY:
            raise ValueError(f"Invalid tool '{tool_name}' in custom recipe. Strict registry validation failed.")
    
    return True