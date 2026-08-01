"""LLM port.

Two shapes only:

* :meth:`LLMClient.complete` — free-form prose (the weekly narrative).
* :meth:`LLMClient.complete_json` — a validated object matching a JSON schema.

Agent tasks use ``complete_json`` almost exclusively. Parsing prose into
structure is where hallucinated fields creep in; forcing the model to fill a
schema keeps the grounding check meaningful, because citations arrive as data
rather than as text to be scraped.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class LLMResponse(BaseModel):
    text: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str | None = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@runtime_checkable
class LLMClient(Protocol):
    async def complete(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        model: str,
        max_tokens: int = 4096,
        temperature: float | None = None,
    ) -> LLMResponse:
        """Free-form completion."""
        ...

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
        """Completion constrained to ``schema``; result lands in ``.data``."""
        ...

    async def aclose(self) -> None: ...
