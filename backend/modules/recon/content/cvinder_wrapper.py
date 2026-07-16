import sys
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

def _get_cvinder_script_path(ctx: ToolContext) -> Path:
    """Resolve path to CVINDER.py script within the Docker Volume."""
    return ctx.base_dir / "backend" / "tools" / "CVINDER" / "CVINDER.py"

@vibe_tool(submodule="sub_crawler", tool_id="cvinder", tool_name="CVINDER", category="content", ext="json")
def run(ctx: ToolContext):
    output_file = ctx.get_output_path("cvinder", "content", "json")
    run_cvinder(ctx, ctx.target, str(output_file))

def run_cvinder(ctx: ToolContext, target_domain: str, output_file: str, min_cvss: float = 7.0):
    hostname = target_domain.replace("https://", "").replace("http://", "").strip("/")
    output_dir = Path(output_file).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    cvinder_script = _get_cvinder_script_path(ctx)

    print(f"[*] Running CVINDER on {hostname} -> {Path(output_file).name}...")

    cvinder_cmd = [
        "python3", str(cvinder_script),
        "-host", hostname,
        "-o", output_file,
        "-e",
        "-cvss", str(int(min_cvss)),
    ]

    try:
        # ctx.run_command executes safely inside docker
        ctx.run_command(cvinder_cmd, check=False, timeout=300)
        print("[*] CVINDER complete.")
    except Exception as e:
        print(f"[!] CVINDER execution failed: {e}")
        if not Path(output_file).exists():
            with open(output_file, "w") as f:
                json.dump([], f)