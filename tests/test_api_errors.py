"""Control API failure classification.

Atlas and Jupiter both returned HTTP 403 ("Tailscale control capability
required") while their control services were running. The integration reported
"Control API is not active", which sent debugging in the wrong direction for
days. Every distinguishable failure must therefore map to its own error code and
its own human-readable reason.

Only aiohttp is required, so this runs without Home Assistant Core installed.
"""
from __future__ import annotations

import asyncio
import importlib.util
import socket
import ssl
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]

try:
    import aiohttp
    from aiohttp import web
except ImportError:  # pragma: no cover - environment without aiohttp
    raise unittest.SkipTest("aiohttp is unavailable")

# Load api.py directly: it only needs aiohttp, while importing the package would
# pull in Home Assistant Core.
_spec = importlib.util.spec_from_file_location(
    "interstellar_api", ROOT / "custom_components/interstellar_network/api.py")
api = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(api)

InterstellarApiClient = api.InterstellarApiClient
InterstellarApiError = api.InterstellarApiError
InterstellarCannotConnect = api.InterstellarCannotConnect
InterstellarCapabilityMissing = api.InterstellarCapabilityMissing
InterstellarConnectionRefused = api.InterstellarConnectionRefused
InterstellarDnsError = api.InterstellarDnsError
InterstellarInvalidResponse = api.InterstellarInvalidResponse
InterstellarNotFound = api.InterstellarNotFound
InterstellarServerError = api.InterstellarServerError
InterstellarServiceUnavailable = api.InterstellarServiceUnavailable
InterstellarTimeout = api.InterstellarTimeout
InterstellarTlsError = api.InterstellarTlsError
InterstellarUnauthorized = api.InterstellarUnauthorized
connection_error = api.connection_error


class StatusMappingTests(unittest.IsolatedAsyncioTestCase):
    """Drive a real aiohttp server so status handling is not mocked away."""

    async def serve(self, handler):
        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        self.addAsyncCleanup(runner.cleanup)
        port = runner.addresses[0][1]
        session = aiohttp.ClientSession()
        self.addAsyncCleanup(session.close)
        return InterstellarApiClient(session, f"http://127.0.0.1:{port}", timeout=5)

    @staticmethod
    def responder(status, payload):
        async def handler(request):
            return web.json_response(payload, status=status)
        return handler

    async def assert_control_error(self, status, payload, expected, code, reason_contains=""):
        client = await self.serve(self.responder(status, payload))
        with self.assertRaises(expected) as caught:
            await client.async_get_control()
        self.assertEqual(code, caught.exception.error_code)
        if reason_contains:
            self.assertIn(reason_contains, caught.exception.reason)
        # Every API failure stays catchable as the documented base class.
        self.assertIsInstance(caught.exception, InterstellarApiError)

    async def test_403_is_a_missing_tailscale_capability(self):
        """The exact live response from Atlas and Jupiter."""
        await self.assert_control_error(
            403, {"error": "Tailscale control capability required"},
            InterstellarCapabilityMissing, "tailscale_capability_missing",
            "Tailscale control capability is not granted")

    async def test_401_is_reported_as_unauthenticated(self):
        await self.assert_control_error(401, {"error": "nope"}, InterstellarUnauthorized, "unauthorized")

    async def test_404_points_at_the_control_url(self):
        await self.assert_control_error(404, {"error": "Not found"}, InterstellarNotFound,
                                        "not_found", "control URL")

    async def test_500_is_a_server_error(self):
        await self.assert_control_error(500, {"error": "boom"}, InterstellarServerError, "server_error")

    async def test_503_is_service_unavailable_not_a_transport_failure(self):
        await self.assert_control_error(503, {"error": "Control state unavailable"},
                                        InterstellarServiceUnavailable, "service_unavailable")

    async def test_invalid_json_is_distinct(self):
        async def handler(request):
            return web.Response(text="not json", status=200)
        client = await self.serve(handler)
        with self.assertRaises(InterstellarInvalidResponse) as caught:
            await client.async_get_control()
        self.assertEqual("invalid_response", caught.exception.error_code)

    async def test_valid_but_unexpected_payload_is_invalid_response(self):
        client = await self.serve(self.responder(200, {"version": "0.2.1"}))
        with self.assertRaises(InterstellarInvalidResponse):
            await client.async_get_control()

    async def test_successful_control_state_is_returned(self):
        async def handler(request):
            if request.path == "/state":
                return web.json_response({"version": "0.2.1", "policy": {}, "toolbox_version": "4.5.1"})
            return web.json_response({"actions": [{"action": "reboot"}]})
        client = await self.serve(handler)
        state = await client.async_get_control()
        self.assertEqual("0.2.1", state["version"])
        self.assertEqual("4.5.1", state["toolbox_version"])
        self.assertEqual([{"action": "reboot"}], state["actions"])

    async def test_action_403_is_also_a_capability_failure(self):
        client = await self.serve(self.responder(403, {"error": "Tailscale control capability required"}))
        with self.assertRaises(InterstellarCapabilityMissing) as caught:
            await client.async_action("/actions/reboot", {"confirm_hostname": "atlas"})
        self.assertEqual("tailscale_capability_missing", caught.exception.error_code)

    async def test_connection_refused_reaches_no_service(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        session = aiohttp.ClientSession()
        self.addAsyncCleanup(session.close)
        client = InterstellarApiClient(session, f"http://127.0.0.1:{port}", timeout=5)
        with self.assertRaises(InterstellarCannotConnect) as caught:
            await client.async_get_control()
        self.assertIn(caught.exception.error_code, {"connection_refused", "cannot_connect"})

    async def test_timeout_is_distinct(self):
        async def handler(request):
            await asyncio.sleep(5)
            return web.json_response({})
        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        self.addAsyncCleanup(runner.cleanup)
        session = aiohttp.ClientSession()
        self.addAsyncCleanup(session.close)
        client = InterstellarApiClient(session, f"http://127.0.0.1:{runner.addresses[0][1]}", timeout=1)
        with self.assertRaises(InterstellarTimeout) as caught:
            await client.async_get_control()
        self.assertEqual("timeout", caught.exception.error_code)


class ConnectionMappingTests(unittest.TestCase):
    """Transport failures are classified without needing the real condition."""

    @staticmethod
    def connection_key():
        return type("Key", (), {"host": "atlas.ts.net", "port": 8443, "is_ssl": True, "ssl": None})()

    @classmethod
    def connector_error(cls, os_error):
        return aiohttp.ClientConnectorError(connection_key=cls.connection_key(), os_error=os_error)

    def test_dns_failure(self):
        mapped = connection_error(self.connector_error(socket.gaierror(8, "nodename nor servname provided")))
        self.assertIsInstance(mapped, InterstellarDnsError)
        self.assertEqual("dns_error", mapped.error_code)

    def test_connection_refused(self):
        mapped = connection_error(self.connector_error(ConnectionRefusedError(61, "Connection refused")))
        self.assertIsInstance(mapped, InterstellarConnectionRefused)
        self.assertEqual("connection_refused", mapped.error_code)

    def test_tls_failure(self):
        error = aiohttp.ClientConnectorCertificateError(
            connection_key=self.connection_key(),
            certificate_error=ssl.SSLCertVerificationError("self signed certificate"))
        mapped = connection_error(error)
        self.assertIsInstance(mapped, InterstellarTlsError)
        self.assertEqual("tls_error", mapped.error_code)

    def test_timeout(self):
        mapped = connection_error(TimeoutError())
        self.assertIsInstance(mapped, InterstellarTimeout)

    def test_every_transport_failure_stays_cannot_connect(self):
        """The config flow catches InterstellarCannotConnect; nothing may escape it."""
        for error in (self.connector_error(socket.gaierror()),
                      self.connector_error(ConnectionRefusedError()),
                      TimeoutError(),
                      aiohttp.ClientError("generic")):
            self.assertIsInstance(connection_error(error), InterstellarCannotConnect)

    def test_http_errors_are_cannot_connect_subclasses(self):
        """Keeps the existing config-flow `cannot_connect` behaviour for bad hosts."""
        for error in (InterstellarCapabilityMissing(403), InterstellarNotFound(404),
                      InterstellarServerError(500), InterstellarUnauthorized(401),
                      InterstellarServiceUnavailable(503)):
            self.assertIsInstance(error, InterstellarCannotConnect)

    def test_error_codes_are_unique(self):
        codes = [InterstellarCapabilityMissing.error_code, InterstellarUnauthorized.error_code,
                 InterstellarNotFound.error_code, InterstellarServerError.error_code,
                 InterstellarServiceUnavailable.error_code, InterstellarTimeout.error_code,
                 InterstellarDnsError.error_code, InterstellarConnectionRefused.error_code,
                 InterstellarTlsError.error_code, InterstellarInvalidResponse.error_code]
        self.assertEqual(len(codes), len(set(codes)))


if __name__ == "__main__":
    unittest.main()
