"""Async OpenRouter wrapper for the Hunter Agent."""

from __future__ import annotations

import asyncio
import logging
import time

from backend.core.llm.model_config import FALLBACKS, OPENROUTER_MODELS, needs_reasoning
from backend.core.openrouter_client import OpenRouterClient
from backend.core.telemetry import log_llm_call

logger = logging.getLogger(__name__)


class OpenRouterAgentClient:
    """Async wrapper around the synchronous OpenRouterClient."""

    RPM_LIMIT = 20

    def __init__(self, client: OpenRouterClient | None = None):
        self._client = client or OpenRouterClient()
        self._call_timestamps: dict[str, list[float]] = {}
        logger.info("OpenRouterAgentClient initialized")

    async def _enforce_rpm(self, model: str) -> None:
        now = time.time()
        timestamps = self._call_timestamps.setdefault(model, [])
        timestamps[:] = [stamp for stamp in timestamps if now - stamp < 60]

        if len(timestamps) >= self.RPM_LIMIT:
            wait_time = 60.0 - (now - timestamps[0]) + 1.0
            logger.info(
                "[OpenRouterAgent] RPM limit (%s/min) hit for %s. Sleeping %.1fs",
                self.RPM_LIMIT,
                model,
                wait_time,
            )
            await asyncio.sleep(wait_time)

        timestamps.append(time.time())

    def _build_extra_body(self, model: str, thinking: bool = False) -> dict:
        extra = {}
        if needs_reasoning(model) and thinking:
            extra["reasoning"] = {"enabled": True}
        return extra

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        node_name: str = "coordinator",
        thinking: bool = False,
        temperature: float | None = None,
    ) -> str:
        primary_model = OPENROUTER_MODELS.get(node_name, "openai/gpt-oss-120b:free")
        fallback_model = FALLBACKS.get(node_name, "openai/gpt-oss-120b:free")

        try:
            await self._enforce_rpm(primary_model)
            return await self._call(
                prompt,
                system_prompt,
                primary_model,
                thinking,
                temperature,
                node_name=node_name,
            )
        except Exception as exc:
            logger.error(
                "[OpenRouterAgent] Primary model %s failed after internal retries: %s",
                primary_model,
                exc,
            )

            if fallback_model and fallback_model != primary_model:
                try:
                    logger.warning(
                        "[OpenRouterAgent] Falling back to %s for node %s",
                        fallback_model,
                        node_name,
                    )
                    await self._enforce_rpm(fallback_model)
                    return await self._call(
                        prompt,
                        system_prompt,
                        fallback_model,
                        thinking,
                        temperature,
                        node_name=node_name,
                        was_fallback=True,
                    )
                except Exception as fallback_exc:
                    raise RuntimeError(
                        f"Both primary ({primary_model}) and fallback ({fallback_model}) "
                        f"failed for node '{node_name}'. Primary error: {exc}; "
                        f"fallback error: {fallback_exc}"
                    ) from fallback_exc

            raise RuntimeError(
                f"Primary model {primary_model} failed and no fallback is available "
                f"for node '{node_name}'. Error: {exc}"
            ) from exc

    async def generate_json(
        self,
        prompt: str,
        system_prompt: str | None = None,
        node_name: str = "coordinator",
    ) -> str:
        model = OPENROUTER_MODELS.get(node_name, "openai/gpt-oss-120b:free")
        await self._enforce_rpm(model)

        return await asyncio.to_thread(
            self._client.generate_json,
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
        )

    async def _call(
        self,
        prompt: str,
        system_prompt: str | None,
        model: str,
        thinking: bool = False,
        temperature: float | None = None,
        node_name: str = "unknown",
        session_id: str | None = None,
        was_fallback: bool = False,
    ) -> str:
        thinking_level = "high" if thinking else None

        start_ms = int(time.time() * 1000)
        result = await asyncio.to_thread(
            self._client.generate_text,
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            thinking_level=thinking_level,
        )
        duration_ms = int(time.time() * 1000) - start_ms

        try:
            log_llm_call(
                provider="openrouter",
                model=model,
                node_name=node_name,
                was_fallback=was_fallback,
                duration_ms=duration_ms,
                session_id=session_id,
            )
        except Exception as exc:
            logger.debug("[OpenRouterAgent] log_llm_call failed: %s", exc)

        return result

    def get_rpm_status(self) -> dict:
        now = time.time()
        status = {}
        for model, timestamps in self._call_timestamps.items():
            recent = [stamp for stamp in timestamps if now - stamp < 60]
            status[model] = {
                "calls_in_window": len(recent),
                "rpm_limit": self.RPM_LIMIT,
            }
        return status
