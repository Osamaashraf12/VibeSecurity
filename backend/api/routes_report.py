from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import json
from backend.core.paths import SCAN_RESULTS_DIR

router = APIRouter()

# Files that are clickable (rendered in the dashboard) vs download-only
CLICKABLE_REPORTS = {"report.json", "http_report.json", "hunter_report.json"}


@router.get("/api/report")
async def get_report():
    """
    Retrieves the generated report.json for the frontend dashboard.
    """
    report_path = SCAN_RESULTS_DIR / "report.json"
    
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="No scan report found.")
    
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse report: {e}")


@router.get("/api/report/http")
async def get_http_report():
    """
    Retrieves the generated http_report.json (from AI Hacker Markdown→JSON conversion).
    """
    report_path = SCAN_RESULTS_DIR / "http_report.json"
    
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="No HTTP analysis report found. Run an HTTP traffic scan first.")
    
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse HTTP report: {e}")


@router.get("/api/report/hunter")
async def get_hunter_report():
    """
    Retrieves the generated hunter_report.json from the Hunter Agent pipeline.
    """
    report_path = SCAN_RESULTS_DIR / "hunter_report.json"
    
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="No hunter report found. Run a Hunter Agent scan first.")
    
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse hunter report: {e}")


@router.get("/api/report/artifacts")
async def list_artifacts():
    """
    Lists all session output files in the runtime scan-results directory.
    Used by the Artifacts Sidebar in the Reporting Dashboard.
    
    Returns:
        {
            "artifacts": [
                { "name": "report.json", "type": "report", "clickable": true, "size": 3816, "path": "report.json" },
                { "name": "http_report.json", "type": "report", "clickable": true, "size": 2048, "path": "http_report.json" },
                { "name": "target_crawler.json", "type": "data", "clickable": false, "size": 15000, "path": "content/target_crawler.json" }
            ]
        }
    """
    artifacts = []
    
    if not SCAN_RESULTS_DIR.exists():
        return {"artifacts": []}
    
    # Use rglob to recursively find ALL files in scan_results and its subdirectories
    for item in SCAN_RESULTS_DIR.rglob("*"):
        if item.is_file():
            is_clickable = item.name in CLICKABLE_REPORTS
            
            # Calculate the relative path for the download endpoint
            rel_path = item.relative_to(SCAN_RESULTS_DIR).as_posix()
            
            artifacts.append({
                "name": item.name,
                "type": "report" if is_clickable else "data",
                "clickable": is_clickable,
                "size": item.stat().st_size,
                "path": rel_path,
            })
    
    return {"artifacts": artifacts}


@router.get("/api/report/download/{filepath:path}")
async def download_artifact(filepath: str):
    """
    Downloads a specific artifact file from the runtime scan-results directory.
    Supports nested paths like content/target_crawler.json.
    """
    # Security: prevent path traversal
    if ".." in filepath or filepath.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid file path.")
    
    file_path = SCAN_RESULTS_DIR / filepath
    
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {filepath}")
    
    # Ensure the resolved path is still within SCAN_RESULTS_DIR
    try:
        file_path.resolve().relative_to(SCAN_RESULTS_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied.")
    
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/octet-stream",
    )


from pydantic import BaseModel as _BaseModel

class _GenerateRequest(_BaseModel):
    target: str


@router.post("/report/generate")
async def generate_report(req: _GenerateRequest):
    """
    Consolidates all vulnerability scan findings for the given target
    into a single report.json and returns the report.
    """
    from backend.modules.reporting.report_builder import build_report

    try:
        report = build_report(req.target)
        return {
            "status": "success",
            "message": f"Report generated with {len(report.get('findings', []))} findings.",
            "report": report,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {e}")
