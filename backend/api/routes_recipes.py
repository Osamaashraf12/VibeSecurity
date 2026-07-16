from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
import logging
import uuid

from backend.core.schemas import RecipeCreate, Recipe, RecipeExecute, OrchestrationPayload, ToolCall
from backend.core.registry import TOOL_REGISTRY, validate_recipe_steps
from backend.core.recipe_storage import read_recipes, save_recipe, delete_recipe, get_recipe
from backend.core.orchestration import WorkflowManager

router = APIRouter(tags=["Custom Recipes"])
logger = logging.getLogger(__name__)

@router.get("/list", response_model=List[Dict[str, Any]])
async def list_recipes():
    """Returns all saved custom recipes."""
    return await read_recipes()

@router.post("/save")
async def create_new_recipe(recipe: RecipeCreate):
    """Saves a new workflow configuration as a reusable recipe."""
    try:
        # Convert Pydantic ToolCall objects to dicts for validation
        steps_dict = [step.model_dump() for step in recipe.steps]
        validate_recipe_steps(steps_dict)
        
        saved_record = await save_recipe(recipe.model_dump())
        return {"status": "success", "message": "Recipe saved successfully", "recipe": saved_record}
    except ValueError as ve:
        logger.error(f"Validation error for recipe '{recipe.recipe_name}': {str(ve)}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to save recipe: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error while saving recipe.")

@router.delete("/{recipe_id}")
async def remove_recipe(recipe_id: str):
    """Deletes a specific custom recipe."""
    success = await delete_recipe(recipe_id)
    if success:
        return {"status": "success", "message": "Recipe deleted"}
    raise HTTPException(status_code=404, detail="Recipe not found.")

@router.post("/execute/{recipe_id}")
async def execute_saved_recipe(recipe_id: str, payload: RecipeExecute):
    """Fetches a saved recipe and dispatches it for execution against a target."""
    recipe = await get_recipe(recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found.")
    
    # Construct orchestration payload
    steps = [ToolCall(**step) for step in recipe.get("steps", [])]
    
    orch_payload = OrchestrationPayload(
        workflow_id=f"recipe_{recipe_id}_{str(uuid.uuid4())[:8]}",
        target=payload.target,
        source="custom_recipe",
        steps=steps
    )
    
    try:
        dispatch_result = WorkflowManager.dispatch(orch_payload)
        return {
            "status": "accepted",
            "message": f"Recipe '{recipe.get('recipe_name')}' dispatched.",
            "workflow_id": dispatch_result.get("workflow_id"),
            "target": payload.target,
            "task_ids": dispatch_result.get("task_ids", [])
        }
    except ValueError as ve:
        logger.error(f"Validation error during recipe execution: {str(ve)}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to execute recipe: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error during execution.")
