"""Shared response shapes."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

ItemT = TypeVar("ItemT")


class ORMModel(BaseModel):
    """Base for schemas built from ORM rows."""

    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[ItemT]):
    items: list[ItemT]
    total: int | None = None
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.total is not None and self.offset + len(self.items) < self.total


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class Acknowledgement(BaseModel):
    ok: bool = True
    message: str | None = None


class HealthStatus(BaseModel):
    status: str
    environment: str
    version: str = "0.1.0"
    database: str | None = None
    integrations: dict[str, str] = Field(default_factory=dict)
    scheduler: str | None = None
