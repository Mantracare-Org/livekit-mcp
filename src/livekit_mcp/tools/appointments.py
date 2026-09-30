"""Appointment listing, cancellation, and rescheduling MCP tool."""

import json
import logging
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP

from livekit_mcp.clients.backend_client import MantraAssistBackendClient
from livekit_mcp.config import Settings, get_settings

logger = logging.getLogger(__name__)


def register_appointment_tool(
    server: FastMCP,
    settings: Settings | None = None,
    backend_client: MantraAssistBackendClient | None = None,
) -> None:
    """Register the appointment management tool."""
    app_settings = settings or get_settings()
    ma_client = backend_client or MantraAssistBackendClient(app_settings)

    @server.tool(
        name="manage_appointments",
        description=(
            "Manage appointments for a recognized inbound client. Use action=list to retrieve the client's "
            "appointments, action=availability to check possible rescheduling slots, action=cancel to cancel "
            "a selected appointment, or action=reschedule to submit a selected appointment with a new date/time."
        ),
    )
    async def manage_appointments(
        action: Annotated[str, "One of: list, availability, cancel, reschedule"],
        org_id: Annotated[int | str, "Organization ID"],
        user_id: Annotated[int | str, "Recognized client's user ID"],
        appointment_id: Annotated[int | str | None, "Selected appointment ID"] = None,
        appointment_title: Annotated[str | None, "Selected appointment title"] = None,
        requested_date: Annotated[str | None, "Date for checking available rescheduling slots, YYYY-MM-DD"] = None,
        new_datetime: Annotated[str | None, "New appointment date/time in UTC ISO-8601 format"] = None,
    ) -> str:
        """Execute an appointment action for a recognized client."""
        normalized_action = str(action).strip().lower()
        if normalized_action not in {"list", "availability", "cancel", "reschedule"}:
            return json.dumps({"status": "error", "message": "Unsupported appointment action."})
        if normalized_action in {"cancel", "reschedule"} and appointment_id in (None, ""):
            return json.dumps({"status": "error", "message": "appointment_id is required."})
        if normalized_action == "reschedule" and not new_datetime:
            return json.dumps({"status": "error", "message": "new_datetime is required."})

        logger.info(
            "[MCP-TOOL] manage_appointments action=%s org_id=%s user_id=%s appointment_id=%s",
            normalized_action,
            org_id,
            user_id,
            appointment_id,
        )
        result: Any = await ma_client.manage_appointments(
            action=normalized_action,
            org_id=org_id,
            user_id=user_id,
            appointment_id=appointment_id,
            appointment_title=appointment_title,
            requested_date=requested_date,
            new_datetime=new_datetime,
        )
        return json.dumps(result, default=str)
