import sys
import os
import json
from pathlib import Path

try:
    project_root = Path(__file__).resolve().parents[4]
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))
except IndexError:
    pass

from backend.core.schemas import ToolContext
from backend.core.loader import vibe_tool
from backend.core.validators import validate_target_domain

@vibe_tool(submodule="sub_Vhost", tool_id="ffuf_vhost", tool_name="Virtual Host Enumeration", category="asset", ext="txt")
def run(ctx: ToolContext):
    output_file = ctx.get_output_path("ffuf_vhost", "asset")
    wordlist_name = ctx.options.get("wordlist", "deepmagic-prefixes-top500.txt")
    wordlist_path = ctx.get_wordlist_path(wordlist_name)
    
    # FIX: Use clean_target to prevent FFUF from generating invalid URLs like https://https://target.com
    run_vhost_enumeration(ctx, ctx.clean_target, str(output_file), str(wordlist_path))

def run_vhost_enumeration(ctx: ToolContext, target_domain: str, output_file: str, wordlist: str):
    validate_target_domain(target_domain)

    if not os.path.exists(wordlist):
        raise RuntimeError(f"Wordlist not found at {wordlist}")

    print(f"[*] Virtual Host Enumerating {target_domain} using {Path(wordlist).name} -> {Path(output_file).name}")
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    # Use a temporary JSON file for structured parsing
    temp_json_out = output_file + ".json"

    # FIX 1: Added '-ac' (Auto-Calibration) to filter out wildcard/catch-all false positives.
    # FIX 2: Added '-t 50' to increase threading and prevent slow execution times.
    cmd = [
        "ffuf",
        "-s",
        "-ac",
        "-t", "50",
        "-u", f"https://{target_domain}",
        "-w", wordlist,
        "-H", f"Host: FUZZ.{target_domain}",
        "-o", temp_json_out,
        "-of", "json"
    ]

    try:
        # FIX 3: Added a 10-minute timeout so FFUF can never hang the background worker infinitely
        result = ctx.run_command(cmd, check=False, timeout=600)
        
        if result.returncode == 127:
            raise RuntimeError("ffuf execution failed: Command not found (Exit 127). Please install ffuf inside the Docker container.")
        elif result.returncode != 0 and not os.path.exists(temp_json_out):
            print(f"[!] FFUF encountered a soft-fail or timeout: {result.stderr or result.stdout}")
    except Exception as e:
        print(f"[!] FFUF execution error (Timeout/Crash): {e}")
        
    # Parse the structured JSON safely
    found_vhosts = set()
    if os.path.exists(temp_json_out):
        try:
            # FIX 4: Enforce utf-8 encoding to prevent UnicodeDecodeError crashes on weird payloads
            with open(temp_json_out, 'r', encoding="utf-8", errors="replace") as f:
                data = json.load(f)
                for res in data.get("results", []):
                    # For VHosts, the target is in the header, so we extract the exact FUZZ payload
                    fuzz_word = res.get("input", {}).get("FUZZ")
                    if fuzz_word:
                        found_vhosts.add(f"{fuzz_word}.{target_domain}")
        except Exception as e:
            print(f"[!] Error parsing FFUF JSON output: {e}")
        finally:
            os.remove(temp_json_out)
            
    with open(output_file, 'w', encoding="utf-8") as f:
        f.write('\n'.join(found_vhosts))
    
    print("[*] FFUF VHost enumeration complete.")