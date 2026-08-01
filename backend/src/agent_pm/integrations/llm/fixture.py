"""Deterministic LLM stand-in.

Runs when ``ANTHROPIC_API_KEY`` is unset. It does not imitate a model — it
fills the requested schema from the *evidence already in the prompt*, so
offline output is always perfectly grounded and unit tests assert on structure
rather than on prose.

Because it never invents a citation, a grounding failure in a test run means
the task's own wiring is wrong, not that the model misbehaved. That is the
point of having it.
"""

from __future__ import annotations

import json
import re
from typing import Any

from agent_pm.core.logging import get_logger
from agent_pm.integrations.llm.base import LLMMessage, LLMResponse

logger = get_logger(__name__)

EVIDENCE_BLOCK = re.compile(r"<evidence>(.*?)</evidence>", re.DOTALL)


class FixtureLLMClient:
    """Implements :class:`~agent_pm.integrations.llm.base.LLMClient`."""

    name = "llm-fixture"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        model: str,
        max_tokens: int = 4096,
        temperature: float | None = None,
    ) -> LLMResponse:
        self.calls.append({"kind": "text", "model": model, "system": system})
        prompt = messages[-1].content if messages else ""
        evidence = self._evidence(prompt)
        body = "\n".join(f"- {line}" for line in evidence[:10]) or "- No activity recorded."
        text = (
            "_Generated offline without a model; every line below is copied "
            "verbatim from the supplied evidence._\n\n" + body
        )
        return LLMResponse(
            text=text,
            model=f"fixture:{model}",
            input_tokens=len(prompt) // 4,
            output_tokens=len(text) // 4,
            stop_reason="end_turn",
        )

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
        self.calls.append({"kind": "json", "model": model, "schema": schema_name})
        prompt = messages[-1].content if messages else ""
        data = self._fill(schema, self._evidence(prompt))
        return LLMResponse(
            data=data,
            model=f"fixture:{model}",
            input_tokens=len(prompt) // 4,
            output_tokens=len(json.dumps(data)) // 4,
            stop_reason="tool_use",
        )

    # ---- internals -------------------------------------------------------

    @staticmethod
    def _evidence(prompt: str) -> list[str]:
        """Lines inside the prompt's <evidence> block.

        Every task prompt wraps its facts in that tag precisely so this client
        can echo them instead of inventing anything.
        """
        block = EVIDENCE_BLOCK.search(prompt)
        if not block:
            return []
        return [line.strip("- ").strip() for line in block.group(1).splitlines() if line.strip()]

    def _fill(self, schema: dict[str, Any], evidence: list[str]) -> dict[str, Any]:
        """Produce the smallest object that satisfies ``schema``."""
        result: dict[str, Any] = {}
        properties: dict[str, Any] = schema.get("properties", {})
        required: list[str] = schema.get("required", list(properties))

        for name, spec in properties.items():
            if name not in required:
                continue
            result[name] = self._value_for(name, spec, evidence)
        return result

    def _value_for(self, name: str, spec: dict[str, Any], evidence: list[str]) -> Any:
        kind = spec.get("type", "string")

        if kind == "string":
            if "summary" in name or "markdown" in name or "narrative" in name:
                lines = "\n".join(f"- {line}" for line in evidence[:10])
                return f"Offline summary (evidence verbatim):\n{lines}"
            return evidence[0] if evidence else ""
        if kind == "integer":
            return 0
        if kind == "number":
            return 0.0
        if kind == "boolean":
            return False
        if kind == "array":
            items = spec.get("items", {})
            if items.get("type") == "object":
                return []
            return []
        if kind == "object":
            return self._fill(spec, evidence)
        return None

    async def aclose(self) -> None:
        return None
