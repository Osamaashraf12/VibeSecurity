from fastapi import APIRouter, HTTPException
from backend.core.schemas import OrchestrationPayload
from backend.core.orchestration import WorkflowManager
import logging

# Initialize router and logger
router = APIRouter(tags=["Orchestration Engine"])
logger = logging.getLogger(__name__)

@router.post("/execute")
async def execute_orchestration(payload: OrchestrationPayload):
    """
    Receives a unified orchestration payload from any entry point (AI, Manual, Workflow),
    validates dependencies, and dispatches a background workflow chain via WorkflowManager.
    """
    logger.info(f"Received {payload.source} request for {payload.target} with {len(payload.steps)} steps.")
    
    try:
        dispatch_result = WorkflowManager.dispatch(payload)
        
        return {
            "status": "accepted",
            "message": f"Orchestration from {payload.source} validated and dispatched.",
            "workflow_id": dispatch_result.get("workflow_id"),
            "chain_id": dispatch_result.get("chain_id"),
            "source": payload.source,
            "target": payload.target,
            "steps_count": len(payload.steps),
            "task_ids": dispatch_result.get("task_ids", [])
        }
        
    except ValueError as ve:
        logger.error(f"Validation error during orchestration dispatch: {str(ve)}")
        raise HTTPException(status_code=400, detail=str(ve))
    except RuntimeError as re:
        # Task queue / semaphore at capacity
        logger.warning(f"Task queue full, rejecting request: {str(re)}")
        raise HTTPException(status_code=429, detail=str(re))
    except Exception as e:
        logger.error(f"Failed to dispatch orchestration: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error during orchestration dispatch.")