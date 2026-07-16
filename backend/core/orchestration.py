"""
VibeSecurity Orchestration Engine
==================================
Handles tool dispatch, dependency checking, and multi-step workflows.
All tools execute directly in-process via Python import + run(ctx).
Background execution is handled by TaskManager (ThreadPoolExecutor).
"""

import importlib
import json
import sys
import traceback
import re
from urllib.parse import urlparse
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)

from backend.core.registry import TOOL_REGISTRY, ToolMetadata
from backend.core.schemas import (
    ToolContext, SubenumerArgs, SubbforcerArgs, SubpermuterArgs, SubcheckerArgs,
    SubcrawlerArgs, JsAnalyzerArgs, LinkAnalyzerArgs, TechDetectorArgs, AIHackerArgs,
    VulnScanArgs, OrchestrationPayload
)
from backend.core.task_manager import task_manager
from backend.core.loader import PLUGIN_FUNCS
from backend.modules.exploitation.payload_generation import (
    generate_payload_files_for_step,
    is_payload_generation_step,
)


class Orchestrator:
    def __init__(self):
        self.base_dir = Path(__file__).resolve().parents[2]

    def _check_dependencies(self, metadata: ToolMetadata, ctx: ToolContext, simulated_outputs: Optional[set] = None) -> bool:
        """
        Verifies if the output files of required tools exist or will be produced.
        We issue warnings but DO NOT block execution, so tools can use their 
        internal fallbacks (e.g. running on the root domain) if upstream files are missing.
        """
        if not metadata.requires:
            return True

        AGGREGATOR_TOOLS = {"sub_checker", "link_analyzer", "tech_detector"}
        is_aggregator = metadata.key in AGGREGATOR_TOOLS

        found_dependencies = 0
        missing_dependencies = []

        for req_key in metadata.requires:
            # Check if it exists in simulated outputs (for chains)
            if simulated_outputs and req_key in simulated_outputs:
                found_dependencies += 1
                continue

            if req_key not in TOOL_REGISTRY:
                continue
                
            # FIX: Special case for link_analyzer (it outputs a directory of patterns, not a single file)
            if req_key == "link_analyzer":
                pattern_dir = ctx.scan_results_dir / "content" / f"{ctx.clean_target}_patterns"
                if pattern_dir.exists() and any(pattern_dir.iterdir()):
                    found_dependencies += 1
                else:
                    missing_dependencies.append(req_key)
                continue
            
            req_meta = TOOL_REGISTRY[req_key]
            req_path = ctx.resolve_input_path(req_meta.key, req_meta.category, req_meta.output_ext)
            
            # Special case for crawler consuming text files
            if req_key == "sub_crawler":
                 req_path = req_path.parent / Path(f"{ctx.clean_target}_crawled_links.txt").name

            if req_path.exists() and req_path.stat().st_size > 0:
                found_dependencies += 1
            else:
                missing_dependencies.append(req_key)

        if is_aggregator:
            if found_dependencies == 0:
                print(f"⚠️ [Orchestrator] Dependency Missing for {metadata.name}. Needs at least one of: {metadata.requires}. Proceeding with fallback.")
            return True
        else:
            if len(missing_dependencies) > 0:
                print(f"⚠️ [Orchestrator] Strict Dependencies Missing for {metadata.name}: {missing_dependencies}. Proceeding with fallback.")
            return True

    def _execute_tool(self, metadata: ToolMetadata, ctx: ToolContext):
        """
        Execute a tool directly in-process by importing its module and calling run(ctx).
        This runs inside a background thread via TaskManager.
        """
        module = importlib.import_module(metadata.module_path)
        entry_fn = getattr(module, metadata.entry_point, None)

        if entry_fn is None:
            raise RuntimeError(f"Entry point '{metadata.entry_point}' not found in {metadata.module_path}")

        entry_fn(ctx)
        return f"{metadata.name} completed successfully."

    def handle_ai_tool_call(self, tool_call_data: dict):
        """
        Intercepts an AI-generated tool call, validates it with Pydantic,
        and dispatches it to the background task queue.
        """
        try:
            # Extract details from Ollama's tool_call format
            function_data = tool_call_data.get("function", {})
            tool_key = function_data.get("name")
            arguments = function_data.get("arguments", {})

            if not tool_key or tool_key not in TOOL_REGISTRY:
                logger.warning(f"Unknown tool requested by AI: {tool_key}")
                return {"error": f"Invalid or unregistered tool requested: {tool_key}"}

            # Schema mapping for validation
            schema_map = {
                "sub_enumer": SubenumerArgs,
                "sub_bforcer": SubbforcerArgs,
                "sub_permuter": SubpermuterArgs,
                "sub_checker": SubcheckerArgs,
                "sub_crawler": SubcrawlerArgs,
                "js_analyzer": JsAnalyzerArgs,
                "link_analyzer": LinkAnalyzerArgs,
                "tech_detector": TechDetectorArgs,
                "ai_hacker": AIHackerArgs,
                "vuln_scan": VulnScanArgs
            }

            model_class = schema_map.get(tool_key)
            if not model_class:
                return {"error": f"No Pydantic schema found for {tool_key}"}

            # Validate data using Pydantic
            validated_args = model_class(**arguments)
            
            # Prepare arguments for execution
            target = getattr(validated_args, "target", None)
            
            # Special handling for tools that don't take a standard target domain
            if tool_key == "ai_hacker":
                options = {
                    "http_request": getattr(validated_args, "http_request", ""),
                    "http_response": getattr(validated_args, "http_response", "")
                }
                target = "traffic_analysis" # Placeholder target for tracking
            else:
                options = validated_args.model_dump(exclude={"target"}, exclude_unset=True)

            print(f"🧠 [AI Tool Dispatch] Validated request for {tool_key}")
            
            # Dispatch using the standard run_tool method
            return self.run_tool(tool_key, target, options)

        except Exception as e:
            print(f"❌ [Orchestrator] Failed to Dispatch Task: {e}")
            traceback.print_exc()
            return {"status": "error", "message": str(e)}

    def run_tool(self, tool_key: str, target: str, options: Optional[Dict[str, Any]] = None):
        """
        Executes a tool in a background thread via TaskManager.
        Returns immediately with a task_id for polling.
        """
        if tool_key not in TOOL_REGISTRY:
            return {"error": f"Tool '{tool_key}' not found in registry."}

        metadata = TOOL_REGISTRY[tool_key]
        ctx = ToolContext(target=target, base_dir=self.base_dir, options=options or {})

        print(f"[Orchestrator] Dispatching: {metadata.name} ({tool_key})")
        
        # 1. Check Dependencies
        if not self._check_dependencies(metadata, ctx):
            return {"error": f"Missing dependencies for {metadata.name}", "missing": metadata.requires}

        def _tracked_execute():
            return self._execute_tool(metadata, ctx)
        task_id = task_manager.submit(
            _tracked_execute,
            tool_name=tool_key,
        )

        print(f"[Orchestrator] Task Submitted. ID: {task_id}")
        return {
            "status": "success",
            "message": "Task dispatched to background worker.",
            "task_id": task_id,
            "tool": tool_key,
            "scan_id": None,
        }

        
class WorkflowManager:
    """
    Manages the execution of multi-tool security workflows mapped from the visual UI.
    Tools execute sequentially in a background thread.
    """

    @staticmethod
    def _sanitize_url(raw_url: str) -> str:
        """
        Aggressively sanitizes a URL to prevent downstream hangs caused by poisoned crawler data.
        Removes appended HTTP headers, vulnerability tags, and trailing punctuation.
        """
        if not raw_url or not isinstance(raw_url, str):
            return ""
            
        url = raw_url.strip()
        
        # 1. Regex to extract valid HTTP/HTTPS base, ignoring prepended garbage
        match = re.search(r'(https?://[^\s\'"<>\\]+)', url)
        if not match:
            return ""
        url = match.group(1)
        
        # 2. Aggressively remove appended garbage (Headers, Tags, Severities)
        bad_suffixes = [
            "Medium", "High", "Low", "Critical", "Info", "Cross-Site", 
            "Host:", "Cookie:", "Accept:", "User-Agent:", "Cacheable", 
            "Request", "Response", "Server:", "Date:", "111"
        ]
        
        changed = True
        while changed:
            changed = False
            for suffix in bad_suffixes:
                if url.endswith(suffix):
                    url = url[:-len(suffix)]
                    changed = True
                    
        # 3. Strip trailing punctuation often left by bad log parsers
        url = url.rstrip(',;"|')
        
        # 4. Validate strict URL structure
        try:
            parsed = urlparse(url)
            if parsed.scheme in ['http', 'https'] and parsed.netloc:
                # Discard insanely long URLs (likely corrupted payloads causing downstream hangs)
                if len(url) > 1024:
                    return ""
                return url
        except ValueError:
            pass
            
        return ""

    @staticmethod
    def _merge_outputs(target: str, submodule: str, tools_run: List[str], category: str, ext: str, base_dir: Path):
        """Merges outputs from multiple parallel tools into a single submodule output file and cleans up."""
        ctx = ToolContext(target=target, base_dir=base_dir)
        out_dir = ctx.scan_results_dir / category
        out_dir.mkdir(parents=True, exist_ok=True)

        files_to_delete = []

        # Special handling for crawler producing txt URLs from json
        if submodule == "sub_crawler":
            merged_txt = out_dir / f"{ctx.clean_target}_crawled_links.txt"
            merged_json = out_dir / f"{ctx.clean_target}_{submodule}.json"
            
            found_urls = set()
            all_json_lines = []
            
            for t in tools_run:
                t_file = out_dir / f"{ctx.clean_target}_{t}.json"
                if not t_file.exists():
                    continue
                files_to_delete.append(t_file)
                with open(t_file, 'r', encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line_stripped = line.strip()
                        if not line_stripped:
                            continue
                        all_json_lines.append(line_stripped)
                        try:
                            data = json.loads(line_stripped)
                            raw_url = data.get("url") or (data.get("request") or {}).get("endpoint")
                            if raw_url:
                                clean_url = WorkflowManager._sanitize_url(raw_url)
                                if clean_url:
                                    found_urls.add(clean_url)
                        except Exception:
                            continue
                            
            # Write both formats (TXT for legacy/external tools, JSON for advanced Logic Probers)
            with open(merged_txt, 'w', encoding="utf-8") as f:
                f.write('\n'.join(sorted(found_urls)))
                
            with open(merged_json, 'w', encoding="utf-8") as f:
                f.write('\n'.join(all_json_lines))
            
            # Cleanup intermediate files safely
            for temp_file in files_to_delete:
                temp_file.unlink(missing_ok=True)
                
            return f"Merged crawler outputs into {merged_txt} and {merged_json}"

        merged_file = out_dir / f"{ctx.clean_target}_{submodule}.{ext}"

        if ext == "txt":
            merged_lines = set()
            for t in tools_run:
                t_file = out_dir / f"{ctx.clean_target}_{t}.txt"
                if not t_file.exists():
                    continue
                files_to_delete.append(t_file)
                with open(t_file, 'r', encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            merged_lines.add(line)
            with open(merged_file, 'w', encoding="utf-8") as f:
                f.write('\n'.join(x for x in merged_lines if x.strip()))
                
            # Cleanup intermediate files
            for temp_file in files_to_delete:
                temp_file.unlink(missing_ok=True)
                
            return f"Merged txt outputs into {merged_file}"

        elif ext == "json":
            all_json_lines = []
            for t in tools_run:
                t_file = out_dir / f"{ctx.clean_target}_{t}.json"
                if not t_file.exists():
                    continue
                files_to_delete.append(t_file)
                with open(t_file, 'r', encoding="utf-8", errors="replace") as f:
                    all_json_lines.extend(f.read().splitlines())
            with open(merged_file, 'w', encoding="utf-8") as f:
                f.write('\n'.join(all_json_lines))
                
            # Cleanup intermediate files
            for temp_file in files_to_delete:
                temp_file.unlink(missing_ok=True)
                
            return f"Merged json lines into {merged_file}"

        raise ValueError("Unsupported merge extension")

    @staticmethod
    def _run_workflow_chain(payload: OrchestrationPayload, base_dir: Path):
        """
        Executes workflow steps sequentially in a single background thread.
        """
        results = []

        try:
            completed_tool_keys = []

            for step in payload.steps:
                tool_key = step.tool_name
                if tool_key not in TOOL_REGISTRY:
                    raise ValueError(f"Tool '{tool_key}' not found in registry.")

                metadata = TOOL_REGISTRY[tool_key]
                tool_args = step.arguments.copy()
                if "target" not in tool_args:
                    tool_args["target"] = payload.target

                tools = tool_args.pop("tools", [])

                try:
                    if metadata.available_tools:
                        if not tools:
                            tools = list(metadata.available_tools.keys())

                        if is_payload_generation_step(tool_key, tool_args):
                            payload_ctx = ToolContext(
                                target=payload.target,
                                base_dir=base_dir,
                                options=tool_args,
                            )
                            generated_payload_files = generate_payload_files_for_step(
                                ctx=payload_ctx,
                                parent_tool_key=tool_key,
                                selected_subtools=tools,
                                previous_tool_keys=completed_tool_keys,
                                workflow_id=payload.workflow_id,
                                user_prompt=tool_args.get("payload_prompt"),
                            )
                            tool_args["generated_payload_files"] = generated_payload_files
                            tool_args["payload_files"] = generated_payload_files

                        # Execute each sub-tool sequentially
                        for t in tools:
                            sub_ctx = ToolContext(
                                target=payload.target,
                                base_dir=base_dir,
                                options=tool_args,
                            )
                            try:
                                if t in PLUGIN_FUNCS:
                                    PLUGIN_FUNCS[t](sub_ctx)
                                else:
                                    sub_meta = TOOL_REGISTRY.get(t)
                                    if sub_meta:
                                        assert sub_meta.module_path.startswith("backend.modules.")
                                        mod = importlib.import_module(sub_meta.module_path)
                                        fn = getattr(mod, sub_meta.entry_point)
                                        fn(sub_ctx)
                                    else:
                                        logger.error(f"Sub-tool {t} not found in TOOL_REGISTRY or PLUGIN_FUNCS")
                                        continue
                            except Exception as e:
                                print(f"[Workflow] Sub-tool {t} failed (soft-fail): {e}")

                        # Merge outputs from all sub-tools (THIS NOW CLEANS UP TEMP FILES)
                        WorkflowManager._merge_outputs(
                            payload.target, tool_key, tools,
                            metadata.category, metadata.output_ext, base_dir,
                        )
                    else:
                        ctx = ToolContext(
                            target=payload.target,
                            base_dir=base_dir,
                            options=tool_args,
                        )
                        mod = importlib.import_module(metadata.module_path)
                        fn = getattr(mod, metadata.entry_point)
                        fn(ctx)

                except Exception as step_err:
                    print(f"[Workflow] Step {tool_key} failed: {step_err}")
                    raise

                results.append({"tool": tool_key, "status": "completed"})
                completed_tool_keys.append(tool_key)
                print(f"[Workflow] Step completed: {tool_key}")


        except Exception:
            raise

        return results

    @staticmethod
    def dispatch(payload: OrchestrationPayload) -> Dict[str, Any]:
        orchestrator = Orchestrator()
        steps_info = []
        
        simulated_outputs = set()
        
        for step in payload.steps:
            tool_key = step.tool_name
            if tool_key not in TOOL_REGISTRY:
                raise ValueError(f"Tool '{tool_key}' not found in registry.")
            
            metadata = TOOL_REGISTRY[tool_key]
            ctx = ToolContext(target=payload.target, base_dir=orchestrator.base_dir, options=step.arguments)
            
            if not orchestrator._check_dependencies(metadata, ctx, simulated_outputs):
                raise ValueError(f"Validation Failed: Tool '{tool_key}' is missing required dependencies: {metadata.requires}. "
                                f"Ensure required tools are selected in the correct order.")
            
            simulated_outputs.add(tool_key)
            steps_info.append({"tool": tool_key, "arguments": step.arguments})

        if not steps_info:
            raise ValueError("Workflow contains no valid steps.")

        print(f"🚀 [WorkflowManager] Dispatching workflow for {payload.source}: {len(steps_info)} steps.")
        
        task_id = task_manager.submit(
            WorkflowManager._run_workflow_chain,
            payload,
            orchestrator.base_dir,
            tool_name=f"workflow_{payload.workflow_id}",
        )

        print(f"✅ [WorkflowManager] Workflow dispatched. Task ID: {task_id}")

        return {
            "workflow_id": payload.workflow_id,
            "status": "dispatched",
            "source": payload.source,
            "target": payload.target,
            "steps": steps_info,
            "task_ids": [task_id],
            "chain_id": task_id,
        }

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python orchestration.py <tool_key> <target>")
        sys.exit(1)
    
    print(Orchestrator().run_tool(sys.argv[1], sys.argv[2]))
