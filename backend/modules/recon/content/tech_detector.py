import sys
import json
import os
from pathlib import Path

try:
    project_root = Path(__file__).resolve().parents[4]
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))
except IndexError:
    pass

from backend.core.schemas import ToolContext
from backend.core.loader import vibe_tool

HIGH_VALUE_TAGS = {
    "Laravel", "Django", "Ruby on Rails", "Spring Boot", "Express", "NestJS", 
    "React", "Vue.js", "Angular", "Svelte", 
    "WordPress", "Magento", "Shopify", "Drupal", "Joomla",
    "Docker", "Kubernetes", "AWS", "Azure", "Cloudflare"
}

@vibe_tool(submodule="tech_detector", tool_id="httpx", tool_name="Tech Stack Fingerprinter", category="content", ext="json")
def run(ctx: ToolContext):
    output_file = ctx.get_output_path("httpx", "content", "json")
    
    merged_list = ctx.scan_results_dir / "content" / f"{ctx.clean_target}_patterns" / "full_merged_list.txt"
    crawler_output_base = ctx.resolve_input_path("sub_crawler", "content", "json")
    crawler_links = crawler_output_base.parent / f"{ctx.clean_target}_crawled_links.txt"
    
    input_source = None
    if merged_list.exists() and merged_list.stat().st_size > 0:
        input_source = str(merged_list)
    elif crawler_links.exists() and crawler_links.stat().st_size > 0:
        input_source = str(crawler_links)
        
    if not input_source:
        print("❌ Error: No target list found for Tech Detection.")
        return

    run_tech_detector(ctx, input_source, str(output_file))

def parse_httpx_json(temp_output: Path, final_output_file: str):
    final_results = []
    
    if temp_output.exists() and temp_output.stat().st_size > 0:
        print("[*] Processing technology fingerprints...")
        # FIX: Added encoding="utf-8" and errors="replace"
        with open(temp_output, 'r', encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.strip(): continue
                try:
                    raw = json.loads(line)
                    url = raw.get("url")
                    if not url: continue

                    tech_data = raw.get("tech-and-stack", [])
                    technologies = []
                    
                    if isinstance(tech_data, list):
                        technologies = list(set([t.strip() for t in tech_data if t]))
                    elif isinstance(tech_data, dict):
                        for k, v in tech_data.items():
                            technologies.append(k)
                            if isinstance(v, list): technologies.extend(v)
                            
                    technologies = list(set(technologies))
                    
                    notes = []
                    high_value = [t for t in technologies if any(h in t for h in HIGH_VALUE_TAGS)]
                    if high_value:
                        notes.append(f"High-value stack detected: {', '.join(high_value)}")
                    
                    if "php" in url.lower() and "PHP" in technologies:
                        notes.append("PHP Backend detected - Check for potential phpinfo()")
                
                    final_results.append({
                        "url": url,
                        "status": raw.get("status_code", 0),
                        "title": raw.get("title", ""),
                        "technologies": technologies,
                        "server": raw.get("webserver") or raw.get("header", {}).get("server", "N/A"),
                        "notes": notes
                    })
                except json.JSONDecodeError: continue

    # FIX: Added encoding="utf-8"
    with open(final_output_file, 'w', encoding="utf-8") as f:
        json.dump(final_results, f, indent=2)
    print(f"✅ Tech Detection Complete. Found {len(final_results)} fingerprinted endpoints.")

def run_tech_detector(ctx: ToolContext, input_file: str, output_file: str):
    input_path = Path(input_file)
    output_path = Path(output_file)
    temp_output = output_path.parent / f"temp_httpx_{output_path.stem}.json"
    
    if not input_path.exists() or input_path.stat().st_size == 0:
        # FIX: Added encoding="utf-8"
        with open(output_file, 'w', encoding="utf-8") as f: json.dump([], f)
        return

    print(f"[*] Running httpx tech-detect on {input_path.name}...")
    
    cmd = [
        "httpx", "-l", str(input_path),
        "-td", "-sc", "-title", "-server",
        "-silent", "-json", "-threads", "30",
        "-o", str(temp_output)
    ]
    
    ctx.run_command(cmd, check=False)
    
    parse_httpx_json(temp_output, output_file)
    
    if temp_output.exists():
        temp_output.unlink()