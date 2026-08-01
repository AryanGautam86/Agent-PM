"""Anthropic adapter.

Model ids are configuration (``ANTHROPIC_MODEL_STRUCTURED`` /
``ANTHROPIC_MODEL_NARRATIVE``), never literals in task code — a task declares a
:class:`~agent_pm.core.enums.ModelTier` and the registry resolves it. Swapping
to a newer model is then an environment change.

Structured output uses a forced tool call rather than "reply with JSON":
the API validates the arguments against the schema, so malformed output is
retried by the provider instead of arriving here as a parse error.
"""

from __future__ import annotations

from typing import Any

import anthropic
from anthropic import AsyncAnthropic

from agent_pm.core.config import Settings
from agent_pm.core.errors import IntegrationError, RateLimitedError
from agent_pm.core.logging import get_logger
from agent_pm.integrations.llm.base import LLMMessage, LLMResponse

logger = get_logger(__name__)


class AnthropicClient:
    """Implements :class:`~agent_pm.integrations.llm.base.LLMClient`."""

    name = "anthropic"

    def __init__(self, settings: Settings) -> None:
        if not settings.anthropic_configured:
            raise IntegrationError("anthropic", "ANTHROPIC_API_KEY is not configured")
        self._client = AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.anthropic_timeout_seconds,
            max_retries=2,
        )
        self._default_max_tokens = settings.anthropic_max_tokens

    async def complete(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        model: str,
        max_tokens: int = 4096,
        temperature: float | None = None,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens or self._default_max_tokens,
            "system": system,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if temperature is not None:
            payload["temperature"] = temperature

        response = await self._call(payload)
        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
        return self._to_response(response, text=text)

    async def complete_json(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        model: str,
        schema: dict[str, Any],
        schema_name: str = "result",
        max_tokens: int = 4096,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens or self._default_max_tokens,
            "system": system,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "tools": [
                {
                    "name": schema_name,
                    "description": "Return the result in this exact structure.",
                    "input_schema": schema,
                }
            ],
            "tool_choice": {"type": "tool", "name": schema_name},
        }

        response = await self._call(payload)
        for block in response.content:
            if getattr(block, "type", "") == "tool_use":
                data = dict(block.input) if isinstance(block.input, dict) else {}
                return self._to_response(response, data=data)

        raise IntegrationError(
            "anthropic",
            "Model did not return the required structured output",
            details={"stop_reason": response.stop_reason},
        )

    # ---- internals -------------------------------------------------------

    async def _call(self, payload: dict[str, Any]) -> Any:
        try:
            return await self._client.messages.create(**payload)
        except anthropic.RateLimitError as exc:
            raise RateLimitedError("Anthropic rate limit reached") from exc
        except anthropic.APIStatusError as exc:
            raise IntegrationError(
                "anthropic",
                f"API returned {exc.status_code}",
                details={"body": str(exc)[:500]},
            ) from exc
        except anthropic.APIError as exc:
            raise IntegrationError("anthropic", str(exc)) from exc

    @staticmethod
    def _to_response(
        response: Any, *, text: str = "", data: dict[str, Any] | None = None
    ) -> LLMResponse:
        usage = getattr(response, "usage", None)
        return LLMResponse(
            text=text,
            data=data or {},
            model=str(getattr(response, "model", "")),
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            stop_reason=getattr(response, "stop_reason", None),
        )

    async def aclose(self) -> None:
        await self._client.close()
