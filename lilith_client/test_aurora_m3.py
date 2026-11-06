"""Windows-side Phase 4 tests for AURORA adapter connector (M3).

Run on Windows after deploying adapter_connector.py:
    cd C:\\JARVIS
    python -m pytest lilith_client\\test_aurora_m3.py -v

Requirements:
    pip install pytest pytest-asyncio psutil
    (sounddevice or pyaudio optional — audio tests skip if absent)
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import asyncio
import pytest

sys.path.insert(0, os.path.dirname(__file__))

import adapter_connector as mod  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _future_deadline(seconds: float = 30.0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _past_deadline() -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()


def _invoke_message(
    capability_id: str,
    required_scope: str,
    parameters: dict[str, Any] | None = None,
    *,
    deadline: str | None = None,
    adapter_id: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    return {
        "type": "invoke",
        "request_id": request_id or str(uuid4()),
        "correlation_id": correlation_id or str(uuid4()),
        "adapter_id": adapter_id or mod.ADAPTER_ID,
        "capability_id": capability_id,
        "parameters": parameters or {},
        "deadline": deadline or _future_deadline(),
        "required_scope": required_scope,
    }


# ---------------------------------------------------------------------------
# Test: catalog structure
# ---------------------------------------------------------------------------

class TestWindowsCatalog:
    @pytest.fixture(autouse=True)
    def _enable_phase4_catalog(self, monkeypatch):
        monkeypatch.setenv("ADAPTER_INVOKE_READONLY_ENABLED", "true")

    def test_catalog_has_ten_entries(self):
        caps = mod._build_windows_catalog()
        assert len(caps) == 10

    def test_disabled_catalog_keeps_exact_six_legacy(self, monkeypatch):
        monkeypatch.setenv("ADAPTER_INVOKE_READONLY_ENABLED", "false")
        caps = mod._build_windows_catalog()
        assert [item["capability_id"] for item in caps] == [
            "system.health", "system.metrics", "process.list",
            "service.status", "application.list", "audio.device.list",
        ]

    def test_catalog_has_six_phase2_legacy_ids(self):
        caps = mod._build_windows_catalog()
        ids = {c["capability_id"] for c in caps}
        legacy = {"system.health", "system.metrics", "process.list",
                  "service.status", "application.list", "audio.device.list"}
        assert legacy.issubset(ids)

    def test_catalog_has_four_phase4_canonical_ids(self):
        caps = mod._build_windows_catalog()
        ids = {c["capability_id"] for c in caps}
        canonical = {
            "windows.system.metrics.read",
            "windows.application.list",
            "windows.window.list",
            "windows.audio.device.list",
        }
        assert canonical.issubset(ids)

    def test_phase4_entries_have_availability_available(self):
        caps = mod._build_windows_catalog()
        p4 = {
            c["capability_id"]: c for c in caps
            if c["capability_id"].startswith("windows.")
        }
        for cap_id, entry in p4.items():
            assert entry.get("availability") == "AVAILABLE", (
                f"{cap_id} missing availability=AVAILABLE"
            )

    def test_application_list_has_interactive_session_bool(self):
        caps = mod._build_windows_catalog()
        entry = next(c for c in caps if c["capability_id"] == "windows.application.list")
        assert "interactive_session" in entry
        assert isinstance(entry["interactive_session"], bool)

    def test_window_list_has_interactive_session_bool(self):
        caps = mod._build_windows_catalog()
        entry = next(c for c in caps if c["capability_id"] == "windows.window.list")
        assert "interactive_session" in entry
        assert isinstance(entry["interactive_session"], bool)

    def test_audio_device_list_has_hardware_available_bool(self):
        caps = mod._build_windows_catalog()
        entry = next(c for c in caps if c["capability_id"] == "windows.audio.device.list")
        assert "hardware_available" in entry
        assert isinstance(entry["hardware_available"], bool)

    def test_all_entries_platform_windows(self):
        caps = mod._build_windows_catalog()
        for cap in caps:
            assert cap["platform"] == "windows"

    def test_catalog_hash_stable(self):
        caps1 = mod._build_windows_catalog()
        caps2 = mod._build_windows_catalog()
        assert mod._compute_catalog_hash(caps1) == mod._compute_catalog_hash(caps2)

    def test_phase4_risk_class_read_only(self):
        caps = mod._build_windows_catalog()
        for cap in caps:
            if cap["capability_id"].startswith("windows."):
                assert cap["risk_class"] == "READ_ONLY"


# ---------------------------------------------------------------------------
# Test: _handle_invoke dispatch
# ---------------------------------------------------------------------------

class TestHandleInvoke:
    @pytest.fixture(autouse=True)
    def _enable_invoke(self, monkeypatch):
        monkeypatch.setenv("ADAPTER_INVOKE_READONLY_ENABLED", "true")

    def _connector(self) -> mod.AdapterConnector:
        return mod.AdapterConnector()

    def test_invoke_disabled_returns_error(self, monkeypatch):
        monkeypatch.setenv("ADAPTER_INVOKE_READONLY_ENABLED", "false")
        c = self._connector()
        msg = _invoke_message("windows.system.metrics.read", "system.read")
        result = asyncio.run(c._handle_invoke(msg))
        assert result["ok"] is False
        assert result["error_code"] == "invoke_disabled"

    def test_unknown_capability_not_found(self):
        c = self._connector()
        msg = _invoke_message("windows.unknown.cap", "system.read")
        result = asyncio.run(c._handle_invoke(msg))
        assert result["ok"] is False
        assert result["error_code"] == "capability_not_found"

    def test_wrong_adapter_id_rejected(self):
        c = self._connector()
        msg = _invoke_message("windows.system.metrics.read", "system.read",
                              adapter_id="adapter.jarvis.ubuntu")
        result = asyncio.run(c._handle_invoke(msg))
        assert result["ok"] is False
        assert result["error_code"] == "invalid_request"

    def test_wrong_scope_rejected(self):
        c = self._connector()
        msg = _invoke_message("windows.system.metrics.read", "wrong.scope")
        result = asyncio.run(c._handle_invoke(msg))
        assert result["ok"] is False
        assert result["error_code"] == "forbidden_scope"

    def test_expired_deadline_rejected(self):
        c = self._connector()
        msg = _invoke_message("windows.system.metrics.read", "system.read",
                              deadline=_past_deadline())
        result = asyncio.run(c._handle_invoke(msg))
        assert result["ok"] is False
        assert result["error_code"] == "timeout"
        assert result["retryable"] is True

    def test_invalid_uuid_rejected(self):
        c = self._connector()
        msg = _invoke_message("windows.system.metrics.read", "system.read",
                              request_id="not-a-uuid")
        result = asyncio.run(c._handle_invoke(msg))
        assert result["ok"] is False
        assert result["error_code"] == "invalid_request"

    def test_system_metrics_ok(self):
        c = self._connector()
        msg = _invoke_message("windows.system.metrics.read", "system.read")
        result = asyncio.run(c._handle_invoke(msg))
        assert result["ok"] is True
        data = result["result"]
        assert "cpu_percent" in data
        assert "memory" in data
        assert "disk_c" in data

    def test_system_metrics_rejects_parameters(self):
        c = self._connector()
        msg = _invoke_message("windows.system.metrics.read", "system.read",
                              parameters={"unexpected": True})
        result = asyncio.run(c._handle_invoke(msg))
        assert result["ok"] is False
        assert result["error_code"] == "schema_mismatch"

    def test_application_list_ok(self):
        c = self._connector()
        msg = _invoke_message("windows.application.list", "application.read")
        result = asyncio.run(c._handle_invoke(msg))
        assert result["ok"] is True
        apps = result["result"]["applications"]
        assert isinstance(apps, list)
        for app in apps:
            assert "\\" not in app["name"]
            assert "/" not in app["name"]

    def test_application_list_limit_enforced(self):
        c = self._connector()
        msg = _invoke_message("windows.application.list", "application.read",
                              parameters={"limit": 5})
        result = asyncio.run(c._handle_invoke(msg))
        assert result["ok"] is True
        assert len(result["result"]["applications"]) <= 5

    def test_application_list_invalid_limit_rejected(self):
        c = self._connector()
        msg = _invoke_message("windows.application.list", "application.read",
                              parameters={"limit": 999})
        result = asyncio.run(c._handle_invoke(msg))
        assert result["ok"] is False
        assert result["error_code"] == "schema_mismatch"

    def test_application_list_string_limit_rejected(self):
        c = self._connector()
        msg = _invoke_message("windows.application.list", "application.read",
                              parameters={"limit": "5"})
        result = asyncio.run(c._handle_invoke(msg))
        assert result["ok"] is False
        assert result["error_code"] == "schema_mismatch"

    def test_window_list_unavailable_when_session_missing(self, monkeypatch):
        monkeypatch.setattr(mod, "_has_interactive_session", lambda: False)
        c = self._connector()
        msg = _invoke_message("windows.window.list", "window.read")
        result = asyncio.run(c._handle_invoke(msg))
        assert result["ok"] is False
        assert result["error_code"] == "capability_unavailable"

    def test_audio_unavailable_without_hardware(self, monkeypatch):
        monkeypatch.setattr(mod, "_has_audio_hardware", lambda: False)
        c = self._connector()
        msg = _invoke_message("windows.audio.device.list", "catalog.read")
        result = asyncio.run(c._handle_invoke(msg))
        assert result["ok"] is False
        assert result["error_code"] == "capability_unavailable"

    def test_window_list_ok(self):
        c = self._connector()
        msg = _invoke_message("windows.window.list", "window.read")
        result = asyncio.run(c._handle_invoke(msg))
        assert result["ok"] is True
        windows = result["result"]["windows"]
        assert result["result"]["titles_redacted"] is True
        assert isinstance(windows, list)
        for title in windows:
            assert "AURORA" not in title.upper()
            assert "JARVIS" not in title.upper()

    def test_window_list_rejects_parameters(self):
        c = self._connector()
        msg = _invoke_message("windows.window.list", "window.read",
                              parameters={"unexpected": True})
        result = asyncio.run(c._handle_invoke(msg))
        assert result["ok"] is False
        assert result["error_code"] == "schema_mismatch"

    def test_audio_device_list_ok(self):
        c = self._connector()
        msg = _invoke_message("windows.audio.device.list", "catalog.read")
        result = asyncio.run(c._handle_invoke(msg))
        assert result["ok"] is True
        devices = result["result"]["devices"]
        assert isinstance(devices, list)
        for dev in devices:
            assert "name" in dev
            assert "direction" in dev
            assert len(dev["name"]) <= 100

    def test_audio_device_list_rejects_parameters(self):
        c = self._connector()
        msg = _invoke_message("windows.audio.device.list", "catalog.read",
                              parameters={"extra": True})
        result = asyncio.run(c._handle_invoke(msg))
        assert result["ok"] is False
        assert result["error_code"] == "schema_mismatch"


# ---------------------------------------------------------------------------
# Test: allowlist alignment with Core windows_readonly.py
# ---------------------------------------------------------------------------

class TestAllowlistAlignment:
    def test_pilot_capability_ids_match_phase4_spec(self):
        expected = {
            "windows.system.metrics.read",
            "windows.application.list",
            "windows.window.list",
            "windows.audio.device.list",
        }
        assert set(mod._WINDOWS_PILOT_CAPABILITIES.keys()) == expected

    def test_scopes_match_phase4_spec(self):
        expected_scopes = {
            "windows.system.metrics.read": "system.read",
            "windows.application.list": "application.read",
            "windows.window.list": "window.read",
            "windows.audio.device.list": "catalog.read",
        }
        for cap_id, (scope, _timeout) in mod._WINDOWS_PILOT_CAPABILITIES.items():
            assert scope == expected_scopes[cap_id]

    def test_adapter_id_constant(self):
        assert mod.ADAPTER_ID == "adapter.aurora.windows"