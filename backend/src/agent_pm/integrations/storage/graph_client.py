"""SharePoint / Excel adapter over Microsoft Graph.

Requires an Entra app registration with application permissions
``Sites.ReadWrite.All`` and ``Files.ReadWrite.All``, admin-consented.

The workbook must contain a **named table** (default ``RAIDLog``) — Graph's
table API is row-addressable, whereas the range API is not, and stable row
addressing is what makes an approved update land on the row it was approved for.

Untested against a live tenant: the shapes follow the documented Graph
workbook API, but nothing here has run against real SharePoint. Treat the first
run as an integration test.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from dateutil import parser as date_parser

from agent_pm.core.clock import utc_now
from agent_pm.core.config import Settings
from agent_pm.core.errors import IntegrationError, IntegrationNotConfiguredError
from agent_pm.core.logging import get_logger
from agent_pm.integrations.base import HttpIntegration
from agent_pm.integrations.storage.base import (
    RAID_COLUMNS,
    RaidRow,
    StoredDocument,
    row_to_values,
)

logger = get_logger(__name__)

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
DEFAULT_TABLE = "RAIDLog"

# https://contoso.sharepoint.com/sites/<site>/... /<file>.xlsx
SHAREPOINT_URL = re.compile(r"https://(?P<host>[^/]+)/sites/(?P<site>[^/]+)/(?P<path>.+)$")


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date_parser.parse(value).date()
    except (ValueError, TypeError):
        return None


class GraphStorageClient(HttpIntegration):
    name = "sharepoint"

    def __init__(self, settings: Settings, *, table_name: str = DEFAULT_TABLE) -> None:
        if not (
            settings.teams_tenant_id and settings.teams_client_id and settings.teams_client_secret
        ):
            raise IntegrationNotConfiguredError(
                "sharepoint",
                "Graph credentials (TEAMS_TENANT_ID / TEAMS_CLIENT_ID / "
                "TEAMS_CLIENT_SECRET) are required for workbook access",
            )
        super().__init__(headers={"Content-Type": "application/json"})
        self._tenant = settings.teams_tenant_id
        self._client_id = settings.teams_client_id
        self._client_secret = settings.teams_client_secret
        self._table = table_name
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    # ---- auth ------------------------------------------------------------

    async def _access_token(self) -> str:
        now = utc_now().timestamp()
        if self._token and now < self._token_expires_at - 60:
            return self._token

        # The token endpoint is form-encoded, so it bypasses self.request()
        # (which is JSON-only) and goes straight to the underlying client.
        response = await self._client.post(
            f"https://login.microsoftonline.com/{self._tenant}/oauth2/v2.0/token",
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.status_code >= 400:
            raise IntegrationError(
                "sharepoint", f"token request failed: {response.status_code}"
            )
        payload = response.json()
        self._token = str(payload["access_token"])
        self._token_expires_at = now + float(payload.get("expires_in", 3600))
        return self._token

    async def _graph(self, method: str, path: str, **kwargs: Any) -> Any:
        token = await self._access_token()
        self._client.headers["Authorization"] = f"Bearer {token}"
        return await self.request(method, f"{GRAPH_ROOT}{path}", **kwargs)

    # ---- addressing ------------------------------------------------------

    async def _table_path(self, workbook_url: str) -> str:
        match = SHAREPOINT_URL.match(workbook_url)
        if not match:
            raise IntegrationError(
                "sharepoint",
                "Workbook URL must look like "
                "https://<tenant>.sharepoint.com/sites/<site>/<path>.xlsx",
                details={"url": workbook_url},
            )
        host, site, path = match.group("host"), match.group("site"), match.group("path")
        site_info = await self._graph("GET", f"/sites/{host}:/sites/{site}")
        site_id = site_info["id"]
        return f"/sites/{site_id}/drive/root:/{path}:/workbook/tables/{self._table}"

    # ---- reads -----------------------------------------------------------

    async def read_raid_rows(self, workbook_url: str) -> list[RaidRow]:
        base = await self._table_path(workbook_url)
        header = await self._graph("GET", f"{base}/headerRowRange")
        columns = [str(name) for name in (header.get("values") or [[]])[0]]
        payload = await self._graph("GET", f"{base}/rows")

        rows: list[RaidRow] = []
        for entry in payload.get("value", []):
            values = (entry.get("values") or [[]])[0]
            record = {
                column: str(value) if value is not None else ""
                for column, value in zip(columns, values, strict=False)
            }
            rows.append(
                RaidRow(
                    row_ref=str(entry.get("index")),
                    type=record.get("Type", "risk").lower(),
                    title=record.get("Title", ""),
                    description=record.get("Description") or None,
                    owner=record.get("Owner") or None,
                    status=(record.get("Status") or "").lower() or None,
                    severity=(record.get("Severity") or "").lower() or None,
                    mitigation=record.get("Mitigation") or None,
                    due_date=_parse_date(record.get("Due Date")),
                    source_ref=record.get("Source") or None,
                    raw=record,
                )
            )
        return rows

    # ---- writes ----------------------------------------------------------

    async def append_raid_row(self, workbook_url: str, row: RaidRow) -> RaidRow:
        base = await self._table_path(workbook_url)
        result = await self._graph(
            "POST", f"{base}/rows/add", json={"values": [row_to_values(row)]}
        )
        logger.info("raid_row_appended", extra={"title": row.title})
        return row.model_copy(update={"row_ref": str(result.get("index"))})

    async def update_raid_row(self, workbook_url: str, row: RaidRow) -> RaidRow:
        if row.row_ref is None:
            raise IntegrationError("sharepoint", "update_raid_row needs a row_ref")
        base = await self._table_path(workbook_url)
        await self._graph(
            "PATCH",
            f"{base}/rows/itemAt(index={row.row_ref})",
            json={"values": [row_to_values(row)]},
        )
        return row

    async def save_document(
        self, folder_url: str, name: str, content_markdown: str
    ) -> StoredDocument:
        raise IntegrationNotConfiguredError(
            "sharepoint",
            "Publishing reports to SharePoint is not implemented. Reports are "
            "stored in the database and served by the API; wire "
            "PUT /drive/root:/{path}:/content here when a document library is "
            "chosen.",
            details={"folder_url": folder_url, "name": name},
        )


__all__ = ["RAID_COLUMNS", "GraphStorageClient"]
