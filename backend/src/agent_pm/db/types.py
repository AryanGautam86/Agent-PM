"""Custom SQLAlchemy column types."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from sqlalchemy import Dialect, String
from sqlalchemy.types import TypeDecorator


class StrEnumType(TypeDecorator[StrEnum]):
    """Stores a ``StrEnum`` as VARCHAR and reads it back as the enum.

    Chosen over ``sa.Enum`` on purpose: no Postgres enum type and no CHECK
    constraint, so adding a new autonomy level or RAID status is a code change
    rather than a migration that rewrites a type. The trade-off is that the
    database will accept an unknown string written by something other than this
    application; reads of such a row raise ``ValueError``, which is the
    behaviour we want (loud, not silent).
    """

    impl = String
    cache_ok = True

    def __init__(self, enum_class: type[StrEnum], length: int = 32) -> None:
        self.enum_class = enum_class
        super().__init__(length=length)

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if isinstance(value, self.enum_class):
            return value.value
        return self.enum_class(value).value

    def process_result_value(self, value: Any, dialect: Dialect) -> StrEnum | None:
        if value is None:
            return None
        return self.enum_class(value)
