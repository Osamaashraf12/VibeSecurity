import sys
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
from backend.core.validators import validate_target_domain

@vibe_tool(submodule="sub_bforcer", tool_id="dnscan", tool_name="DNScan", category="asset", ext="txt")
def run(ctx: ToolContext):
    output_file = ctx.get_output_path("dnscan", "asset")
    wordlist_name = ctx.options.get("wordlist", "deepmagic-prefixes-top500.txt")
    wordlist_path = ctx.get_wordlist_path(wordlist_name)
    
    run_bruteforce(ctx, ctx.target, str(output_file), str(wordlist_path))

def run_bruteforce(ctx: ToolContext, target_domain: str, output_file: str, wordlist: str):
    validate_target_domain(target_domain)

    if not os.path.exists(wordlist):
        raise RuntimeError(f"Wordlist not found at {wordlist}")

    print(f"[*] Bruteforcing {target_domain} using {Path(wordlist).name} -> {output_file}")
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "dnscan", 
        "-d", target_domain,
        "-w", wordlist,
        "-t", "300",
        "-o", output_file
    ]

    # BUG FIX: Removed 'subprocess.run' and replaced with ctx.run_command
    result = ctx.run_command(cmd)
    
    if result.returncode == 127:
        # Fallback to python script execution if "dnscan" alias isn't setup
        cmd[0] = "dnscan.py"
        result = ctx.run_command(cmd)
        
    if result.returncode != 0:
        print(f"[!] DNScan returned a non-zero exit code: {result.stderr or result.stdout}")