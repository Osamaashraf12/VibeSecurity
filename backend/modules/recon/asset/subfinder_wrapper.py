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

# CRITICAL FIX: tool_id="subfinder" matches the UI checkbox and registry.py!
@vibe_tool(submodule="sub_enumer", tool_id="subfinder", tool_name="Subfinder", category="asset", ext="txt")
def run(ctx: ToolContext):
    """
    Registry Entry Point for Subfinder.
    """
    output_file = ctx.get_output_path("subfinder", "asset")
    
    # Pass 'ctx' downward to access the smart Docker executor
    run_enumeration(ctx, ctx.target, str(output_file))

def run_enumeration(ctx: ToolContext, target_domain: str, output_file: str):
    print(f"[*] Enumerating {target_domain} -> {output_file}")

    # Ensure output dir exists on the HOST machine (so Docker volume syncs properly)
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "subfinder",
        "-d", target_domain,
        "-o", output_file, # run_command translates this path to Linux automatically!
        "-timeout", "10",
        "-all",
        "-recursive",
        "-t", "30",
        "-rl", "50",
        "-silent"
    ]

    try:
        # MAGIC HAPPENS HERE: Uses Docker Exec + Path Translation
        result = ctx.run_command(cmd)
        
        if result.stdout:
            print(result.stdout)
            
        print("[*] Enumeration complete.")
    except subprocess.CalledProcessError as e:
        print(f"Error Output: {e.stderr}")
        raise RuntimeError(f"Subfinder execution failed in Docker: {e}")
    except Exception as e:
        print(f"Execution Error: {e}")
        raise RuntimeError(f"Failed to execute command: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python subfinder_wrapper.py <domain> <output_file>")
        sys.exit(1)
        
    # Standalone mock context for manual terminal testing
    mock_ctx = ToolContext(target=sys.argv[1], base_dir=Path(__file__).resolve().parents[4])
    run_enumeration(mock_ctx, sys.argv[1], sys.argv[2])