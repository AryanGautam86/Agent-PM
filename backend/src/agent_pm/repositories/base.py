"""Repository base.

Repositories are the only place that builds queries. They take a session,
return ORM instances, and never commit — transaction boundaries belong to the
service layer, so one use case is one transaction even when it touches several
aggregates.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, ClassVar, Generic, TypeVar, cast

from sqlalchemy import CursorResult, Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from agent_pm.core.errors import NotFoundError
from agent_pm.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: ClassVar[type[Any]]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---- reads -----------------------------------------------------------

    async def get(self, entity_id: uuid.UUID) -> ModelT | None:
        entity: ModelT | None = await self.session.get(self.model, entity_id)
        return entity

    async def get_or_raise(self, entity_id: uuid.UUID) -> ModelT:
        entity = await self.get(entity_id)
        if entity is None:
            raise NotFoundError(
                f"{self.model.__name__} not found",
                details={"id": str(entity_id)},
            )
        return entity

    async def find_one(self, *conditions: ColumnElement[bool]) -> ModelT | None:
        result = await self.session.execute(select(self.model).where(*conditions).limit(1))
        entity: ModelT | None = result.scalar_one_or_none()
        return entity

    async def find_many(
        self,
        *conditions: ColumnElement[bool],
        order_by: Any | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> Sequence[ModelT]:
        stmt: Select[tuple[Any]] = select(self.model)
        if conditions:
            stmt = stmt.where(*conditions)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset:
            stmt = stmt.offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()  # type: ignore[no-any-return]

    async def count(self, *conditions: ColumnElement[bool]) -> int:
        stmt = select(func.count()).select_from(self.model)
        if conditions:
            stmt = stmt.where(*conditions)
        return int((await self.session.execute(stmt)).scalar_one())

    async def exists(self, *conditions: ColumnElement[bool]) -> bool:
        return await self.count(*conditions) > 0

    # ---- writes ----------------------------------------------------------

    def add(self, entity: ModelT) -> ModelT:
        """Stage an insert. The service commits."""
        self.session.add(entity)
        return entity

    async def flush(self) -> None:
        """Force SQL now — needed when a generated id is required downstream."""
        await self.session.flush()

    async def remove(self, entity: ModelT) -> None:
        await self.session.delete(entity)

    async def remove_where(self, *conditions: ColumnElement[bool]) -> int:
        # DELETE always yields a CursorResult; only that subclass exposes
        # rowcount, which the generic Result protocol does not promise.
        result = cast(
            CursorResult[Any],
            await self.session.execute(delete(self.model).where(*conditions)),
        )
        return int(result.rowcount or 0)


class EngagementScopedRepository(BaseRepository[ModelT]):
    """For tables that belong to exactly one engagement.

    Every read goes through ``engagement_id``. Tenancy is not something a
    caller can forget to apply, because there is no unscoped list method.
    """

    async def list_for_engagement(
        self,
        engagement_id: uuid.UUID,
        *conditions: ColumnElement[bool],
        order_by: Any | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> Sequence[ModelT]:
        return await self.find_many(
            self.model.engagement_id == engagement_id,
            *conditions,
            order_by=order_by,
            limit=limit,
            offset=offset,
        )

    async def get_for_engagement(
        self, engagement_id: uuid.UUID, entity_id: uuid.UUID
    ) -> ModelT:
        entity = await self.find_one(
            self.model.id == entity_id,
            self.model.engagement_id == engagement_id,
        )
        if entity is None:
            raise NotFoundError(
                f"{self.model.__name__} not found in this engagement",
                details={"id": str(entity_id)},
            )
        return entity
