"""File-backed custom recipe storage."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from backend.core.paths import RECIPES_FILE, ensure_runtime_dirs


def _read_store() -> list[dict[str, Any]]:
    if not RECIPES_FILE.exists():
        return []
    try:
        with open(RECIPES_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _write_store(recipes: list[dict[str, Any]]) -> None:
    ensure_runtime_dirs()
    tmp_path = RECIPES_FILE.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(recipes, handle, indent=2, ensure_ascii=True)
    tmp_path.replace(RECIPES_FILE)


async def read_recipes() -> list[dict[str, Any]]:
    return _read_store()


async def save_recipe(recipe_data: dict[str, Any]) -> dict[str, Any]:
    record = {
        "recipe_id": str(uuid4()),
        "recipe_name": recipe_data.get("recipe_name", "Untitled Recipe"),
        "description": recipe_data.get("description", ""),
        "steps": recipe_data.get("steps", []),
    }
    recipes = _read_store()
    recipes.insert(0, record)
    _write_store(recipes)
    return record


async def delete_recipe(recipe_id: str) -> bool:
    recipes = _read_store()
    remaining = [recipe for recipe in recipes if recipe.get("recipe_id") != recipe_id]
    if len(remaining) == len(recipes):
        return False
    _write_store(remaining)
    return True


async def get_recipe(recipe_id: str) -> dict[str, Any] | None:
    for recipe in _read_store():
        if recipe.get("recipe_id") == recipe_id:
            return recipe
    return None
