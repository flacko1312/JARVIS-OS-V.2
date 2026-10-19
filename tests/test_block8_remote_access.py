"""Block 8 tests — Secure remote access API.

Tests: token auth, endpoint routing, permission gating, Tailscale detection,
tool invocation, panel rendering.
"""
import json
import os
import threading
import time
import unittest
from http.server import HTTPServer
from unittest.mock import patch, MagicMock
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def _find_free_port():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestTokenValidation(unittest.TestCase):
    def test_valid_token(self):
        import api_server
        api_server._api_token = "test-secret-token"
        self.assertTrue(api_server._validate_token("test-secret-token"))

    def test_invalid_token(self):
        import api_server
        api_server._api_token = "test-secret-token"
        self.assertFalse(api_server._validate_token("wrong-token"))

    def test_no_token_configured(self):
        import api_server
        api_server._api_token = None
        self.assertFalse(api_server._validate_token("any-token"))

    def test_empty_token(self):
        import api_server
        api_server._api_token = "test-secret-token"
        self.assertFalse(api_server._validate_token(""))


class TestTailscaleDetection(unittest.TestCase):
    @patch("subprocess.run")
    def test_tailscale_ip_found(self, mock_run):
        import api_server
        mock_run.return_value = MagicMock(returncode=0, stdout="100.64.1.2\n")
        ip = api_server._get_tailscale_ip()
        self.assertEqual(ip, "100.64.1.2")

    @patch("subprocess.run")
    def test_tailscale_not_running(self, mock_run):
        import api_server
        mock_run.side_effect = FileNotFoundError()
        ip = api_server._get_tailscale_ip()
        self.assertIsNone(ip)

    @patch("subprocess.run")
    def test_tailscale_non_ts_ip(self, mock_run):
        import api_server
        mock_run.return_value = MagicMock(returncode=0, stdout="192.168.1.5\n")
        ip = api_server._get_tailscale_ip()
        self.assertIsNone(ip)

    @patch("subprocess.run")
    def test_tailscale_status(self, mock_run):
        import api_server
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "Self": {"HostName": "server-lilith", "TailscaleIPs": ["100.64.1.2"], "Online": True},
                "MagicDNSSuffix": "tail12345.ts.net",
            })
        )
        status = api_server._tailscale_status()
        self.assertTrue(status["connected"])
        self.assertEqual(status["hostname"], "server-lilith")


class TestAPIServer(unittest.TestCase):
    """Integration tests with a real HTTP server."""

    @classmethod
    def setUpClass(cls):
        import api_server
        cls.port = _find_free_port()
        cls.token = "test-api-token-12345"
        api_server._api_token = cls.token
        api_server._start_time = time.time()
        api_server._jarvis_ref = None  # No jarvis for unit tests
        cls.server = HTTPServer(("127.0.0.1", cls.port), api_server._APIHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def _get(self, path, auth=True):
        req = Request(f"{self.base}{path}")
        if auth:
            req.add_header("Authorization", f"Bearer {self.token}")
        return urlopen(req, timeout=5)

    def _post(self, path, body, auth=True):
        data = json.dumps(body).encode()
        req = Request(f"{self.base}{path}", data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        if auth:
            req.add_header("Authorization", f"Bearer {self.token}")
        return urlopen(req, timeout=5)

    def test_health_no_auth_required(self):
        try:
            resp = self._get("/api/health", auth=False)
            data = json.loads(resp.read())
        except HTTPError as e:
            data = json.loads(e.read())
        self.assertIn("status", data)

    def test_status_requires_auth(self):
        with self.assertRaises(HTTPError) as ctx:
            self._get("/api/status", auth=False)
        self.assertEqual(ctx.exception.code, 401)

    def test_status_with_auth_returns_503_without_jarvis(self):
        with self.assertRaises(HTTPError) as ctx:
            self._get("/api/status")
        self.assertEqual(ctx.exception.code, 503)
        data = json.loads(ctx.exception.read())
        self.assertIn("error", data)

    def test_tools_list(self):
        resp = self._get("/api/tools")
        data = json.loads(resp.read())
        self.assertIn("tools", data)
        self.assertGreater(len(data["tools"]), 10)

    def test_invoke_system_status(self):
        resp = self._post("/api/tool/invoke", {"tool": "system_status"})
        data = json.loads(resp.read())
        self.assertIn("load", data)
        self.assertIn("memory", data)

    def test_invoke_process_list(self):
        resp = self._post("/api/tool/invoke", {"tool": "process_list"})
        data = json.loads(resp.read())
        self.assertIn("processes", data)

    def test_invoke_denied_tool(self):
        with self.assertRaises(HTTPError) as ctx:
            self._post("/api/tool/invoke", {"tool": "nonexistent_tool"})
        self.assertEqual(ctx.exception.code, 403)

    def test_invoke_confirm_required_blocked(self):
        with self.assertRaises(HTTPError) as ctx:
            self._post("/api/tool/invoke", {
                "tool": "systemd_action", "action": "restart",
            })
        self.assertEqual(ctx.exception.code, 403)
        data = json.loads(ctx.exception.read())
        self.assertIn("voice confirmation", data["error"])

    def test_invoke_journal_read(self):
        resp = self._post("/api/tool/invoke", {
            "tool": "journal_read", "service": "jarvis-headless", "lines": 5,
        })
        data = json.loads(resp.read())
        self.assertIn("log", data)

    def test_panel_html(self):
        resp = self._get("/api/panel")
        html = resp.read().decode()
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("JARVIS Headless", html)

    def test_404(self):
        with self.assertRaises(HTTPError) as ctx:
            self._get("/api/nonexistent")
        self.assertEqual(ctx.exception.code, 404)

    def test_wrong_token(self):
        req = Request(f"{self.base}/api/status")
        req.add_header("Authorization", "Bearer wrong-token")
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 401)

    def test_invoke_catalog(self):
        resp = self._post("/api/tool/invoke", {"tool": "open_capabilities_catalog"})
        data = json.loads(resp.read())
        self.assertIn("catalog", data)
        self.assertIn("JARVIS Headless", data["catalog"])


class TestStartFunction(unittest.TestCase):
    def test_no_token_disables_server(self):
        import api_server
        old_token = os.environ.get("JARVIS_API_TOKEN")
        if "JARVIS_API_TOKEN" in os.environ:
            del os.environ["JARVIS_API_TOKEN"]
        try:
            result = api_server.start(None, token=None)
            self.assertFalse(result["started"])
            self.assertIn("no token", result["reason"])
        finally:
            if old_token:
                os.environ["JARVIS_API_TOKEN"] = old_token


if __name__ == "__main__":
    unittest.main()
