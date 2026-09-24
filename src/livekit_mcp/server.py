"""Server factory and application builder for LiveKit MCP Server."""

import json
import logging
import os
import sys
from datetime import UTC, datetime

from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Route

from livekit_mcp.auth.middleware import AuthMiddleware
from livekit_mcp.config import Settings, get_settings
from livekit_mcp.routes.api import get_api_routes
from livekit_mcp.tools.appointments import register_appointment_tool
from livekit_mcp.tools.client_recognition import register_client_recognition_tool
from livekit_mcp.tools.doctor_availability import register_doctor_availability_tool
from livekit_mcp.tools.org_processes import register_org_processes_tool
from livekit_mcp.tools.providers import register_provider_tools
from livekit_mcp.utils.db_logger import save_mcp_event

_proc_type = "MCP Server"
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(
    logging.Formatter(
        f"%(asctime)s INFO (Type: {_proc_type}, PID: {os.getpid()}) %(name)s: %(message)s"
    )
)
logging.basicConfig(level=logging.INFO, handlers=[_handler])

logger = logging.getLogger(__name__)

# Track server startup time for dashboard uptime display
STARTUP_TIME = datetime.now(UTC)

def create_mcp_server(settings: Settings | None = None) -> FastMCP:
    """Create and configure the underlying FastMCP server instance."""
    app_settings = settings or get_settings()

    server = FastMCP(
        name="livekit-mcp",
        instructions=(
            "LiveKit MCP Server provides tools to interact with the MantraCare "
            "voice agent engine, telephony trunks, call logs, knowledge base, "
            "organization processes & stages, and healthcare provider availability schedules."
        ),
    )

    # Register tools
    register_org_processes_tool(server, settings=app_settings)
    register_provider_tools(server, settings=app_settings)
    register_doctor_availability_tool(server, settings=app_settings)
    register_client_recognition_tool(server, settings=app_settings)
    register_appointment_tool(server, settings=app_settings)

    return server


def create_app(settings: Settings | None = None) -> Starlette:
    """Create the full Starlette application with official SSE transport and auth middleware."""
    app_settings = settings or get_settings()
    server = create_mcp_server(app_settings)

    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request) -> Response:
        import asyncio
        asyncio.create_task(
            save_mcp_event(
                event_type="sse_connected",
                event_source="handle_sse",
                event_payload={"client": request.client.host if request.client else "unknown"}
            )
        )
        async with sse.connect_sse(request.scope, request.receive, request._send) as (read_stream, write_stream):
            await server._mcp_server.run(
                read_stream,
                write_stream,
                server._mcp_server.create_initialization_options(),
            )
        return Response()

    api_routes = get_api_routes(server, app_settings, STARTUP_TIME)

    routes = [
        Route("/sse", endpoint=handle_sse),
        Mount("/messages", app=sse.handle_post_message),
    ] + api_routes

    app = Starlette(routes=routes)

    # Add AuthMiddleware
    app.add_middleware(AuthMiddleware, settings=app_settings)

    return app
