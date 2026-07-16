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
from backend.core.validators import validate_target_domain

@vibe_tool(submodule="sub_crawler", tool_id="gau", tool_name="GAU", category="content", ext="json")
def run(ctx: ToolContext):
    output_file = ctx.get_output_path("gau", "content", "json")
    
    checker_output = ctx.resolve_input_path("sub_checker", "asset", "json")
    hosts_file = checker_output.parent / f"{ctx.clean_target}_sub_checker_hosts.txt"
    fallback_file = ctx.resolve_input_path("sub_enumer", "asset", "txt")
    
    input_source = "DIRECT"
    if hosts_file.exists() and hosts_file.stat().st_size > 0:
        input_source = str(hosts_file)
    elif fallback_file.exists() and fallback_file.stat().st_size > 0:
        input_source = str(fallback_file)
    
    run_gau(ctx, ctx.target, input_source, str(output_file))

def run_gau(ctx: ToolContext, target_domain: str, input_file: str, output_file: str):
    validate_target_domain(target_domain)

    output_dir = Path(output_file).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = Path(output_file).stem.replace("_gau", "")

    if input_file == "DIRECT" or not Path(input_file).exists() or Path(input_file).stat().st_size == 0:
        temp_target = output_dir / f"{prefix}_temp_target_root.txt"
        # FIX: Added encoding="utf-8"
        with open(temp_target, "w", encoding="utf-8") as f: f.write(target_domain + "\n")
        actual_input_file = str(temp_target)
    else:
        actual_input_file = input_file

    print(f"[*] Running GAU on {Path(actual_input_file).name} -> {Path(output_file).name}...")
    
    # Use shell redirection to pipe the file into GAU inside the Docker container
    sh_cmd = f"cat {actual_input_file} | gau --threads 15 --timeout 15 --retries 8 --blacklist css,scss,less,png,jpg,jpeg,gif,webp,svg,ico,woff,woff2,ttf,otf,eot,mp4,mp3,webm,ogg,pdf,zip,tar,gz,rar,exe,dll,bin,swf,flv,ico,map,js.map,css.map,sourcemap,min.js,min.css --fp --fc 404,500 --o {output_file} --json"
    
    ctx.run_command(["sh", "-c", sh_cmd], check=False)
    
    print("[*] GAU complete.")
    
    if actual_input_file != input_file and Path(actual_input_file).exists():
        Path(actual_input_file).unlink()