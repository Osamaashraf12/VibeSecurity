import sys
import subprocess
from pathlib import Path

try:
    project_root = Path(__file__).resolve().parents[4]
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))
except IndexError:
    pass

from backend.core.schemas import ToolContext
from backend.core.loader import vibe_tool

# Ensure tool_id matches what we just put in registry.py
@vibe_tool(submodule="sub_enumer", tool_id="findomain", tool_name="Findomain", category="asset", ext="txt")
def run(ctx: ToolContext):
    """
    Registry Entry Point for Findomain.
    """
    output_file = ctx.get_output_path("findomain", "asset")
    
    # Pass 'ctx' downward to use the smart Docker executor
    run_enumeration(ctx, ctx.target, str(output_file))

def run_enumeration(ctx: ToolContext, target_domain: str, output_file: str):
    print(f"[*] Enumerating {target_domain} -> {output_file}")

    # Ensure output dir exists on the host
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    # Standard Findomain CLI syntax: findomain -t domain.com -u output.txt
    cmd = [
        "findomain",
        "-t", target_domain,
        "-u", output_file, # run_command translates this path to Linux automatically!
        "-q"               # Quiet mode to prevent progress bars from spamming the logs
    ]

    try:
        # MAGIC HAPPENS HERE: Uses Docker Exec + Path Translation
        result = ctx.run_command(cmd)
        
        if result.stdout:
            print(result.stdout)
            
        print("[*] Findomain Enumeration complete.")
    except subprocess.CalledProcessError as e:
        print(f"Error Output: {e.stderr}")
        raise RuntimeError(f"Findomain execution failed in Docker: {e}")
    except Exception as e:
        print(f"Execution Error: {e}")
        raise RuntimeError(f"Failed to execute findomain command: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python findomain_wrapper.py <domain> <output_file>")
        sys.exit(1)
        
    mock_ctx = ToolContext(target=sys.argv[1], base_dir=Path(__file__).resolve().parents[4])
    run_enumeration(mock_ctx, sys.argv[1], sys.argv[2])