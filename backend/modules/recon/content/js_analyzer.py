import sys
import subprocess
import os
import json
import re
import hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, urljoin
from collections import Counter

import logging
logger = logging.getLogger(__name__)

try:
    project_root = Path(__file__).resolve().parents[4]
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))
except IndexError:
    pass

from backend.core.schemas import ToolContext
from backend.core.loader import vibe_tool

NOISE_DOMAINS = [
    "cdnjs.cloudflare.com", "cdn.jsdelivr.net", "unpkg.com",
    "ajax.googleapis.com", "code.jquery.com", "stackpath.bootstrapcdn.com",
    "cdn.bootcdn.net", "fonts.googleapis.com", "fonts.gstatic.com",
    "use.fontawesome.com", "maxcdn.bootstrapcdn.com",
]

NOISE_FILENAMES = [
    r"^jquery[\-\.]", r"^bootstrap[\-\.]", r"^moment[\-\.]",
    r"^lodash[\-\.]", r"^underscore[\-\.]", r"^backbone[\-\.]",
    r"^popper[\-\.]", r"^chart[\-\.]", r"^socket\.io[\-\.]",
    r"^gtag\.js$", r"^fbevents\.js$",
]

@vibe_tool(submodule="js_analyzer", tool_id="trufflehog", tool_name="Trufflehog & JSLuice", category="content", ext="json")
def run(ctx: ToolContext):
    crawler_output_base = ctx.resolve_input_path("sub_crawler", "content", "json")
    crawler_links_file = crawler_output_base.parent / f"{ctx.clean_target}_crawled_links.txt"
    
    output_dir = ctx.scan_results_dir / "content" / f"{ctx.clean_target}_js_analysis"
    
    input_source = None
    if crawler_links_file.exists() and crawler_links_file.stat().st_size > 0:
        input_source = str(crawler_links_file)
    else:
        print("❌ Error: No crawler links found for JS Analysis.")
        return

    run_analysis(ctx, input_source, str(output_dir))

def get_primary_domain(file_path: Path):
    try:
        # FIX: Added encoding="utf-8" and errors="replace"
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("http"):
                    return "{0.scheme}://{0.netloc}".format(urlparse(line.strip()))
    except Exception:
        return None
    return None

def is_noisy(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.netloc in NOISE_DOMAINS: return True
    filename = Path(parsed.path).name.lower()
    for pattern in NOISE_FILENAMES:
        if re.search(pattern, filename): return True
    return False

def extract_js_urls(input_file: Path, output_file: Path, base_domain: str):
    js_urls = set()
    # FIX: Added encoding="utf-8" and errors="replace"
    with open(input_file, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            url = line.strip()
            if url.endswith(".js") and not is_noisy(url):
                js_urls.add(url)
    
    if not js_urls: return None
    
    # FIX: Added encoding="utf-8"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(js_urls))
        
    return list(js_urls)

def download_js(url: str, save_dir: Path, ctx: ToolContext):
    filename = Path(urlparse(url).path).name
    if not filename: filename = "index.js"
    
    hash_suffix = hashlib.md5(url.encode()).hexdigest()[:8]
    safe_name = f"{filename}_{hash_suffix}.js"
    save_path = save_dir / safe_name
    
    # 1. Thread-safety: Check if another thread or previous scan already downloaded it
    if save_path.exists() and save_path.stat().st_size > 0:
        return save_path
        
    # 2. Use curl to download directly to the final file path
    # -s (silent), -L (follow redirects), -k (ignore SSL cert warnings)
    sh_cmd = f"curl -s -L -k '{url}' -o '{save_path}'"
    ctx.run_command(["sh", "-c", sh_cmd], check=False)
    
    # 3. Verify it worked
    if save_path.exists() and save_path.stat().st_size > 0:
        return save_path
    return None

def run_jsluice(file_path: Path, ctx: ToolContext):
    urls = []
    secrets = []
    
    cmd_urls = ["jsluice", "urls", str(file_path), "-S"]
    res_urls = ctx.run_command(cmd_urls, check=False)
    if res_urls.stdout:
        for line in res_urls.stdout.splitlines():
            try: urls.append(json.loads(line))
            except: pass
            
    cmd_secrets = ["jsluice", "secrets", str(file_path)]
    res_secrets = ctx.run_command(cmd_secrets, check=False)
    if res_secrets.stdout:
        for line in res_secrets.stdout.splitlines():
            try: secrets.append(json.loads(line))
            except: pass
            
    return urls, secrets

def run_trufflehog(target_dir: Path, output_file: Path, ctx: ToolContext):
    print("[*] Running Trufflehog (Entropy Analysis)...")
    sh_cmd = f"trufflehog filesystem {target_dir} --json > {output_file}"
    ctx.run_command(["sh", "-c", sh_cmd], check=False)

def aggregate_endpoints(jsluice_urls, base_domain, output_dir):
    unique_endpoints = set()
    for item in jsluice_urls:
        url_candidate = item.get("url", "")
        if url_candidate and len(url_candidate) > 1:
            if not url_candidate.startswith("http"):
                if url_candidate.startswith("//"):
                    url_candidate = "https:" + url_candidate
                elif base_domain:
                    url_candidate = urljoin(base_domain, url_candidate)
            unique_endpoints.add(url_candidate)

    clean_urls_path = Path(output_dir) / "all_endpoints.txt"
    # FIX: Added encoding="utf-8"
    with open(clean_urls_path, "w", encoding="utf-8") as f: f.write('\n'.join(sorted(unique_endpoints)) + '\n')
    print(f"[*] Total unique JS endpoints discovered: {len(unique_endpoints)}")
    return clean_urls_path

def run_analysis(ctx: ToolContext, input_file_path, output_dir_path):
    input_source = Path(input_file_path)
    output_dir = Path(output_dir_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    base_domain = get_primary_domain(input_source)
    if base_domain: print(f"[*] Detected Base Domain: {base_domain}")
    
    js_urls_file = output_dir / "js_target_urls.txt"
    print(f"[*] Extracting JS targets from {input_source.name}...")
    js_urls = extract_js_urls(input_source, js_urls_file, base_domain)

    if not js_urls:
        print("    ⚠️ No JS URLs found to analyze.")
        # FIX: Added encoding="utf-8"
        with open(output_dir / "all_endpoints.txt", "w", encoding="utf-8") as f: f.write("")
        return

    # Phase 2: Local File Analysis
    js_storage_dir = output_dir / "downloaded_js"
    js_storage_dir.mkdir(parents=True, exist_ok=True)
    
    limit_urls = js_urls[:30] # Hard limit for performance
    print(f"[*] Queueing {len(limit_urls)} JS URLs for download...")
    
    local_files = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(download_js, url, js_storage_dir, ctx) for url in limit_urls]
        for f in futures:
            res = f.result()
            if res: local_files.append(res)
            
    print(f"[*] Running JSLuice (Static Analysis)...")
    all_js_urls = []
    all_js_secrets = []
    
    for local_file in local_files:
        urls, secrets = run_jsluice(local_file, ctx)
        all_js_urls.extend(urls)
        all_js_secrets.extend(secrets)
        
    truffle_output = output_dir / "trufflehog_secrets.json"
    run_trufflehog(js_storage_dir, truffle_output, ctx)
    
    print("[*] Aggregating extracted endpoints and secrets...")
    aggregate_endpoints(all_js_urls, base_domain, output_dir)
    
    if all_js_secrets:
        secrets_out = output_dir / "jsluice_secrets.json"
        # FIX: Added encoding="utf-8"
        with open(secrets_out, "w", encoding="utf-8") as f:
            json.dump(all_js_secrets, f, indent=2)

    print(f"✅ JS Analysis Complete. Data extracted to {output_dir}")