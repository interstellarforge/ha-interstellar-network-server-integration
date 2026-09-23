"""HTTP client for the read-only Interstellar health API and the control API."""
from __future__ import annotations
import socket
from typing import Any
import aiohttp

CONTROL_CAPABILITY = "interstellarnetwork.nl/cap/server-control"


class InterstellarApiError(Exception):
    """Base API error.

    Every failure carries a stable ``error_code`` and a human ``reason`` so
    Home Assistant can explain what actually went wrong instead of collapsing
    unrelated failures into one misleading message.
    """

    error_code = "unknown_error"
    reason = "The Interstellar API returned an unexpected error"

    def __init__(self, message: str = "", *, reason: str | None = None) -> None:
        super().__init__(message or reason or self.reason)
        if reason:
            self.reason = reason


class InterstellarCannotConnect(InterstellarApiError):
    """Cannot reach the agent. Config flow treats every subclass as cannot_connect."""

    error_code = "cannot_connect"
    reason = "Home Assistant could not reach the server"


class InterstellarTimeout(InterstellarCannotConnect):
    error_code = "timeout"
    reason = "The server did not respond in time"


class InterstellarDnsError(InterstellarCannotConnect):
    error_code = "dns_error"
    reason = "The server name could not be resolved"


class InterstellarConnectionRefused(InterstellarCannotConnect):
    error_code = "connection_refused"
    reason = "The connection was refused"


class InterstellarTlsError(InterstellarCannotConnect):
    error_code = "tls_error"
    reason = "The TLS certificate could not be verified"


class InterstellarHttpError(InterstellarCannotConnect):
    error_code = "http_error"
    reason = "The server returned an unexpected HTTP status"

    def __init__(self, status: int, message: str = "", *, reason: str | None = None) -> None:
        self.status = status
        super().__init__(message or f"HTTP {status}", reason=reason)


class InterstellarUnauthorized(InterstellarHttpError):
    error_code = "unauthorized"
    reason = "Home Assistant is not authenticated to the control API"


class InterstellarCapabilityMissing(InterstellarHttpError):
    """HTTP 403: Serve reached the API but stripped or never carried the grant."""

    error_code = "tailscale_capability_missing"
    reason = "Tailscale control capability is not granted to Home Assistant"


class InterstellarNotFound(InterstellarHttpError):
    error_code = "not_found"
    reason = "The control API route was not found; check the control URL"


class InterstellarServiceUnavailable(InterstellarHttpError):
    error_code = "service_unavailable"
    reason = "The control service is running but reported itself unavailable"


class InterstellarServerError(InterstellarHttpError):
    error_code = "server_error"
    reason = "The server reported an internal error"


class InterstellarInvalidResponse(InterstellarApiError):
    """Unexpected agent response."""

    error_code = "invalid_response"
    reason = "The server returned an unexpected response"


_HTTP_ERRORS: dict[int, type[InterstellarHttpError]] = {
    401: InterstellarUnauthorized,
    403: InterstellarCapabilityMissing,
    404: InterstellarNotFound,
}


def _describe(err: Exception) -> str:
    # Error handling must never raise; some aiohttp exceptions format lazily.
    try:
        return str(err)
    except Exception:  # noqa: BLE001 - diagnostics only
        return err.__class__.__name__


def connection_error(err: Exception) -> InterstellarCannotConnect:
    """Map an aiohttp/OS failure onto a distinguishable Interstellar error."""
    if isinstance(err, TimeoutError):
        return InterstellarTimeout(_describe(err))
    # ClientSSLError subclasses ClientConnectorError, so check it first.
    if isinstance(err, aiohttp.ClientSSLError):
        return InterstellarTlsError(_describe(err))
    if isinstance(err, aiohttp.ClientConnectorError):
        os_error = getattr(err, "os_error", None)
        if isinstance(os_error, socket.gaierror):
            return InterstellarDnsError(_describe(err))
        if isinstance(os_error, ConnectionRefusedError):
            return InterstellarConnectionRefused(_describe(err))
    return InterstellarCannotConnect(_describe(err))


class InterstellarApiClient:
    def __init__(self, session: aiohttp.ClientSession, base_url: str, timeout: int = 10) -> None:
        self._session = session
        self.base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    @staticmethod
    def _error_detail(payload: Any) -> str:
        if isinstance(payload, dict):
            value = payload.get("error")
            if isinstance(value, str) and value:
                return value
        return ""

    async def _get_json(self, path: str) -> dict[str, Any]:
        try:
            async with self._session.get(f"{self.base_url}{path}", timeout=self._timeout) as response:
                status = response.status
                # 200 and 503 both carry a JSON body worth reading; the health
                # agent uses 503 for degraded telemetry.
                if status not in (200, 503):
                    try:
                        body = await response.json(content_type=None)
                    except (ValueError, aiohttp.ClientError):
                        body = None
                    detail = self._error_detail(body)
                    error = _HTTP_ERRORS.get(status)
                    if error is None:
                        error = InterstellarServerError if status >= 500 else InterstellarHttpError
                    raise error(status, f"HTTP {status} from {path}{f': {detail}' if detail else ''}")
                payload = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise connection_error(err) from err
        except ValueError as err:
            raise InterstellarInvalidResponse("Invalid JSON response") from err
        if not isinstance(payload, dict):
            raise InterstellarInvalidResponse("Expected a JSON object")
        if status == 503:
            detail = self._error_detail(payload)
            raise InterstellarServiceUnavailable(
                503, f"HTTP 503 from {path}{f': {detail}' if detail else ''}")
        return payload

    async def async_get_stats(self) -> dict[str, Any]:
        payload = await self._get_json("/stats")
        if payload.get("status") != "ok" or "host" not in payload:
            raise InterstellarInvalidResponse("Unexpected /stats payload")
        return payload

    async def async_get_health(self) -> dict[str, Any]:
        return await self._get_json("/health")

    async def async_get_control(self) -> dict[str, Any]:
        state = await self._get_json("/state")
        actions = await self._get_json("/actions")
        if "policy" not in state or not isinstance(actions.get("actions"), list):
            raise InterstellarInvalidResponse("Unexpected control response")
        state["actions"] = actions["actions"]
        return state

    async def async_action(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            async with self._session.post(f"{self.base_url}{path}", json=body or {}, timeout=self._timeout) as response:
                status = response.status
                payload = await response.json(content_type=None)
                if status != 202 or not isinstance(payload, dict) or not isinstance(payload.get("action_id"), str):
                    detail = self._error_detail(payload) or "Action rejected"
                    error = _HTTP_ERRORS.get(status)
                    if error is not None:
                        raise error(status, detail)
                    raise InterstellarApiError(str(detail))
                return payload
        except (aiohttp.ClientError, TimeoutError) as err:
            raise connection_error(err) from err
        except ValueError as err:
            raise InterstellarInvalidResponse("Invalid JSON action response") from err
