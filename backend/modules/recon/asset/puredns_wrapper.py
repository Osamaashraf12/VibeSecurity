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

@vibe_tool(submodule="sub_bforcer", tool_id="puredns", tool_name="PureDNS", category="asset", ext="txt")
def run(ctx: ToolContext):
    """Registry Entry Point for PureDNS Bruteforce."""
    output_file = ctx.get_output_path("puredns", "asset")
    
    wordlist_name = ctx.options.get("wordlist", "deepmagic-prefixes-top500.txt")
    wordlist_path = ctx.get_wordlist_path(wordlist_name)
    
    run_bruteforce(ctx, ctx.target, str(output_file), str(wordlist_path))

def run_bruteforce(ctx: ToolContext, target_domain: str, output_file: str, wordlist: str):
    validate_target_domain(target_domain)
    
    resolvers_file = ctx.get_wordlist_path("resolvers-trusted.txt")

    if not os.path.exists(wordlist):
        raise RuntimeError(f"Wordlist not found at {wordlist}")
        
    print(f"[*] Bruteforcing {target_domain} using {Path(wordlist).name}...")

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    # FIX: Boosted rate-limit drastically. PureDNS handles extreme threading well.
    cmd = [
        "puredns", "bruteforce",
        wordlist,
        target_domain,
        "-r", str(resolvers_file),
        "-w", output_file,
        "--wildcard-tests", "10",
        "--rate-limit", "5000",
        "-q"
    ]

    try:
        result = ctx.run_command(cmd)
        if result.returncode != 0:
            print(f"[!] PureDNS encountered a soft-fail: {result.stderr or result.stdout}")
    except Exception as e:
        print(f"[!] PureDNS execution error: {e}")

    print("[*] PureDNS bruteforce complete.")
