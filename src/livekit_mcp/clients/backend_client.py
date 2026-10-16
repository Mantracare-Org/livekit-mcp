import json
import logging
import urllib.parse
from typing import Any

import httpx

from livekit_mcp.config import Settings, get_settings
from livekit_mcp.utils.hmac_signing import create_hmac_headers
from livekit_mcp.utils.timezone import resolve_date_string, to_utc_iso_string

logger = logging.getLogger(__name__)


class MantraAssistBackendClient:
    """Async HTTP client to query MantraAssist-backend for doctor schedules and availability."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.mantraassist_backend_url.rstrip("/")

    def _base_headers(self) -> dict[str, str]:
        """Base headers for all requests."""
        return {"ngrok-skip-browser-warning": "69420"}

    async def _signed_get(self, url: str, params: dict[str, Any], timeout: float) -> tuple[bool, Any]:
        """Make a signed GET request with HMAC."""
        u = httpx.URL(url)
        if params:
            u = u.copy_merge_params(params)
        original_url = u.raw_path.decode("ascii")

        headers = {
            **self._base_headers(),
            **create_hmac_headers(method="GET", original_url=original_url, payload_str=""),
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(u, headers=headers)
                if resp.status_code == 200:
                    return True, resp.json()
                logger.warning("Signed GET %s returned HTTP %d: %s", original_url, resp.status_code, resp.text[:200])
                return False, None
        except Exception as e:
            logger.error("Signed GET %s failed: %s", url, e)
            return False, None

    async def _signed_post(self, url: str, payload: dict[str, Any], timeout: float) -> tuple[bool, Any]:
        """Make a signed POST request with HMAC."""
        u = httpx.URL(url)
        original_url = u.raw_path.decode("ascii")
        payload_str = json.dumps(payload, separators=(',', ':'))

        headers = {
            **self._base_headers(),
            **create_hmac_headers(method="POST", original_url=original_url, payload_str=payload_str),
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(u, content=payload_str, headers=headers)
                if resp.status_code == 200:
                    return True, resp.json()
                logger.warning("Signed POST %s returned HTTP %d: %s", original_url, resp.status_code, resp.text[:200])
                return False, None
        except Exception as e:
            logger.error("Signed POST %s failed: %s", url, e)
            return False, None

    async def recognize_client(
        self,
        org_id: int | str,
        phone_number: str,
        timeout: float = 3.0,
    ) -> dict[str, Any] | None:
        """Resolve an inbound caller name through the MA client recognition / lead endpoint.

        Contract: GET /v1/webhooks/mcp/lead?org_id={org_id}&phone_number={phone_number}
        Expected response: {"success": true, "data": {"client_name": "...", "client_metadata": {...}}}
        """
        clean_phone = str(phone_number).strip()
        encoded_phone = urllib.parse.quote(clean_phone)
        url = f"{self.base_url}/v1/webhooks/mcp/lead?org_id={org_id}&phone_number={encoded_phone}"

        # First try signed GET
        ok, data = await self._signed_get(url, {}, timeout)
        if ok and isinstance(data, dict) and data.get("data"):
            lead_data = data["data"]
            return {
                "client_name": lead_data.get("client_name"),
                "client_metadata": lead_data.get("client_metadata") or {},
                "user_id": lead_data.get("user_id"),
            }

        # Fallback to POST /v1/webhooks/client-recognition
        post_url = f"{self.base_url}/v1/webhooks/client-recognition"
        ok, pdata = await self._signed_post(post_url, {"org_id": str(org_id), "phone_number": clean_phone}, timeout)
        if ok and isinstance(pdata, dict):
            if isinstance(pdata.get("data"), dict):
                pdata = pdata["data"]
            return {
                "client_name": pdata.get("client_name"),
                "client_metadata": pdata.get("client_metadata") or {},
                "user_id": pdata.get("user_id"),
            }
        return None

    async def get_doctor_availability(
        self,
        org_id: int | str | None = None,
        date: str | None = None,
        doctor_name: str | None = None,
        department: str | None = None,
        caller_phone: str | None = None,
        caller_tz: str | None = None,
        timeout: float = 5.0,
    ) -> list[dict[str, Any]] | None:
        """Fetch calculated doctor availability from MantraAssist-backend webhook endpoint.

        Guaranteed fixed schema sent in UTC every time:
            - org_id: Organization ID (or "" if missing)
            - date: Date string 'YYYY-MM-DD' in UTC (or "" if missing)
            - datetime: ISO 8601 UTC timestamp string 'YYYY-MM-DDTHH:MM:SS.000Z' (or "" if missing)
            - doc_name: Doctor name (or "" if missing)
            - department: Department / Specialization (or "" if missing)
            - caller_phone: Caller phone number (if available)

        Calls: POST /v1/webhooks/mcp (or GET /v1/webhooks/mcp)

        Returns:
            List of provider objects with UTC time slots, or None if request fails.
        """
        url = f"{self.base_url}/v1/webhooks/mcp"

        org_id_val = org_id if org_id is not None else ""
        doc_name_val = str(doctor_name).strip() if doctor_name and str(doctor_name).strip() else ""
        dept_val = str(department).strip() if department and str(department).strip() else ""

        # Always resolve target calendar date and UTC timestamp
        if date and str(date).strip():
            target_d = resolve_date_string(str(date).strip(), caller_tz or "Asia/Kolkata")
            utc_date_val = target_d.strftime("%Y-%m-%d")
            utc_datetime_val = to_utc_iso_string(str(date).strip(), source_tz_str=caller_tz or "Asia/Kolkata")
        else:
            utc_datetime_val = ""
            utc_date_val = ""

        params: dict[str, Any] = {
            "org_id": org_id_val,
            "date": utc_date_val,
            "datetime": utc_datetime_val,
            "doc_name": doc_name_val,
            "department": dept_val,
        }
        if caller_phone:
            params["caller_phone"] = str(caller_phone).strip()

        # 1. Try signed GET request first
        ok, data = await self._signed_get(url, params, timeout)
        if ok:
            return self._extract_providers(data)

        # 2. Try signed POST request fallback
        logger.info("Retrying with signed POST %s", url)
        ok, data = await self._signed_post(url, params, timeout)
        if ok:
            return self._extract_providers(data)

        logger.warning("MantraAssist backend returned non-200 for both GET and POST")
        return None

    async def manage_appointments(
        self,
        *,
        action: str,
        org_id: int | str,
        user_id: int | str,
        appointment_id: int | str | None = None,
        appointment_title: str | None = None,
        requested_date: str | None = None,
        new_datetime: str | None = None,
        timeout: float = 5.0,
    ) -> Any:
        """List, check, cancel, or reschedule a recognized client's appointments.

        Provisional contract: POST /v1/webhooks/appointments.
        The endpoint is intentionally isolated here so its path can be changed later.
        """
        url = f"{self.base_url}/v1/webhooks/appointments"
        payload = {
            "action": str(action).strip().lower(),
            "org_id": str(org_id),
            "user_id": str(user_id),
        }
        if appointment_id not in (None, ""):
            payload["appointment_id"] = appointment_id
        if appointment_title:
            payload["appointment_title"] = appointment_title.strip()
        if requested_date:
            payload["requested_date"] = requested_date.strip()
        if new_datetime:
            payload["new_datetime"] = new_datetime.strip()

        ok, data = await self._signed_post(url, payload, timeout)
        if not ok:
            logger.warning("Appointment backend returned non-200")
            return {"status": "error", "message": "Request failed"}
        return data

    # In-memory temporary cache: org_id -> (timestamp, data)
    _processes_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    async def get_org_processes(
        self,
        org_id: int | str,
        timeout: float = 5.0,
        ttl_seconds: float = 600.0,
    ) -> list[dict[str, Any]]:
        """Fetch processes and stages with descriptions for an organization.

        Uses an in-memory TTL cache to avoid repeated network overhead.
        Calls: GET /v1/processes?org_id={org_id} (with fallback endpoints)
        """
        import time

        org_id_str = str(org_id).strip()
        now = time.time()

        # Check in-memory cache
        if org_id_str in self._processes_cache:
            cached_time, cached_data = self._processes_cache[org_id_str]
            if (now - cached_time) < ttl_seconds:
                logger.info("Returning %d org processes from in-memory cache for org_id=%s", len(cached_data), org_id_str)
                return cached_data

        urls = [
            f"{self.base_url}/v1/webhooks/mcp/processes",
            f"{self.base_url}/v1/processes",
            f"{self.base_url}/v1/webhooks/mcp",
        ]

        params = {"org_id": org_id_str}

        for url in urls:
            try:
                ok, data = await self._signed_get(url, params, timeout)
                if ok:
                    extracted = self._extract_processes(data)
                    logger.info("[MA-BACKEND] Extracted %d normalized processes: %s", len(extracted), json.dumps(extracted, default=str))
                    if extracted:
                        self._processes_cache[org_id_str] = (now, extracted)
                        return extracted
            except Exception as e:
                logger.warning("[MA-BACKEND] Failed querying processes at %s: %s", url, e)

        return []

    def _extract_processes(self, data: Any) -> list[dict[str, Any]]:
        """Normalize process and stage response data into standardized format with descriptions."""
        raw_list = []
        if isinstance(data, list):
            raw_list = data
        elif isinstance(data, dict):
            if "processes" in data and isinstance(data["processes"], list):
                raw_list = data["processes"]
            elif "data" in data and isinstance(data["data"], list):
                raw_list = data["data"]
            elif "data" in data and isinstance(data["data"], dict) and "processes" in data["data"]:
                raw_list = data["data"]["processes"]
            elif "id" in data or "process_id" in data:
                raw_list = [data]

        normalized: list[dict[str, Any]] = []
        for p in raw_list:
            if not isinstance(p, dict):
                continue
            pid = p.get("id") or p.get("process_id")
            if pid is None:
                continue
            try:
                pid_int = int(pid)
            except (ValueError, TypeError):
                pid_int = pid

            p_name = p.get("name") or p.get("process_name") or ""
            p_desc = p.get("description") or p.get("process_description") or ""

            raw_stages = p.get("stages") or p.get("stageDetails") or []
            stage_ids: list[int] = []
            formatted_stages: list[dict[str, Any]] = []

            for stg in raw_stages:
                if not isinstance(stg, dict):
                    try:
                        s_id = int(stg)
                        stage_ids.append(s_id)
                        formatted_stages.append({
                            "stage_id": s_id,
                            "stage_name": f"Stage {s_id}",
                            "stage_description": "",
                        })
                    except (ValueError, TypeError):
                        pass
                    continue

                sid = stg.get("id") or stg.get("stage_id")
                if sid is None:
                    continue
                try:
                    sid_int = int(sid)
                except (ValueError, TypeError):
                    sid_int = sid

                s_name = stg.get("name") or stg.get("stage_name") or ""
                s_desc = stg.get("description") or stg.get("stage_description") or ""

                stage_ids.append(sid_int)
                formatted_stages.append({
                    "stage_id": sid_int,
                    "stage_name": s_name,
                    "stage_description": s_desc,
                })

            normalized.append({
                "process_id": pid_int,
                "process_name": p_name,
                "process_description": p_desc,
                "stage_ids": stage_ids,
                "stages": formatted_stages,
            })

        return normalized

    def _extract_providers(self, data: Any) -> list[dict[str, Any]]:
        """Normalize response data to standard providers list."""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            if "providers" in data and isinstance(data["providers"], list):
                return data["providers"]
            if "data" in data and isinstance(data["data"], list):
                return data["data"]
            if "data" in data and isinstance(data["data"], dict) and "providers" in data["data"]:
                return data["data"]["providers"]
            # Single provider dict fallback
            if "name" in data or "available_slots" in data:
                return [data]
        return []

    async def get_org_services(self, org_id: int | str, timeout: float = 4.0) -> list[dict[str, Any]]:
        """Fetch dynamic services for an organization from MantraAssist backend API endpoint GET /v1/webhooks/mcp/services."""
        urls = [
            f"{self.base_url}/v1/webhooks/mcp/services",
            f"{self.base_url}/webhooks/mcp/services",
            f"{self.base_url}/v1/services",
        ]
        params = {"org_id": str(org_id).strip()}

        for url in urls:
            try:
                ok, data = await self._signed_get(url, params, timeout)
                if ok:
                    if isinstance(data, dict):
                        data_obj = data.get("data") if isinstance(data.get("data"), dict) else data
                        if isinstance(data_obj, dict) and "services" in data_obj and isinstance(data_obj["services"], list):
                            return data_obj["services"]
                        if isinstance(data_obj, list):
                            return data_obj
                    elif isinstance(data, list):
                        return data
            except Exception as exc:
                logger.debug(f"[MA-BACKEND] Failed querying services at {url}: {exc}")

        return []

    async def get_org_locations(
        self,
        org_id: int | str,
        caller_lat: float | str | None = None,
        caller_lng: float | str | None = None,
        timeout: float = 4.0,
    ) -> list[dict[str, Any]]:
        """Fetch dynamic hospital/clinic branch locations for an organization from GET /v1/webhooks/mcp/locations."""
        urls = [
            f"{self.base_url}/v1/webhooks/mcp/locations",
            f"{self.base_url}/webhooks/mcp/locations",
            f"{self.base_url}/v1/locations",
        ]
        params: dict[str, str] = {"org_id": str(org_id).strip()}
        if caller_lat is not None:
            params["caller_lat"] = str(caller_lat)
        if caller_lng is not None:
            params["caller_lng"] = str(caller_lng)

        for url in urls:
            try:
                ok, data = await self._signed_get(url, params, timeout)
                if ok:
                    if isinstance(data, dict):
                        data_obj = data.get("data") if isinstance(data.get("data"), dict) else data
                        if isinstance(data_obj, dict) and "locations" in data_obj and isinstance(data_obj["locations"], list):
                            return data_obj["locations"]
                        if isinstance(data_obj, list):
                            return data_obj
                    elif isinstance(data, list):
                        return data
            except Exception as exc:
                logger.debug(f"[MA-BACKEND] Failed querying locations at {url}: {exc}")

        return []
