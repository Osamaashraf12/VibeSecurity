import sys
from pathlib import Path
from urllib.parse import urlparse

try:
    project_root = Path(__file__).resolve().parents[4]
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))
except IndexError:
    pass

from backend.core.schemas import ToolContext
from backend.core.loader import vibe_tool
from backend.core.validators import validate_target_domain


@vibe_tool(submodule="sub_crawler", tool_id="katana", tool_name="Katana", category="content", ext="json")
def run(ctx: ToolContext):
    output_file = ctx.get_output_path("katana", "content", "json")

    checker_output = ctx.resolve_input_path("sub_checker", "asset", "json")
    hosts_file = checker_output.parent / f"{ctx.clean_target}_sub_checker_hosts.txt"
    fallback_file = ctx.resolve_input_path("sub_enumer", "asset", "txt")

    input_source = "DIRECT"
    if hosts_file.exists() and hosts_file.stat().st_size > 0:
        input_source = str(hosts_file)
    elif fallback_file.exists() and fallback_file.stat().st_size > 0:
        input_source = str(fallback_file)

    run_katana(ctx, ctx.target, input_source, str(output_file))


def run_katana(ctx: ToolContext, target_domain: str, input_file: str, output_file: str):
    """
    Run Katana crawler on the given target.

    target_domain may be:
      - a bare FQDN:   "juice-shop.herokuapp.com"
      - a full URL:    "https://juice-shop.herokuapp.com/"
    The validator always receives the bare FQDN only.
    The crawl input file always gets the full https:// URL.
    """
    # Extract bare domain for validation (strips scheme, port, path)
    _parsed = urlparse(target_domain)
    bare_domain = (_parsed.netloc or _parsed.path).split(":")[0].rstrip("/")
    validate_target_domain(bare_domain)

    resolvers_file = ctx.get_wordlist_path("resolvers-trusted.txt")
    output_dir = Path(output_file).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    prefix = Path(output_file).stem.replace("_katana", "")
    actual_input_file = None

    if input_file == "DIRECT" or not Path(input_file).exists() or Path(input_file).stat().st_size == 0:
        temp_target = output_dir / f"{prefix}_temp_target_root.txt"
        # Always use https:// so we don't hit 503s on HTTPS-only hosts (e.g. Heroku)
        url_entry = target_domain if target_domain.startswith(("http://", "https://")) else f"https://{bare_domain}"
        with open(temp_target, "w") as f:
            f.write(url_entry + "\n")
        actual_input_file = str(temp_target)
    else:
        actual_input_file = input_file

    print(f"[*] Running Katana on {Path(actual_input_file).name} -> {Path(output_file).name}...")

    katana_cmd = [
        "katana", "-list", actual_input_file,
        "-d", "6", "-jc", "-jsl", "-kf", "all",
        "-c", "30", "-rl", "120", "-timeout", "10", "-silent",
        "-ef", "css,scss,less,png,jpg,jpeg,gif,webp,svg,ico,woff,woff2,ttf,otf,eot,mp4,mp3,webm,ogg,pdf,zip,tar,gz,rar,exe,dll,bin,swf,flv,ico,map,js.map,css.map,sourcemap,min.js,min.css",
        "-o", output_file, "-jsonl", "-store-response"
    ]
    if resolvers_file.exists():
        katana_cmd.extend(["-r", str(resolvers_file)])

    result = ctx.run_command(katana_cmd, check=False)
    if result.returncode != 0:
        print(f"[!] Katana exited with code {result.returncode}")
        if result.stderr:
            print(f"[!] Katana stderr:\n{result.stderr[:2000]}")
        if result.stdout:
            print(f"[!] Katana stdout:\n{result.stdout[:2000]}")
    else:
        print("[*] Katana complete.")
