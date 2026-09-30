"""Doctor / Provider availability tool querying MantraAssist-backend HTTP endpoint with timezone localization."""

from datetime import datetime
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from livekit_mcp.clients.backend_client import MantraAssistBackendClient
from livekit_mcp.clients.db_client import DatabaseClient
from livekit_mcp.config import Settings, get_settings
from livekit_mcp.utils.timezone import convert_utc_slot_to_local, get_timezone_from_phone, resolve_date_string

logger = logging.getLogger(__name__)


def register_doctor_availability_tool(
    server: FastMCP,
    settings: Settings | None = None,
    backend_client: MantraAssistBackendClient | None = None,
    db_client: DatabaseClient | None = None,
) -> None:
    """Register doctor availability tool with the MCP server."""
    app_settings = settings or get_settings()
    ma_client = backend_client or MantraAssistBackendClient(app_settings)
    database = db_client or DatabaseClient(app_settings)

    @server.tool(
        name="receive_doctor_availability",
        description=(
            "Check and retrieve doctor availability, working hours, and open consultation slots for an organization. "
            "Queries the MantraAssist-backend HTTP API endpoint (/v1/providers/availability) with optional doctor name, "
            "product/service, hospital branch location, and medical department, auto-detecting caller timezone and location shifts."
        ),
    )
    async def receive_doctor_availability(
        user_id: int | str | None = None,
        org_id: int | str | None = None,
        name: str | None = None,
        date: str | None = None,
        department: str | None = None,
        product_service: str | None = None,
        location: str | None = None,
        available_slots: list[str] | None = None,
        providers: list[dict[str, Any]] | None = None,
        caller_phone: str | None = None,
        timezone: str | None = None,
    ) -> str:
        """Process and format availability for doctors/providers.

        If providers or available_slots are passed directly, formats them.
        Otherwise, hits the MantraAssist-backend HTTP endpoint to fetch real-time slots.
        """
        effective_org_id = org_id if org_id is not None else ""
        target_date_str = str(date or datetime.now().strftime("%Y-%m-%d")).strip()
        dept_str = str(department).strip() if department and str(department).strip() else ""
        prod_str = str(product_service).strip() if product_service and str(product_service).strip() else ""
        loc_str = str(location).strip() if location and str(location).strip() else ""

        # 1. Resolve target timezone: explicit > phone number detection > default (Asia/Kolkata)
        if timezone and timezone.strip():
            target_tz = timezone.strip()
        elif caller_phone and caller_phone.strip():
            target_tz = get_timezone_from_phone(caller_phone, default_tz="Asia/Kolkata")
        else:
            target_tz = "Asia/Kolkata"

        # 2. Parse target date (handles 'today', 'tomorrow', '2026-08-25', etc.)
        target_date = resolve_date_string(target_date_str, source_tz_str=target_tz)
        formatted_date_str = target_date.strftime("%A, %b %d, %Y")
        target_date_str = target_date.strftime("%Y-%m-%d")

        # 3. Determine provider list
        provider_list: list[dict[str, Any]] = []

        # A. Pre-supplied in arguments
        if providers and isinstance(providers, list):
            provider_list = providers
        elif name and available_slots is not None:
            provider_list = [
                {
                    "user_id": user_id,
                    "name": name,
                    "available_slots": available_slots,
                }
            ]
        else:
            # B. Query MantraAssist Backend HTTP API Endpoint
            logger.info(
                "Fetching availability from MantraAssist backend API: org_id=%s, date=%s, doctor=%s, department=%s",
                effective_org_id,
                target_date_str,
                name,
                dept_str,
            )
            backend_providers = await ma_client.get_doctor_availability(
                org_id=effective_org_id,
                date=target_date_str,
                doctor_name=name,
                department=dept_str,
                caller_phone=caller_phone,
                caller_tz=target_tz,
            )

            if backend_providers is not None and len(backend_providers) > 0:
                provider_list = backend_providers
            else:
                # C. Optional DB Fallback if backend API is not yet running
                logger.info("Attempting direct database fallback for org_id=%s", effective_org_id)
                try:
                    pool = await database.get_pool()
                    async with pool.acquire() as conn:
                        rows = await conn.fetch(
                            """
                            SELECT
                                p.id AS provider_id,
                                p.name AS provider_name,
                                p.specialization,
                                pa.start_time,
                                pa.end_time
                            FROM provider_availability pa
                            INNER JOIN providers p ON p.id = pa.provider_id
                            WHERE pa.org_id::text = $1::text
                              AND ($2::text IS NULL OR p.name ILIKE '%' || $2 || '%')
                              AND ($3::text IS NULL OR p.specialization ILIKE '%' || $3 || '%')
                            ORDER BY p.name ASC, pa.start_time ASC
                            """,
                            str(effective_org_id),
                            name.strip() if name else None,
                            dept_str if dept_str else None,
                        )
                        for r in rows:
                            st = r["start_time"].strftime("%H:%M") if r["start_time"] else "09:00"
                            et = r["end_time"].strftime("%H:%M") if r["end_time"] else "17:00"
                            provider_list.append(
                                {
                                    "user_id": r["provider_id"],
                                    "name": r["provider_name"],
                                    "department": r["specialization"] or "",
                                    "available_slots": [f"{st} - {et}"],
                                }
                            )
                except Exception as db_err:
                    logger.debug("Database fallback check skipped: %s", db_err)

        logger.info(
            "Formatting availability response: org_id=%s, date=%s, count=%d, phone=%s, resolved_tz=%s",
            effective_org_id,
            target_date_str,
            len(provider_list),
            caller_phone,
            target_tz,
        )

        dept_label = f" in {dept_str}" if dept_str else ""
        if not provider_list:
            return f"No doctor availability information found{dept_label} on {formatted_date_str}."

        lines = []

        # 4. Format each provider and localize slots
        for provider in provider_list:
            doc_name = provider.get("name") or provider.get("provider_name") or "Doctor"
            uid = provider.get("user_id") or provider.get("id") or provider.get("provider_id")
            uid_str = f" (User ID: {uid})" if uid is not None else ""
            raw_slots = provider.get("available_slots", [])

            if raw_slots:
                local_slots = []
                for slot in raw_slots:
                    slot_str = str(slot).strip()
                    # If already formatted with AM/PM (e.g. '10:00 AM – 11:00 AM'), keep as-is
                    if "AM" in slot_str.upper() or "PM" in slot_str.upper():
                        local_slots.append(slot_str)
                    else:
                        local_slots.append(
                            convert_utc_slot_to_local(
                                slot_str=slot_str,
                                target_date=target_date,
                                target_tz_str=target_tz,
                            )
                        )
                slots_text = ", ".join(local_slots)
                lines.append(f"{doc_name}{uid_str} is available on {formatted_date_str}: {slots_text}.")
            else:
                lines.append(f"{doc_name}{uid_str} has no open appointment slots on {formatted_date_str}.")

        return "\n".join(lines)
