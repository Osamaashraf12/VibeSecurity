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

@vibe_tool(submodule="sub_permuter", tool_id="alterx", tool_name="AlterX", category="asset", ext="txt")
def run(ctx: ToolContext):
    """Registry Entry Point for AlterX."""
    input_file = ctx.resolve_input_path("sub_enumer", "asset")
    output_file = ctx.get_output_path("alterx", "asset")
    
    if not input_file.exists() or input_file.stat().st_size == 0:
        print(f"⚠️ Skipping sub_permuter: Input {input_file.name} missing/empty.")
        return

    run_permuter(ctx, str(input_file), str(output_file))

def run_permuter(ctx: ToolContext, input_file: str, output_file: str):
    if not Path(input_file).exists():
        raise RuntimeError(f"Input file {input_file} not found.")

    print(f"[*] Permuting {Path(input_file).name} -> {Path(output_file).name}")

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    # FIX: Lowered limit to 50k to ensure downstream DNS resolving finishes rapidly
    cmd = [
        "alterx",
        "-l", input_file,
        "-o", output_file,
        "-enrich",
        "-limit", "50000",
        "-silent"
    ]

    try:
        result = ctx.run_command(cmd)
        if result.returncode != 0:
            print(f"[!] AlterX encountered a soft-fail: {result.stderr or result.stdout}")
    except Exception as e:
        print(f"[!] AlterX execution error: {e}")

    print("[*] Permutation complete.")