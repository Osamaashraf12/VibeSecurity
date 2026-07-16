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

@vibe_tool(submodule="sub_bforcer", tool_id="ffuf", tool_name="ffuf", category="asset", ext="txt")
def run(ctx: ToolContext):
    """Registry Entry Point for FFUF Bruteforce."""
    output_file = ctx.get_output_path("ffuf", "asset")
    wordlist_name = ctx.options.get("wordlist", "deepmagic-prefixes-top500.txt")
    wordlist_path = ctx.get_wordlist_path(wordlist_name)
    
    run_bruteforce(ctx, ctx.target, str(output_file), str(wordlist_path))

def run_bruteforce(ctx: ToolContext, target_domain: str, output_file: str, wordlist: str):
    validate_target_domain(target_domain)
    
    if not os.path.exists(wordlist):
        raise RuntimeError(f"Wordlist not found at {wordlist}")

    print(f"[*] Bruteforcing {target_domain} using FFUF with {Path(wordlist).name}...")
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    # Use a temporary JSON file for FFUF's structured output
    temp_json_out = output_file + ".json"

    cmd = [
        "ffuf",
        "-s",
        "-u", f"https://FUZZ.{target_domain}",
        "-w", wordlist,
        "-o", temp_json_out,
        "-of", "json"
    ]

    result = ctx.run_command(cmd)
    
    if result.returncode == 127:
        raise RuntimeError("ffuf execution failed: Command not found (Exit 127). Please install ffuf inside the Docker container.")
    elif result.returncode != 0:
        print(f"[!] FFUF encountered a soft-fail: {result.stderr or result.stdout}")
        
    found_subdomains = set()
    if os.path.exists(temp_json_out):
        try:
            with open(temp_json_out, 'r') as f:
                data = json.load(f)
                for res in data.get("results", []):
                    # Extract the exact FUZZ payload to guarantee a clean subdomain format
                    fuzz_word = res.get("input", {}).get("FUZZ")
                    if fuzz_word:
                        found_subdomains.add(f"{fuzz_word}.{target_domain}")
        except Exception as e:
            print(f"[!] Error parsing FFUF JSON output: {e}")
        finally:
            os.remove(temp_json_out)
            
    with open(output_file, 'w') as f:
        f.write('\n'.join(found_subdomains))