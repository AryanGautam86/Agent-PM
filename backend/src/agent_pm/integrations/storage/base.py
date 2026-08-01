"""Document storage port — the RAID workbook and generated reports.

The RAID log stays a spreadsheet because that is the artefact the client reads.
This port is the two-way bridge between that workbook and ``raid_items``.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class RaidRow(BaseModel):
    """One row of the RAID workbook, normalised.

    ``row_ref`` is whatever the adapter needs to find the row again — a table
    row index for Excel. It is opaque to the rest of the application.
    """

    row_ref: str | None = None
    type: str
    title: str
    description: str | None = None
    owner: str | None = None
    status: str | None = None
    severity: str | None = None
    mitigation: str | None = None
    due_date: date | None = None
    source_ref: str | None = None
    raw: dict[str, str] = Field(default_factory=dict)


class StoredDocument(BaseModel):
    url: str
    name: str
    created: bool


@runtime_checkable
class DocumentStorageClient(Protocol):
    async def read_raid_rows(self, workbook_url: str) -> list[RaidRow]:
        """Every row currently in the workbook."""
        ...

    async def append_raid_row(self, workbook_url: str, row: RaidRow) -> RaidRow:
        """Add a row. Only ever called from an approved payload."""
        ...

    async def update_raid_row(self, workbook_url: str, row: RaidRow) -> RaidRow:
        """Update a row identified by ``row_ref``. Approved payloads only."""
        ...

    async def save_document(
        self, folder_url: str, name: str, content_markdown: str
    ) -> StoredDocument:
        """Publish a generated report."""
        ...

    async def aclose(self) -> None: ...


# Column order used when writing. Matches the header row the fixture produces;
# a real workbook's headers are read at runtime and mapped by name.
RAID_COLUMNS = [
    "Type",
    "Title",
    "Description",
    "Owner",
    "Status",
    "Severity",
    "Mitigation",
    "Due Date",
    "Source",
]


def row_to_values(row: RaidRow) -> list[str]:
    return [
        row.type,
        row.title,
        row.description or "",
        row.owner or "",
        row.status or "",
        row.severity or "",
        row.mitigation or "",
        row.due_date.isoformat() if row.due_date else "",
        row.source_ref or "",
    ]
