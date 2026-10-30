"""Tests for the AURORA Windows → LILITH adapter connector.

Validates:
- Feature flag gating (OFF = no connections)
- Catalog construction and hash
- Backoff schedule with jitter bounds
- Connector lifecycle (start/stop)
- Stats tracking
- Graceful degradation when LILITH is unavailable
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import unittest
from unittest.mock import patch

from lilith_client.adapter_connector import (
    ADAPTER_ID,
    BACKOFF_SCHEDULE,
    HEARTBEAT_INTERVAL,
    JITTER_FACTOR,
    PROTOCOL_VERSION,
    AdapterConnector,
    _build_windows_catalog,
    _compute_backoff,
    _compute_catalog_hash,
    _is_enabled,
    _get_core_ws_url,
)


class TestFeatureFlag(unittest.TestCase):
    """ADAPTER_CONNECTION_ENABLED defaults to false."""

    def test_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ADAPTER_CONNECTION_ENABLED", None)
            self.assertFalse(_is_enabled())

    def test_enabled_when_true(self):
        with patch.dict(os.environ, {"ADAPTER_CONNECTION_ENABLED": "true"}):
            self.assertTrue(_is_enabled())

    def test_disabled_when_false(self):
        with patch.dict(os.environ, {"ADAPTER_CONNECTION_ENABLED": "false"}):
            self.assertFalse(_is_enabled())

    def test_case_insensitive(self):
        with patch.dict(os.environ, {"ADAPTER_CONNECTION_ENABLED": "TRUE"}):
            self.assertTrue(_is_enabled())


class TestCoreWsUrl(unittest.TestCase):
    """WebSocket URL derived from LILITH_API_URL."""

    def test_http_to_ws(self):
        with patch.dict(os.environ, {"LILITH_API_URL": "http://192.168.1.51:8000"}):
            self.assertEqual(_get_core_ws_url(), "ws://192.168.1.51:8000/api/v1/adapters/connect")

    def test_https_to_wss(self):
        with patch.dict(os.environ, {"LILITH_API_URL": "https://lilith.local"}):
            self.assertEqual(_get_core_ws_url(), "wss://lilith.local/api/v1/adapters/connect")

    def test_missing_url_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("LILITH_API_URL", None)
            with self.assertRaises(ValueError):
                _get_core_ws_url()


class TestWindowsCatalog(unittest.TestCase):
    """Bootstrap catalog has exactly 6 read-only capabilities."""

    def setUp(self):
        self.catalog = _build_windows_catalog()

    def test_count(self):
        self.assertEqual(len(self.catalog), 6)

    def test_capability_ids(self):
        ids = [c["capability_id"] for c in self.catalog]
        self.assertEqual(ids, [
            "system.health", "system.metrics", "process.list",
            "service.status", "application.list", "audio.device.list",
        ])

    def test_all_windows_platform(self):
        for cap in self.catalog:
            self.assertEqual(cap["platform"], "windows")

    def test_all_read_only(self):
        for cap in self.catalog:
            self.assertEqual(cap["risk_class"], "READ_ONLY")
            self.assertEqual(cap["operation_class"], "READ_ONLY")

    def test_schema_version(self):
        for cap in self.catalog:
            self.assertEqual(cap["schema_version"], "1.0")

    def test_version_matches_protocol(self):
        for cap in self.catalog:
            self.assertEqual(cap["version"], PROTOCOL_VERSION)


class TestCatalogHash(unittest.TestCase):
    """Catalog hash is deterministic SHA-256."""

    def test_deterministic(self):
        caps = _build_windows_catalog()
        h1 = _compute_catalog_hash(caps)
        h2 = _compute_catalog_hash(caps)
        self.assertEqual(h1, h2)

    def test_is_sha256(self):
        caps = [{"test": True}]
        canonical = json.dumps(caps, sort_keys=True, separators=(",", ":"))
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        self.assertEqual(_compute_catalog_hash(caps), expected)

    def test_length(self):
        h = _compute_catalog_hash([])
        self.assertEqual(len(h), 64)


class TestBackoff(unittest.TestCase):
    """Bounded backoff with jitter."""

    def test_base_values(self):
        for attempt, expected in enumerate(BACKOFF_SCHEDULE):
            delay = _compute_backoff(attempt)
            self.assertGreaterEqual(delay, expected)
            self.assertLessEqual(delay, expected * (1 + JITTER_FACTOR))

    def test_capped_at_30(self):
        for attempt in range(10, 20):
            delay = _compute_backoff(attempt)
            self.assertLessEqual(delay, 30.0 * (1 + JITTER_FACTOR))

    def test_negative_clamped(self):
        delay = _compute_backoff(-1)
        self.assertGreaterEqual(delay, 1.0)
        self.assertLessEqual(delay, 1.5)


class TestAdapterConstants(unittest.TestCase):
    """Protocol constants match Phase 2 spec."""

    def test_adapter_id(self):
        self.assertEqual(ADAPTER_ID, "adapter.aurora.windows")

    def test_protocol_version(self):
        self.assertEqual(PROTOCOL_VERSION, "1.0.0")

    def test_heartbeat_interval(self):
        self.assertEqual(HEARTBEAT_INTERVAL, 15.0)

    def test_backoff_schedule(self):
        self.assertEqual(BACKOFF_SCHEDULE, (1.0, 2.0, 4.0, 8.0, 15.0, 30.0))


class TestConnectorLifecycle(unittest.TestCase):
    """Connector start/stop when disabled."""

    def test_start_disabled_is_noop(self):
        connector = AdapterConnector()
        with patch.dict(os.environ, {"ADAPTER_CONNECTION_ENABLED": "false"}):
            asyncio.run(connector.start())
            self.assertFalse(connector.is_connected)
            self.assertIsNone(connector._task)

    def test_stats_initial(self):
        connector = AdapterConnector()
        stats = connector.stats
        self.assertEqual(stats["heartbeats_sent"], 0)
        self.assertEqual(stats["heartbeats_acked"], 0)
        self.assertEqual(stats["reconnects"], 0)
        self.assertEqual(stats["errors"], 0)
        self.assertFalse(stats["catalog_published"])

    def test_stop_when_not_started(self):
        connector = AdapterConnector()
        asyncio.run(connector.stop())


class TestNoInvoke(unittest.TestCase):
    """Phase 2 connector has no invoke or cancel methods."""

    def test_no_invoke_method(self):
        self.assertFalse(hasattr(AdapterConnector, 'invoke'))
        self.assertFalse(hasattr(AdapterConnector, 'send_invoke'))
        self.assertFalse(hasattr(AdapterConnector, 'execute'))

    def test_no_cancel_method(self):
        self.assertFalse(hasattr(AdapterConnector, 'cancel'))
        self.assertFalse(hasattr(AdapterConnector, 'send_cancel'))

    def test_no_audio_method(self):
        self.assertFalse(hasattr(AdapterConnector, 'send_audio'))
        self.assertFalse(hasattr(AdapterConnector, 'stream_audio'))


if __name__ == "__main__":
    unittest.main()
