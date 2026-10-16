import hashlib
import hmac
import json
import time
from datetime import UTC, datetime

from livekit_mcp.config import get_settings


def create_hmac_headers(
    method: str = "GET",
    original_url: str = "/",
    payload_str: str = "",
    webhook_secret: str | None = None,
) -> dict[str, str]:
    """
    Create HMAC-signed headers for requests to MantraAssist backend.
    Matches the backend signature format: METHOD.originalUrl.payloadString.timestamp

    Args:
        method: HTTP method in uppercase (GET, POST, etc.)
        original_url: The path and query string (e.g. /v1/webhooks/mcp/locations?org_id=153)
        payload_str: Raw body string (empty string for GET)
        webhook_secret: Optional override for the webhook secret (uses settings if not provided)

    Returns:
        Dictionary of headers including x-signature, x-timestamp, x-timestamp-iso, x-source
    """
    settings = get_settings()
    secret = webhook_secret or settings.mantraassist_webhook_secret or ""

    timestamp = str(int(time.time()))
    timestamp_iso = datetime.fromtimestamp(int(timestamp), tz=UTC).strftime("%Y-%m-%dT%H:%M:%S")

    headers = {
        "Content-Type": "application/json",
        "x-timestamp": timestamp,
        "x-source": "mcp",
        "x-timestamp-iso": timestamp_iso,
    }

    if secret:
        clean_method = method.upper()
        clean_url = original_url if original_url.startswith("/") else f"/{original_url}"
        clean_payload = payload_str if clean_method != "GET" else ""

        data_to_sign = f"{clean_method}.{clean_url}.{clean_payload}.{timestamp}"
        headers["x-signature"] = hmac.new(
            secret.encode("utf-8"),
            data_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    return headers


async def deliver_signed_request(
    url: str,
    payload: dict | None = None,
    method: str = "POST",
    webhook_secret: str | None = None,
    max_retries: int = 3,
    timeout: float = 30.0,
) -> tuple[bool, int | None, int, str]:
    """
    Send an HMAC-signed HTTP request with retry logic.
    Matches the retry behavior of livekit's deliver_signed_payload function.

    Args:
        url: Target URL
        payload: Request payload as dict (query params for GET, json body for POST)
        method: HTTP method (GET, POST, etc.)
        webhook_secret: Optional override for webhook secret
        max_retries: Maximum retry attempts
        timeout: Request timeout in seconds

    Returns:
        Tuple of (success, http_status, attempts_made, error_message)
    """
    import asyncio
    import httpx

    settings = get_settings()
    secret = webhook_secret or settings.mantraassist_webhook_secret or ""

    clean_method = method.upper()
    u = httpx.URL(url)

    if clean_method == "GET":
        if payload:
            u = u.copy_merge_params(payload)
        original_url = u.raw_path.decode("ascii")
        payload_str = ""
    else:
        original_url = u.raw_path.decode("ascii")
        payload_str = json.dumps(payload or {}, separators=(',', ':'))

    last_error = ""
    last_status: int | None = None

    for attempt in range(1, max_retries + 1):
        headers = create_hmac_headers(
            method=clean_method,
            original_url=original_url,
            payload_str=payload_str,
            webhook_secret=secret,
        )

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if clean_method == "GET":
                    resp = await client.get(u, headers=headers)
                else:
                    resp = await client.request(clean_method, u, content=payload_str, headers=headers)

                resp.raise_for_status()
                return True, resp.status_code, attempt, ""

        except Exception as e:
            last_error = str(e)
            last_status = getattr(getattr(e, "response", None), "status_code", None)

        if attempt < max_retries:
            await asyncio.sleep(2 ** (attempt - 1))

    return False, last_status, max_retries, last_error
