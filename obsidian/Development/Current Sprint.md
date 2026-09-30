# Current Sprint

> **Sprint:** 0.3.0 Production Dockerization & Org Processes Integration  
> **Last Updated:** 2026-08-29  
> **Status:** Active

- [x] **Inbound Client Recognition MCP Tool (2026-09-07):** Added `recognize_client` to normalize the inbound caller number and query the MA backend with `org_id` plus phone number. The livekit agent calls this tool before greeting and treats `null`, timeout, or backend failure as an anonymous caller. Backend endpoint contract: `POST /api/v1/webhooks/client-recognition`.

- [x] **Appointment Management MCP Tool (2026-09-11):** Added `manage_appointments` with `list`, `availability`, `cancel`, and `reschedule` actions for recognized clients. Uses provisional backend route `/v1/webhooks/appointments`, isolated in `MantraAssistBackendClient.manage_appointments()` for later replacement.

- [x] **Production Docker Build & Exec Fix (2026-09-01):** Resolved `exec /app/.venv/bin/livekit-mcp: no such file or directory` by enforcing `UV_PYTHON=/usr/local/bin/python3.12` in `Dockerfile`. Added `docker-compose.yml` with `env_file: .env` and fixed `DATABASE_URL` format.
- [x] **Production Environment Config (2026-08-30):** Created dedicated production environment file `.env.prod` with `ENVIRONMENT=production`, secure JWT secret configuration, and production service URLs. Files: `.env.prod`.
- [x] **Production Multi-Stage Dockerfile (2026-08-29):** Created production Dockerfile using `ghcr.io/astral-sh/uv:python3.12-bookworm-slim`, unprivileged `appuser` (UID 10001), layer caching, runtime healthcheck, and direct binary CMD execution. Files: `Dockerfile`.
- [x] **Organization Processes & Stages Tool (`fetch_org_processes`) (2026-08-27):** Implemented `fetch_org_processes` (and alias `receive_org_processes`) with 10-min in-memory TTL caching querying `MantraAssist-backend`. Files: `src/livekit_mcp/tools/org_processes.py`, `src/livekit_mcp/clients/backend_client.py`.
- [x] **Doctor `provider_user_id` Injection (2026-08-27):** Added doctor user IDs into `receive_doctor_availability` output for automatic post-call appointment resolution. Files: `src/livekit_mcp/tools/doctor_availability.py`.
- [x] **Unauthenticated Backend Client (2026-08-27):** Removed `x-client-id` and `x-client-secret` headers from `MantraAssistBackendClient`. Files: `src/livekit_mcp/clients/backend_client.py`.
- [x] **JSON Root Status Endpoint (2026-08-27):** Replaced static landing page with lightweight JSON response. Files: `src/livekit_mcp/routes/api.py`.
- [x] **Agentic Memory Infrastructure (2026-08-20):** Created `AGENTS.md` and full Obsidian knowledge vault (`obsidian/`) replicating the agentic memory pattern from `~/lkt`.
- [x] **Shared JWT Authentication (2026-08-20):** Implemented HS256 JWT validation and pure ASGI middleware supporting header and query parameter token injection compatible with `mantra-auth`.
- [x] **MCP Server Core & SSE Transport (2026-08-20):** Set up `MCPServer` with `/sse`, `/messages`, `/health`, and `/api/tools/call` endpoints.
- [x] **Greeting Test Tool (2026-08-20):** Implemented typed, documented `greet_user` tool for end-to-end verification.
- [x] **Provider Availability Search Tool (2026-08-21):** Implemented `search_provider_availability` tool in `src/livekit_mcp/tools/providers.py` with direct PostgreSQL connection pool (`DatabaseClient`), UTC-to-local timezone conversion (`zoneinfo.ZoneInfo`), and RFC 5545 recurrence rule matching against `assist_db`.
- [x] **Doctor Availability Receiver Tool (2026-08-22):** Implemented `receive_doctor_availability` tool in `src/livekit_mcp/tools/doctor_availability.py` receiving computed slots from `MantraAssist-backend` supporting arrays of providers.
- [x] **International Timezone Resolution (2026-08-22):** Integrated Google's `phonenumbers` engine (`src/livekit_mcp/utils/timezone.py`) to auto-detect caller country/timezone from phone number (`+1` US -> EDT, `+44` UK -> GMT/BST, `+91` India -> IST, `+971` UAE -> GST, `+61` Australia -> AEST) and convert UTC slots dynamically.
- [x] **Integration Contract (`structure.json` & `format.json`) (2026-08-22):** Created minimal 1:1 schema contracts for backend developer.
- [x] **Automated Test Suite (2026-08-22):** 27 unit & integration tests passing 100% across auth, config, greeting, provider search, doctor availability receiver, and international timezone conversions.
- [x] **Developer Landing Dashboard & Diagnostics UI (2026-08-25):** Created a clean, simplified developer landing console at `/` with PostgreSQL/LKT diagnostics and dynamic tool catalog schemas.

