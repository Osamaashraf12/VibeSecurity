import sys
import os
import json
import shutil
from pathlib import Path

try:
    project_root = Path(__file__).resolve().parents[4]
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))
except IndexError:
    pass

from backend.core.schemas import ToolContext
from backend.core.loader import vibe_tool

@vibe_tool(submodule="sub_checker", tool_id="dnsx_httpx", tool_name="DNSX/HTTPX", category="asset", ext="json")
def run(ctx: ToolContext):
    """
    Registry Entry Point for Live Host Verification.
    Aggregates enumer, bforcer, and permuter results.
    """
    output_file = ctx.get_output_path("dnsx_httpx", "asset", "json")
    
    possible_inputs = [
        ctx.resolve_input_path("sub_enumer", "asset"),
        ctx.resolve_input_path("sub_bforcer", "asset"),
        ctx.resolve_input_path("sub_permuter", "asset")
    ]
    
    valid_inputs = [str(p) for p in possible_inputs if p.exists() and p.stat().st_size > 0]
    
    if not valid_inputs:
        print("❌ No valid subdomains found from previous steps. Skipping checker.")
        return

    merged_temp = output_file.parent / f"{ctx.clean_target}_merged_temp.txt"
    with open(merged_temp, 'w', encoding="utf-8") as f_out:
        seen_lines = set()
        for inp in valid_inputs:
            with open(inp, 'r', encoding="utf-8", errors="replace") as f_in:
                for line in f_in:
                    clean_line = line.strip()
                    if clean_line and clean_line not in seen_lines:
                        seen_lines.add(clean_line)
                        f_out.write(clean_line + "\n")
                        
    print(f"[*] Total unique subdomains after merge: {len(seen_lines)}")

    # --- Step 1: DNS Resolution ---
    print(f"[*] Starting DNS resolution on {merged_temp.name}...")
    dnsx_output = output_file.parent / f"{ctx.clean_target}_dnsx_httpx_dns_raw.json"
    
    # FIX: Increased rate limit from 150 to 5000 to prevent hour-long bottlenecks
    dnsx_cmd = [
        "dnsx", "-l", str(merged_temp),
        "-a", "-aaaa", "-cname", "-resp-only", "-json",
        "-o", str(dnsx_output),
        "-t", "200", "-rl", "5000", "-silent"
    ]
    
    resolvers_file = ctx.base_dir / "data" / "wordlists" / "resolvers-trusted.txt"
    if resolvers_file.exists():
        dnsx_cmd.extend(["-r", str(resolvers_file)])
        
    ctx.run_command(dnsx_cmd, check=False)
    
    # --- Step 2: Parse DNS Output & Filter ---
    hosts_list_file = output_file.parent / f"{ctx.clean_target}_dnsx_httpx_hosts.txt"
    httpx_output = output_file.parent / f"{ctx.clean_target}_dnsx_httpx_httpx.json"
    main_output_file = str(output_file)
    
    valid_hosts_count = 0
    if os.path.exists(dnsx_output):
        try:
            with open(hosts_list_file, 'w', encoding="utf-8") as f_out:
                with open(dnsx_output, 'r', encoding="utf-8", errors="replace") as f_in:
                    seen_hosts = set() # FIX: Deduplicate A/CNAME records to save HTTPX time
                    for line in f_in:
                        if not line.strip(): continue
                        try:
                            data = json.loads(line)
                            host = data.get("host")
                            if host and host not in seen_hosts:
                                seen_hosts.add(host)
                                f_out.write(host + "\n")
                                valid_hosts_count += 1
                        except json.JSONDecodeError: continue
        except Exception as e:
            print(f"[!] Error during cleaning: {e}")
            
    if valid_hosts_count == 0:
        print("[!] No live subdomains found. Skipping HTTPX.")
        Path(hosts_list_file).touch()
        return

    # --- Step 3: HTTP Probing ---
    print(f"[*] Running HTTPX on {valid_hosts_count} targets...")
    # FIX: Increased rate limit from 40 to 150
    httpx_cmd = [
        "httpx", "-l", str(hosts_list_file),
        "-sc", "-rt", "-json", "-o", str(httpx_output),
        "-t", "100", "-rl", "150", "-timeout", "10", "-fc", "404", "-mc", "200", "-silent"
    ]
    
    ctx.run_command(httpx_cmd, check=False)

    # --- Step 4: Routing & Cleanup ---
    if os.path.exists(httpx_output) and os.path.getsize(httpx_output) > 0:
        shutil.move(httpx_output, main_output_file)
        print(f"[*] Replaced DNS output with rich HTTPX JSON data -> {Path(main_output_file).name}")
    else:
        print("[!] HTTPX produced no output. Falling back to basic DNS JSON data.")
        if os.path.exists(dnsx_output):
            shutil.move(dnsx_output, main_output_file)

    print("[*] Cleaning up intermediate checker files...")
    for f in [merged_temp, dnsx_output, hosts_list_file]:
        if os.path.exists(f):
            os.remove(f)