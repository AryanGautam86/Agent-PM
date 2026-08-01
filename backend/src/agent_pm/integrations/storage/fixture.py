"""In-memory RAID workbook.

Seeded with a plausible log that deliberately does *not* cover every blocker in
the Jira fixture — that gap is what the gap-scan task is supposed to find, so
the offline demo exercises the real behaviour rather than a happy path.
"""

from __future__ import annotations

from agent_pm.core.logging import get_logger
from agent_pm.integrations.storage.base import RaidRow, StoredDocument

logger = get_logger(__name__)

_SEED = [
    RaidRow(
        row_ref="0",
        type="risk",
        title="Vendor SSO integration may slip past the pilot date",
        description="Third-party dependency with no committed delivery date.",
        owner="Daniel Okafor",
        status="mitigating",
        severity="high",
        mitigation="Weekly vendor sync; fallback to email OTP only for pilot.",
        source_ref="DEMO-111",
    ),
    RaidRow(
        row_ref="1",
        type="dependency",
        title="Read replica provisioning owned by platform team",
        description="Reporting migration cannot complete until the replica exists.",
        owner="Mei Lin",
        status="open",
        severity="medium",
        source_ref=None,
    ),
    RaidRow(
        row_ref="2",
        type="assumption",
        title="Client provides production data sample by end of sprint 14",
        owner="Priya Nair",
        status="open",
        severity="low",
    ),
]


class FixtureStorageClient:
    """Implements the ``DocumentStorageClient`` port, in memory."""

    name = "storage-fixture"

    def __init__(self) -> None:
        self._rows: list[RaidRow] = [row.model_copy(deep=True) for row in _SEED]
        self.saved_documents: list[StoredDocument] = []

    async def read_raid_rows(self, workbook_url: str) -> list[RaidRow]:
        return [row.model_copy(deep=True) for row in self._rows]

    async def append_raid_row(self, workbook_url: str, row: RaidRow) -> RaidRow:
        stored = row.model_copy(update={"row_ref": str(len(self._rows))})
        self._rows.append(stored)
        logger.info("raid_row_appended_simulated", extra={"title": row.title})
        return stored

    async def update_raid_row(self, workbook_url: str, row: RaidRow) -> RaidRow:
        for index, existing in enumerate(self._rows):
            if existing.row_ref == row.row_ref:
                self._rows[index] = row
                return row
        # Unknown ref: append rather than silently dropping an approved write.
        return await self.append_raid_row(workbook_url, row)

    async def save_document(
        self, folder_url: str, name: str, content_markdown: str
    ) -> StoredDocument:
        document = StoredDocument(
            url=f"memory://{folder_url or 'reports'}/{name}", name=name, created=True
        )
        self.saved_documents.append(document)
        return document

    async def aclose(self) -> None:
        return None
