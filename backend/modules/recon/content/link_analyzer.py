import sys
from pathlib import Path

try:
    project_root = Path(__file__).resolve().parents[4]
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))
except IndexError:
    pass

from backend.core.schemas import ToolContext
from backend.core.loader import vibe_tool

# FIX: Added 'interestingparams' and 'interestingsubs' to the GF pattern loop
GF_PATTERNS = [
    "xss", "sqli", "ssrf", "lfi", "rce", "idor", "redirect", 
    "ssti", "debug_logic", "uploads", "sensitive_files", 
    "secrets", "api_endpoints", "js", "interestingparams", "interestingsubs"
]

@vibe_tool(submodule="link_analyzer", tool_id="gf", tool_name="GF Pattern Matcher", category="content", ext="txt")
def run(ctx: ToolContext):
    crawler_output_base = ctx.resolve_input_path("sub_crawler", "content", "json")
    crawler_links_file = crawler_output_base.parent / f"{ctx.clean_target}_crawled_links.txt"
    
    js_output_base = ctx.scan_results_dir / "content" / f"{ctx.clean_target}_js_analysis"
    js_endpoints_file = js_output_base / "all_endpoints.txt"
    
    output_dir = ctx.scan_results_dir / "content" / f"{ctx.clean_target}_patterns"
    
    inputs = []
    if crawler_links_file.exists(): inputs.append(str(crawler_links_file))
    if js_endpoints_file.exists(): inputs.append(str(js_endpoints_file))
        
    if not inputs:
        print("❌ Error: No crawler or JS links found for Pattern Matching.")
        return

    run_link_analyzer(ctx, inputs, str(output_dir))

def merge_inputs(input_files: list, output_file: Path):
    unique_urls = set()
    print(f"[*] Merging {len(input_files)} input files...")
    
    for file in input_files:
        try:
            # FIX: Added encoding="utf-8"
            with open(file, 'r', encoding="utf-8", errors="replace") as f:
                for line in f:
                    url = line.strip()
                    if url and url.startswith("http"):
                        unique_urls.add(url)
        except Exception as e:
            print(f"    ⚠️ Failed to read {file}: {e}")
            
    # FIX: Added encoding="utf-8"
    with open(output_file, 'w', encoding="utf-8") as f:
        f.write('\n'.join(unique_urls))
    
    print(f"[*] Total Unique URLs for Analysis: {len(unique_urls)}")
    return output_file

def run_link_analyzer(ctx: ToolContext, input_files: list, output_pattern_dir: str):
    out_path = Path(output_pattern_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    
    merged_file = out_path / "full_merged_list.txt"
    merge_inputs(input_files, merged_file)
    
    print("[*] Running GF Pattern Matching...")
    
    # FIX: Added encoding="utf-8"
    if not merged_file.read_text(encoding="utf-8", errors="replace").strip():
        print("    ⚠️ No URLs to scan.")
        return

    for pattern in GF_PATTERNS:
        outfile = out_path / f"{pattern}.txt"
        sh_cmd = f"cat {merged_file} | gf {pattern} > {outfile}"
        ctx.run_command(["sh", "-c", sh_cmd], check=False)
        
        if outfile.exists() and outfile.stat().st_size > 0:
            # FIX: Added encoding="utf-8"
            lines = len(outfile.read_text(encoding="utf-8", errors="replace").strip().split('\n'))
            if lines > 0:
                print(f"    [+] {pattern.upper()}: Found {lines} candidates.")
                
    # Run URO for deduplication
    print("[*] Running 'uro' deduplication safely...")
    
    files_to_dedup = [merged_file] + [out_path / f"{p}.txt" for p in GF_PATTERNS]
    
    for file in files_to_dedup:
        if file.exists() and file.stat().st_size > 0:
            dedup_file = out_path / f"{file.name}_dedup"
            
            # FIX: Don't use `&& mv`. Let python handle the replace logic to prevent data wiping
            uro_cmd = f"cat {file} | uro > {dedup_file}"
            ctx.run_command(["sh", "-c", uro_cmd], check=False)
            
            # ONLY replace if uro succeeded and generated output
            if dedup_file.exists() and dedup_file.stat().st_size > 0:
                dedup_file.replace(file) # Overwrites original safely
            else:
                # uro failed or returned nothing, clean up empty file and keep original
                if dedup_file.exists():
                    dedup_file.unlink()

    # FIX: Write a dummy standard output file to clear the Orchestrator's dependency fallback warning
    standard_out = ctx.get_output_path("link_analyzer", "content", "txt")
    with open(standard_out, "w", encoding="utf-8") as f:
        f.write("Link analysis completed successfully. Patterns saved to directory.\n")

    print(f"✅ Link Analysis Complete. Results saved to {out_path}")