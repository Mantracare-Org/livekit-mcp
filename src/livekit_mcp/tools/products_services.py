"""MCP tools for fetching dynamic organization products, services, and locations."""

import json
import logging
from typing import Annotated

from mcp.server.fastmcp import FastMCP

from livekit_mcp.clients.backend_client import MantraAssistBackendClient
from livekit_mcp.config import Settings, get_settings

logger = logging.getLogger(__name__)


def register_products_services_locations_tools(
    server: FastMCP,
    settings: Settings | None = None,
    backend_client: MantraAssistBackendClient | None = None,
) -> None:
    """Register organization products, services, and locations MCP tools."""
    app_settings = settings or get_settings()
    ma_client = backend_client or MantraAssistBackendClient(app_settings)

    @server.tool(
        name="get_org_products_services",
        description=(
            "Fetch active medical services, specialties, consultation types, and products offered by an organization. "
            "Use this tool to discover what services or departments are available to map against a caller's symptoms."
        ),
    )
    async def get_org_products_services(
        org_id: Annotated[int | str, "Organization ID associated with the call"],
    ) -> str:
        """Query dynamic organization products and services from backend."""
        logger.info("[MCP-TOOL] get_org_products_services called for org_id=%s", org_id)
        services = await ma_client.get_org_services(org_id=org_id)
        return json.dumps({"org_id": str(org_id), "services": services})

    @server.tool(
        name="get_org_locations",
        description=(
            "Fetch hospital/clinic branch locations for an organization. "
            "Pass optional caller_lat and caller_lng to receive distance_km calculations."
        ),
    )
    async def get_org_locations(
        org_id: Annotated[int | str, "Organization ID associated with the call"],
        caller_lat: Annotated[float | str | None, "Optional caller latitude"] = None,
        caller_lng: Annotated[float | str | None, "Optional caller longitude"] = None,
    ) -> str:
        """Query dynamic organization branch locations from backend."""
        logger.info("[MCP-TOOL] get_org_locations called for org_id=%s, lat=%s, lng=%s", org_id, caller_lat, caller_lng)
        locations = await ma_client.get_org_locations(
            org_id=org_id,
            caller_lat=caller_lat,
            caller_lng=caller_lng,
        )
        return json.dumps({"org_id": str(org_id), "locations": locations})
