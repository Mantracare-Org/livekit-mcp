import hashlib
import hmac
import json
import time
from datetime import UTC, datetime

from livekit_mcp.config import get_settings


def create_hmac_headers(
    payload_str: str,
    webhook_secret: str | None = None,
) -> dict[str, str]:
    """
    Create HMAC-signed headers for requests to MantraAssist backend.
    Matches the signature format used by livekit's deliver_signed_payload function.

    Args:
        payload_str: The JSON payload string to sign
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
        data_to_sign = f"{payload_str}.{timestamp}"
        headers["x-signature"] = hmac.new(
            secret.encode("utf-8"),
            data_to_sign.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

    return headers


async def deliver_signed_request(
    url: str,
    payload: dict,
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
        payload: Request payload as dict
        method: HTTP method (GET, POST, etc.)
        webhook_secret: Optional override for webhook secret
        max_retries: Maximum retry attempts
        timeout: Request timeout in seconds

    Returns:
        Tuple of (success, http_status, attempts_made, error_message)
    """
    import httpx

    settings = get_settings()
    secret = webhook_secret or settings.mantraassist_webhook_secret or ""

    payload_str = json.dumps(payload, separators=(',', ':'))

    last_error = ""
    last_status: int | None = None

    for attempt in range(1, max_retries + 1):
        headers = create_hmac_headers(payload_str, secret)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if method.upper() == "GET":
                    # For GET, send payload as query params
                    resp = await client.get(url, params=payload, headers=headers)
                else:
                    resp = await client.request(method, url, content=payload_str, headers=headers)

                resp.raise_for_status()
                return True, resp.status_code, attempt, ""

        except Exception as e:
            last_error = str(e)
            last_status = getattr(getattr(e, "response", None), "status_code", None)

        if attempt < max_retries:
            import asyncio
            await asyncio.sleep(2 ** (attempt - 1))

    return False, last_status, max_retries, last_error
