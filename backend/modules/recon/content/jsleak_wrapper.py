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

@vibe_tool(submodule="js_analyzer", tool_id="jsleak", tool_name="JSLeak", category="content", ext="txt")
def run(ctx: ToolContext):
    output_file = ctx.get_output_path("jsleak", "content", "txt")
    js_urls_file = Path(ctx.scan_results_dir) / "content" / f"{ctx.clean_target}_js_analysis" / "js_target_urls.txt"
    
    input_source = None
    if js_urls_file.exists() and js_urls_file.stat().st_size > 0:
        input_source = str(js_urls_file)
    else:
        print("❌ Error: No JS URLs input file found for JSLeak.")
        return

    run_jsleak(ctx, input_source, str(output_file))

def run_jsleak(ctx: ToolContext, input_file: str, output_file: str):
    output_dir = Path(output_file).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Running JSLeak on {Path(input_file).name} -> {Path(output_file).name}...")
    
    # Run through docker bash pipe
    sh_cmd = f"cat {input_file} | xargs -P 20 -I {{}} jsleak -s -l -k -e {{}} > {output_file}"
    ctx.run_command(["sh", "-c", sh_cmd], check=False)
            
    print("[*] JSLeak complete.")