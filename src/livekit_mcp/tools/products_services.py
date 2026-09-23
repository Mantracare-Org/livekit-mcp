"""Products & Services and Nearest Location tools for LiveKit MCP Server."""

import json
import logging
from typing import Any

from geopy.distance import geodesic
from geopy.geocoders import Nominatim
from mcp.server.fastmcp import FastMCP

from livekit_mcp.clients.backend_client import MantraAssistBackendClient
from livekit_mcp.clients.db_client import DatabaseClient
from livekit_mcp.config import Settings, get_settings

logger = logging.getLogger(__name__)


def register_products_services_tools(
    server: FastMCP,
    settings: Settings | None = None,
    backend_client: MantraAssistBackendClient | None = None,
    db_client: DatabaseClient | None = None,
) -> None:
    """Register product/services and nearest location calculation tools."""
    app_settings = settings or get_settings()
    ma_client = backend_client or MantraAssistBackendClient(app_settings)
    database = db_client or DatabaseClient(app_settings)

    @server.tool(
        name="get_org_products_services",
        description=(
            "Fetch the available products, healthcare services, and consultation packages for an organization. "
            "Queries the backend API and database dynamically for the given org_id."
        ),
    )
    async def get_org_products_services(org_id: int | str) -> str:
        """Fetch products and services dynamically for an organization."""
        org_id_str = str(org_id).strip()
        logger.info(f"Fetching dynamic products/services for org_id={org_id_str}")

        # 1. Query MantraAssist Backend HTTP API
        api_products = await ma_client.get_org_products_services(org_id_str)
        if api_products:
            return json.dumps({"products_services": api_products})

        # 2. Query Database if table exists
        try:
            sql_query = """
                SELECT id, name, description, category
                FROM org_products_services
                WHERE org_id = $1 AND is_active = TRUE
                ORDER BY name ASC
            """
            rows = await database.fetch(sql_query, int(org_id_str) if org_id_str.isdigit() else org_id_str)
            if rows:
                products = [
                    {
                        "product_id": r["id"],
                        "name": r["name"],
                        "description": r["description"] or "",
                        "category": r["category"] or "Healthcare Service",
                    }
                    for r in rows
                ]
                return json.dumps({"products_services": products})
        except Exception as e:
            logger.debug(f"DB query for org_products_services skipped: {e}")

        return json.dumps({"products_services": []})

    @server.tool(
        name="find_nearest_location",
        description=(
            "Calculate and find the nearest hospital/clinic branch location based on the caller's whereabouts or address. "
            "Dynamically fetches organization branch locations and uses geopy to compute geodesic distances."
        ),
    )
    async def find_nearest_location(
        user_address_or_area: str,
        org_id: int | str | None = None,
    ) -> str:
        """Find the nearest hospital or clinic branch using dynamic branch data and geopy geodesic distance."""
        user_location_str = str(user_address_or_area).strip()
        logger.info(f"Finding nearest location for caller whereabouts: '{user_location_str}' (org_id={org_id})")

        if not user_location_str:
            return "Please specify your current area, landmark, or city to find the nearest hospital location."

        branches: list[dict[str, Any]] = []

        # 1. Query backend API for org locations
        if org_id:
            api_locations = await ma_client.get_org_locations(org_id)
            if api_locations:
                branches = api_locations

        # 2. Query DB for org locations if backend returned empty
        if not branches and org_id:
            try:
                sql_query = """
                    SELECT id AS location_id, name, address, latitude, longitude
                    FROM org_locations
                    WHERE org_id = $1 AND is_active = TRUE
                """
                org_val = int(org_id) if str(org_id).isdigit() else org_id
                db_branches = await database.fetch(sql_query, org_val)
                if db_branches:
                    branches = [dict(b) for b in db_branches]
            except Exception as err:
                logger.debug(f"DB query for org_locations skipped: {err}")

        if not branches:
            return f"No registered hospital or clinic locations found for this organization to match against '{user_location_str}'."

        # Geocode user address/area using Nominatim
        user_coords = None
        try:
            geolocator = Nominatim(user_agent="mantra_voice_agent")
            loc = geolocator.geocode(user_location_str, timeout=4)
            if loc:
                user_coords = (loc.latitude, loc.longitude)
                logger.info(f"Geocoded '{user_location_str}' -> ({loc.latitude}, {loc.longitude})")
        except Exception as exc:
            logger.warning(f"Geocoding failed for '{user_location_str}': {exc}")

        calculated_results = []
        if user_coords:
            for branch in branches:
                if branch.get("latitude") and branch.get("longitude"):
                    branch_coords = (float(branch["latitude"]), float(branch["longitude"]))
                    dist_km = geodesic(user_coords, branch_coords).kilometers
                    calculated_results.append({
                        "name": branch["name"],
                        "address": branch.get("address") or "",
                        "distance_km": round(dist_km, 2),
                    })
            calculated_results.sort(key=lambda x: x["distance_km"])
        else:
            # Fallback to returning registered branch locations
            for branch in branches:
                calculated_results.append({
                    "name": branch["name"],
                    "address": branch.get("address") or "",
                    "distance_km": None,
                })

        if not calculated_results:
            return f"No hospital branches found matching '{user_location_str}'."

        nearest = calculated_results[0]
        dist_str = f" ({nearest['distance_km']} km away)" if nearest["distance_km"] is not None else ""

        response_lines = [
            f"Nearest Location: {nearest['name']}{dist_str}",
            f"Address: {nearest['address']}",
        ]
        if len(calculated_results) > 1:
            response_lines.append("\nOther Available Locations:")
            for b in calculated_results[1:]:
                d_str = f" ({b['distance_km']} km)" if b["distance_km"] is not None else ""
                response_lines.append(f"• {b['name']}{d_str} - {b['address']}")

        return "\n".join(response_lines)
