"""Client recognition tool for inbound caller context."""

import json
import logging
import re
from typing import Annotated

from mcp.server.fastmcp import FastMCP

from livekit_mcp.clients.backend_client import MantraAssistBackendClient
from livekit_mcp.config import Settings, get_settings

logger = logging.getLogger(__name__)


def normalize_phone_number(phone_number: str) -> str:
    """Normalize the caller number to the E.164-style format used by MA."""
    value = str(phone_number or "").strip()
    if value.startswith("+"):
        return "+" + re.sub(r"\D", "", value)

    digits = re.sub(r"\D", "", value)
    if len(digits) == 10:
        return f"+91{digits}"
    return f"+{digits}" if digits else ""


def register_client_recognition_tool(
    server: FastMCP,
    settings: Settings | None = None,
    backend_client: MantraAssistBackendClient | None = None,
) -> None:
    """Register the inbound client recognition tool."""
    app_settings = settings or get_settings()
    ma_client = backend_client or MantraAssistBackendClient(app_settings)

    @server.tool(
        name="recognize_client",
        description=(
            "Identify an inbound caller by organization and phone number before the greeting. "
            "Returns client_name and user_id when registered; both are null for an anonymous caller."
        ),
    )
    async def recognize_client(
        org_id: Annotated[int | str, "Organization ID associated with the inbound phone number"],
        phone_number: Annotated[str, "Inbound caller phone number, preferably in E.164 format"],
    ) -> str:
        """Return the registered client identity or null fields for anonymous callers."""
        normalized_phone = normalize_phone_number(phone_number)
        logger.info(
            "[MCP-TOOL] recognize_client called for org_id=%s, phone=%s",
            org_id,
            normalized_phone,
        )
        result = await ma_client.recognize_client(
            org_id=org_id,
            phone_number=normalized_phone,
        )
        return json.dumps(
            {
                "client_name": result.get("client_name") if result else None,
                "user_id": result.get("user_id") if result else None,
            }
        )
