"""HTTP client for the read-only Interstellar health API."""
from __future__ import annotations
from typing import Any
import aiohttp

class InterstellarApiError(Exception):
    """Base API error."""

class InterstellarCannotConnect(InterstellarApiError):
    """Cannot connect to agent."""

class InterstellarInvalidResponse(InterstellarApiError):
    """Unexpected agent response."""

class InterstellarApiClient:
    def __init__(self, session: aiohttp.ClientSession, base_url: str, timeout: int = 10) -> None:
        self._session = session
        self.base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    async def _get_json(self, path: str) -> dict[str, Any]:
        try:
            async with self._session.get(f"{self.base_url}{path}", timeout=self._timeout) as response:
                if response.status not in (200, 503):
                    raise InterstellarCannotConnect(f"HTTP {response.status} from {path}")
                payload = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise InterstellarCannotConnect(str(err)) from err
        except ValueError as err:
            raise InterstellarInvalidResponse("Invalid JSON response") from err
        if not isinstance(payload, dict):
            raise InterstellarInvalidResponse("Expected a JSON object")
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
                payload = await response.json(content_type=None)
                if response.status != 202 or not isinstance(payload, dict) or not isinstance(payload.get("action_id"), str):
                    reason = payload.get("error", "Action rejected") if isinstance(payload, dict) else "Invalid action response"
                    raise InterstellarApiError(str(reason))
                return payload
        except (aiohttp.ClientError, TimeoutError) as err:
            raise InterstellarCannotConnect(str(err)) from err
        except ValueError as err:
            raise InterstellarInvalidResponse("Invalid JSON action response") from err
