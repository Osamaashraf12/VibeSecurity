import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from backend.core.paths import GENERATED_PAYLOADS_DIR, PAYLOADS_DIR, PROMPTS_DIR, SCAN_RESULTS_DIR, WORDLISTS_DIR

@dataclass
class ToolContext:
    """
    Standardized context object passed to every tool execution.
    Acts as the single source of truth for paths and configuration.
    """
    target: str
    base_dir: Path
    options: Dict[str, Any] = field(default_factory=dict)
    
    # --- Dynamic Properties ---
    @property
    def clean_target(self) -> str:
        """Removes protocol and slashes for safe filenames (e.g., 'google.com')."""
        return self.target.replace("https://", "").replace("http://", "").strip("/")

    @property
    def scan_results_dir(self) -> Path:
        """Central location for all scan outputs."""
        return SCAN_RESULTS_DIR

    @property
    def wordlists_dir(self) -> Path:
        """Central location for wordlists."""
        return WORDLISTS_DIR

    @property
    def payloads_dir(self) -> Path:
        """Central location for curated payload seeds."""
        return PAYLOADS_DIR

    @property
    def generated_payloads_dir(self) -> Path:
        """Central location for generated payload files."""
        return GENERATED_PAYLOADS_DIR

    @property
    def prompts_dir(self) -> Path:
        """Central location for shared prompt files."""
        return PROMPTS_DIR

    # --- Path Generators (The Utility) ---
    
    def get_output_path(self, tool_key: str, category: str, ext: str = "txt") -> Path:
        """
        Generates the standard output path for any tool.
        Format: var/scan_results/{category}/{target}_{tool}.{ext}
        """
        category_dir = self.scan_results_dir / category
        category_dir.mkdir(parents=True, exist_ok=True)
        return category_dir / f"{self.clean_target}_{tool_key}.{ext}"

    def get_wordlist_path(self, filename: str) -> Path:
        """Resolves a wordlist filename to its full path."""
        path = self.wordlists_dir / filename
        if not path.exists():
            pass 
        return path

    def resolve_input_path(self, tool_key: str, category: str, ext: str = "txt") -> Path:
        """
        Helper to find the output of a PREVIOUS tool to use as input.
        """
        return self.get_output_path(tool_key, category, ext)

    # --- NEW: Smart Docker Executor ---
    def run_command(self, cmd_args: List[str], check: bool = True, timeout: Optional[int] = None) -> subprocess.CompletedProcess:
        """
        Executes a shell command. Automatically translates Windows host paths to 
        Linux container paths and routes execution through Docker if DOCKER_MODE is enabled.
        """
        # Configuration - Can be overridden in your .env file
        use_docker = os.getenv("DOCKER_MODE", "true").lower() == "true"
        container_name = os.getenv("CONTAINER_NAME", "vibesecurity-app-1")
        
        translated_cmd = []
        host_base_str = str(self.base_dir)
        
        for arg in cmd_args:
            arg_str = str(arg)
            # If the argument is a file path inside our project, translate it!
            if host_base_str in arg_str:
                # Replace Windows host base with Docker '/app' base and flip slashes
                arg_str = arg_str.replace(host_base_str, "/app").replace("\\", "/")
            translated_cmd.append(arg_str)
            
        if use_docker:
            # Wrap in docker exec (using non-interactive mode for background tasks)
            final_cmd = ["docker", "exec", container_name] + translated_cmd
        else:
            final_cmd = translated_cmd
            
        print(f"[Executor] Running: {' '.join(final_cmd)}")
        
        # FIX: Added encoding="utf-8" and errors="replace" to prevent UnicodeDecodeError
        return subprocess.run(
            final_cmd, 
            check=check, 
            capture_output=True, 
            text=True, 
            encoding="utf-8",
            errors="replace",
            timeout=timeout
        )

# --- Pydantic Validation Models ---

class SubenumerArgs(BaseModel):
    target: str = Field(..., description="The target domain name")
    tools: Optional[List[str]] = Field(default_factory=list, description="List of tools to execute")

class SubbforcerArgs(BaseModel):
    target: str = Field(...)
    wordlist: str = Field(default="deepmagic-prefixes-top500.txt")
    tools: Optional[List[str]] = Field(default_factory=list, description="List of tools to execute")

class SubpermuterArgs(BaseModel):
    target: str = Field(...)
    tools: Optional[List[str]] = Field(default_factory=list, description="List of tools to execute")

class SubcheckerArgs(BaseModel):
    target: str = Field(...)
    tools: Optional[List[str]] = Field(default_factory=list, description="List of tools to execute")

class SubcrawlerArgs(BaseModel):
    target: str = Field(...)
    tools: Optional[List[str]] = Field(default_factory=list, description="List of tools to execute")

class JsAnalyzerArgs(BaseModel):
    target: str = Field(...)
    tools: Optional[List[str]] = Field(default_factory=list, description="List of tools to execute")

class LinkAnalyzerArgs(BaseModel):
    target: str = Field(...)
    tools: Optional[List[str]] = Field(default_factory=list, description="List of tools to execute")

class TechDetectorArgs(BaseModel):
    target: str = Field(...)
    tools: Optional[List[str]] = Field(default_factory=list, description="List of tools to execute")

class AIHackerArgs(BaseModel):
    http_request: str = Field(..., description="The raw HTTP request text")
    http_response: str = Field(..., description="The raw HTTP response text")

class VulnScanArgs(BaseModel):
    target: str = Field(..., description="The target domain")
    tools: Optional[List[str]] = Field(default_factory=list, description="List of Nuclei scanner tools to run")

class ActiveVerifiersArgs(BaseModel):
    target: str = Field(..., description="The target domain")
    tools: Optional[List[str]] = Field(default_factory=list, description="Specific verifiers to run")

class KatanaReadArgs(BaseModel):
    target_domain: str = Field(..., description="The target domain name to read Katana traffic for (e.g., target.com)")
    limit: int = Field(default=10, description="Number of entries to return")
    offset: int = Field(default=0, description="Starting offset for entries")

class ToolCall(BaseModel):
    tool_name: str = Field(..., description="The name of the tool from the registry")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Arguments required by the tool")

class OrchestrationPayload(BaseModel):
    workflow_id: str = Field(..., description="Unique identifier for the orchestration")
    target: str = Field(..., description="The main target domain or identifier")
    source: str = Field(..., description="The source of the request (e.g., ai_parser, manual_selection, workflow_builder)")
    steps: List[ToolCall] = Field(..., min_length=1, description="Sequential list of tools to execute")

class RecipeCreate(BaseModel):
    recipe_name: str = Field(..., description="Name of the custom recipe")
    description: str = Field(default="", description="Description of what the recipe does")
    steps: List[ToolCall] = Field(..., min_length=1, description="Sequential list of tools to execute")

class Recipe(RecipeCreate):
    recipe_id: str = Field(..., description="Unique identifier for the recipe")

class RecipeExecute(BaseModel):
    target: str = Field(..., description="The main target domain or identifier")
