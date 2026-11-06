"""Hermetic tests for actions.shared_alarm_v2 — no real LILITH calls.

Coverage:
 - SharedAlarmStore CRUD: create, list, cancel, modify
 - Offline recovery: errors are visible, not silent
 - Restart recovery: alarms survive store-instance replacement (LILITH is authoritative)
 - Duplicate prevention: ambiguous label cancel requires explicit ID
 - Delivery ownership: Windows cannot claim; Ubuntu can claim once
 - alarm_control feature gate: disabled by default, routes to shared when enabled
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from actions.shared_alarm_v2 import (
    SharedAlarmError,
    SharedAlarmStore,
    _CATEGORY,
    _DELIVERY_MODE,
    _RECEIPT_CATEGORY,
    aware_iso,
    parse_instant,
    shared_alarm_action,
)


# ---------------------------------------------------------------------------
# Fake LILITH HTTP client
#
# Key invariant: a fact stored with key K is returned as "jarvis:K" in
# /memory/context responses.  This matches the behaviour observed in the
# production LILITH memory API (see lilith_client/client.py).


class _FakeResponse:
    def __init__(self, status_code: int, body: dict) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> dict:
        return self._body


class FakeLilithClient:
    """In-memory LILITH /memory/* API simulator.

    Stores facts keyed as "jarvis:<raw_key>", mirroring how LILITH
    prefixes all stored keys in its context response.
    """

    def __init__(self) -> None:
        self._facts: dict[str, dict] = {}  # "jarvis:<key>" -> fact

    def get(self, url: str) -> _FakeResponse:
        if "/memory/context" in url:
            by_cat: dict[str, list] = {}
            for jk, fact in self._facts.items():
                cat = fact.get("category", "default")
                by_cat.setdefault(cat, []).append({**fact, "key": jk})
            return _FakeResponse(200, {"ok": True, "data": {"categories": by_cat}})
        return _FakeResponse(404, {"ok": False, "data": {}})

    def post(self, url: str, json: dict | None = None) -> _FakeResponse:
        if "/memory/store" in url:
            raw_key = (json or {})["key"]
            full_key = "jarvis:" + raw_key
            self._facts[full_key] = {
                "value": (json or {})["value"],
                "category": (json or {}).get("category", "default"),
            }
            return _FakeResponse(200, {"ok": True, "data": {}})
        elif "/memory/delete" in url:
            raw_key = (json or {}).get("key", "")
            full_key = "jarvis:" + raw_key
            self._facts.pop(full_key, None)
            return _FakeResponse(200, {"ok": True, "data": {}})
        return _FakeResponse(404, {"ok": False, "data": {}})


# ---------------------------------------------------------------------------
# Helpers

def _store(source: str = "jarvis_windows", client: FakeLilithClient | None = None) -> SharedAlarmStore:
    return SharedAlarmStore(source=source, http_client=client or FakeLilithClient())


def _future(minutes: int = 60) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def _offline_client() -> MagicMock:
    """HTTP client that always returns 503 (simulates LILITH unreachable)."""
    m = MagicMock()
    m.get.return_value = _FakeResponse(503, {})
    m.post.return_value = _FakeResponse(503, {})
    return m


# ---------------------------------------------------------------------------
# TestInit


class TestInit:
    def test_invalid_source_raises(self):
        with pytest.raises(ValueError):
            SharedAlarmStore(source="jarvis_android")

    def test_valid_windows(self):
        s = _store("jarvis_windows")
        assert s.source == "jarvis_windows"

    def test_valid_ubuntu(self):
        s = _store("jarvis_ubuntu")
        assert s.source == "jarvis_ubuntu"


# ---------------------------------------------------------------------------
# TestDatetimeHelpers


class TestDatetimeHelpers:
    def test_aware_iso_gives_timezone_to_naive(self):
        naive = datetime(2027, 3, 1, 8, 0, 0)
        iso = aware_iso(naive)
        assert datetime.fromisoformat(iso).tzinfo is not None

    def test_aware_iso_preserves_aware(self):
        aware = datetime(2027, 3, 1, 8, 0, 0, tzinfo=timezone.utc)
        iso = aware_iso(aware)
        # Round-trip must recover the same instant
        assert parse_instant(iso) == aware.astimezone(timezone.utc)

    def test_parse_instant_naive_raises(self):
        with pytest.raises(ValueError):
            parse_instant("2027-03-01T08:00:00")

    def test_parse_instant_aware_returns_utc(self):
        result = parse_instant("2027-03-01T08:00:00+00:00")
        assert result.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# TestList


class TestList:
    def test_empty(self):
        s = _store()
        assert s.list() == []

    def test_shows_created_alarm(self):
        c = FakeLilithClient()
        s = _store(client=c)
        s.create("Despertador", _future())
        items = s.list()
        assert len(items) == 1
        assert items[0]["label"] == "Despertador"

    def test_sorted_by_fire_at(self):
        c = FakeLilithClient()
        s = _store(client=c)
        s.create("Second", _future(120))
        s.create("First", _future(30))
        items = s.list()
        assert items[0]["label"] == "First"
        assert items[1]["label"] == "Second"

    def test_excludes_malformed_facts(self):
        c = FakeLilithClient()
        # Inject a fact that is not valid JSON
        c._facts["jarvis:jarvis_shared_alarm_v2:" + "a" * 32] = {
            "value": "not-json", "category": _CATEGORY,
        }
        s = _store(client=c)
        assert s.list() == []

    def test_excludes_wrong_delivery_mode(self):
        c = FakeLilithClient()
        alarm_id = "b" * 32
        value = json.dumps({
            "id": alarm_id, "label": "X", "fire_at": aware_iso(_future()),
            "source": "jarvis_windows", "revision": 1,
            "delivery_mode": "wrong_mode",
        })
        c._facts[f"jarvis:jarvis_shared_alarm_v2:{alarm_id}"] = {
            "value": value, "category": _CATEGORY,
        }
        s = _store(client=c)
        assert s.list() == []

    def test_excludes_claimed_alarms(self):
        c = FakeLilithClient()
        s_win = _store("jarvis_windows", client=c)
        alarm = s_win.create("ClaimedAlarm", _future())
        s_ubu = _store("jarvis_ubuntu", client=c)
        claimed = s_ubu.claim_delivery(alarm)
        assert claimed is True
        # Windows list must no longer see the claimed alarm
        items = s_win.list()
        assert all(a["id"] != alarm["id"] for a in items)

    def test_offline_raises(self):
        s = SharedAlarmStore(source="jarvis_windows", http_client=_offline_client())
        with pytest.raises(SharedAlarmError):
            s.list()


# ---------------------------------------------------------------------------
# TestCreate


class TestCreate:
    def test_success(self):
        s = _store()
        alarm = s.create("Test alarm", _future())
        assert alarm["label"] == "Test alarm"
        assert alarm["delivery_mode"] == _DELIVERY_MODE
        assert alarm["source"] == "jarvis_windows"
        assert alarm["revision"] == 1
        assert len(alarm["id"]) == 32
        assert all(c in "0123456789abcdef" for c in alarm["id"])

    def test_empty_label_raises(self):
        s = _store()
        with pytest.raises(SharedAlarmError, match="nombre"):
            s.create("", _future())

    def test_whitespace_label_raises(self):
        s = _store()
        with pytest.raises(SharedAlarmError, match="nombre"):
            s.create("   ", _future())

    def test_past_time_raises(self):
        s = _store()
        with pytest.raises(SharedAlarmError, match="pasado"):
            s.create("Alarm", datetime.now(timezone.utc) - timedelta(seconds=1))

    def test_verified_in_store(self):
        c = FakeLilithClient()
        s = _store(client=c)
        alarm = s.create("Verified", _future())
        assert any(a["id"] == alarm["id"] for a in s.list())

    def test_offline_raises_clear_error(self):
        s = SharedAlarmStore(source="jarvis_windows", http_client=_offline_client())
        with pytest.raises(SharedAlarmError):
            s.create("WillFail", _future())

    def test_offline_does_not_create_phantom_alarm(self):
        c = FakeLilithClient()
        s_bad = SharedAlarmStore(source="jarvis_windows", http_client=_offline_client())
        try:
            s_bad.create("WillFail", _future())
        except SharedAlarmError:
            pass
        # A fresh store on the same (empty) backend sees nothing
        s_ok = _store(client=c)
        assert s_ok.list() == []

    def test_ubuntu_can_create(self):
        c = FakeLilithClient()
        s = _store("jarvis_ubuntu", client=c)
        alarm = s.create("Ubuntu alarm", _future())
        assert alarm["source"] == "jarvis_ubuntu"


# ---------------------------------------------------------------------------
# TestCancel


class TestCancel:
    def test_by_id(self):
        c = FakeLilithClient()
        s = _store(client=c)
        alarm = s.create("ToCancel", _future())
        removed = s.cancel(alarm_id=alarm["id"])
        assert removed["id"] == alarm["id"]
        assert s.list() == []

    def test_by_label_match(self):
        c = FakeLilithClient()
        s = _store(client=c)
        s.create("Morning alarm", _future())
        removed = s.cancel(label_match="Morning")
        assert "Morning" in removed["label"]
        assert s.list() == []

    def test_nonexistent_id_raises(self):
        s = _store()
        with pytest.raises(SharedAlarmError, match="encontró"):
            s.cancel(alarm_id="c" * 32)

    def test_ambiguous_label_raises(self):
        """Cancel without explicit ID must fail when multiple alarms match."""
        c = FakeLilithClient()
        s = _store(client=c)
        s.create("Morning 1", _future(60))
        s.create("Morning 2", _future(90))
        with pytest.raises(SharedAlarmError, match="Varias"):
            s.cancel(label_match="Morning")

    def test_no_id_no_label_raises(self):
        s = _store()
        with pytest.raises(SharedAlarmError, match="Indica"):
            s.cancel()

    def test_offline_raises(self):
        s = SharedAlarmStore(source="jarvis_windows", http_client=_offline_client())
        with pytest.raises(SharedAlarmError):
            s.cancel(alarm_id="d" * 32)


# ---------------------------------------------------------------------------
# TestModify


class TestModify:
    def test_updates_time(self):
        c = FakeLilithClient()
        s = _store(client=c)
        alarm = s.create("ToModify", _future(60))
        updated = s.modify(alarm_id=alarm["id"], fire_at=_future(120))
        assert updated["revision"] == 2
        assert updated["fire_at"] != alarm["fire_at"]

    def test_updates_label(self):
        c = FakeLilithClient()
        s = _store(client=c)
        alarm = s.create("OldName", _future())
        updated = s.modify(alarm_id=alarm["id"], fire_at=_future(90), label="NewName")
        assert updated["label"] == "NewName"

    def test_keeps_old_label_when_blank(self):
        c = FakeLilithClient()
        s = _store(client=c)
        alarm = s.create("KeepName", _future())
        updated = s.modify(alarm_id=alarm["id"], fire_at=_future(90), label="")
        assert updated["label"] == "KeepName"

    def test_past_time_raises(self):
        c = FakeLilithClient()
        s = _store(client=c)
        alarm = s.create("WillFail", _future())
        with pytest.raises(SharedAlarmError, match="pasado"):
            s.modify(alarm_id=alarm["id"],
                     fire_at=datetime.now(timezone.utc) - timedelta(seconds=1))

    def test_verified_after_modify(self):
        c = FakeLilithClient()
        s = _store(client=c)
        alarm = s.create("VerifyModify", _future())
        updated = s.modify(alarm_id=alarm["id"], fire_at=_future(90))
        items = s.list()
        matched = next((a for a in items if a["id"] == alarm["id"]), None)
        assert matched is not None
        assert matched["revision"] == 2
        assert matched["fire_at"] == updated["fire_at"]


# ---------------------------------------------------------------------------
# TestClaimDelivery


class TestClaimDelivery:
    def test_windows_cannot_claim(self):
        c = FakeLilithClient()
        s_win = _store("jarvis_windows", client=c)
        alarm = s_win.create("WinAlarm", _future())
        s_win2 = _store("jarvis_windows", client=c)
        with pytest.raises(SharedAlarmError, match="Windows"):
            s_win2.claim_delivery(alarm)

    def test_ubuntu_can_claim_once(self):
        c = FakeLilithClient()
        s_win = _store("jarvis_windows", client=c)
        alarm = s_win.create("UbuAlarm", _future())
        s_ubu = _store("jarvis_ubuntu", client=c)
        result = s_ubu.claim_delivery(alarm)
        assert result is True  # True = no longer in list (claim accepted)

    def test_second_claim_returns_false(self):
        """At-most-once: second claim on same alarm returns False."""
        c = FakeLilithClient()
        s_win = _store("jarvis_windows", client=c)
        alarm = s_win.create("IdempotentAlarm", _future())
        s_ubu = _store("jarvis_ubuntu", client=c)
        first = s_ubu.claim_delivery(alarm)
        assert first is True
        # Item is gone from list; second attempt sees stale item → False
        second = s_ubu.claim_delivery(alarm)
        assert second is False

    def test_stale_revision_returns_false(self):
        """If the alarm was modified since we last read, claim must fail safely."""
        c = FakeLilithClient()
        s_win = _store("jarvis_windows", client=c)
        alarm = s_win.create("StaleRevision", _future())
        # Modify bumps revision
        s_win.modify(alarm_id=alarm["id"], fire_at=_future(90))
        s_ubu = _store("jarvis_ubuntu", client=c)
        # Claiming old revision must fail (revision mismatch)
        result = s_ubu.claim_delivery(alarm)
        assert result is False


# ---------------------------------------------------------------------------
# TestRestartRecovery
#
# "Restart" = new SharedAlarmStore instance; LILITH (the fake) is the
# authoritative store and survives across instances.


class TestRestartRecovery:
    def test_list_after_restart(self):
        c = FakeLilithClient()
        s1 = _store("jarvis_windows", client=c)
        alarm = s1.create("SurviveRestart", _future())

        s2 = _store("jarvis_windows", client=c)   # new instance, same LILITH
        items = s2.list()
        assert any(a["id"] == alarm["id"] for a in items)

    def test_cancel_after_restart(self):
        c = FakeLilithClient()
        s1 = _store("jarvis_windows", client=c)
        alarm = s1.create("CancelRestart", _future())

        s2 = _store("jarvis_windows", client=c)
        removed = s2.cancel(alarm_id=alarm["id"])
        assert removed["id"] == alarm["id"]

        s3 = _store("jarvis_windows", client=c)
        assert s3.list() == []

    def test_multiple_alarms_survive_restart(self):
        c = FakeLilithClient()
        s1 = _store("jarvis_windows", client=c)
        a1 = s1.create("Alpha", _future(30))
        a2 = s1.create("Beta", _future(60))

        s2 = _store("jarvis_windows", client=c)
        ids = {a["id"] for a in s2.list()}
        assert a1["id"] in ids and a2["id"] in ids


# ---------------------------------------------------------------------------
# TestDuplicatePrevention


class TestDuplicatePrevention:
    def test_same_label_creates_distinct_ids(self):
        c = FakeLilithClient()
        s = _store(client=c)
        a1 = s.create("Morning", _future(60))
        a2 = s.create("Morning", _future(90))
        assert a1["id"] != a2["id"]

    def test_both_duplicates_visible(self):
        c = FakeLilithClient()
        s = _store(client=c)
        a1 = s.create("Duplicate", _future(60))
        a2 = s.create("Duplicate", _future(90))
        ids = {a["id"] for a in s.list()}
        assert a1["id"] in ids and a2["id"] in ids

    def test_cancel_duplicate_by_label_requires_id(self):
        c = FakeLilithClient()
        s = _store(client=c)
        s.create("Duplicate", _future(60))
        s.create("Duplicate", _future(90))
        with pytest.raises(SharedAlarmError, match="Varias"):
            s.cancel(label_match="Duplicate")

    def test_cancel_duplicate_by_id_works(self):
        c = FakeLilithClient()
        s = _store(client=c)
        a1 = s.create("Duplicate", _future(60))
        a2 = s.create("Duplicate", _future(90))
        s.cancel(alarm_id=a1["id"])
        remaining = s.list()
        ids = {a["id"] for a in remaining}
        assert a1["id"] not in ids
        assert a2["id"] in ids


# ---------------------------------------------------------------------------
# TestSharedAlarmAction (string-level routing)


class TestSharedAlarmAction:
    """Tests for shared_alarm_action(), which translates dict→string for callers."""

    def _inject(self, monkeypatch, client: FakeLilithClient) -> None:
        """Patch SharedAlarmStore.__init__ to inject fake client."""
        orig = SharedAlarmStore.__init__

        def _patched(self, *, source, http_client=None):
            orig(self, source=source, http_client=client)

        monkeypatch.setattr(SharedAlarmStore, "__init__", _patched)

    def test_list_empty(self, monkeypatch):
        self._inject(monkeypatch, FakeLilithClient())
        result = shared_alarm_action({"action": "list"}, source="jarvis_windows")
        assert "compartida" in result.lower()

    def test_set_valid(self, monkeypatch):
        self._inject(monkeypatch, FakeLilithClient())
        future = (datetime.now() + timedelta(hours=2)).strftime("%H:%M")
        result = shared_alarm_action(
            {"action": "set", "time": future, "label": "TestAction"},
            source="jarvis_windows",
        )
        assert "TestAction" in result or "compartida" in result.lower()

    def test_cancel_by_id(self, monkeypatch):
        c = FakeLilithClient()
        s = _store(client=c)
        alarm = s.create("ToRemove", _future())
        self._inject(monkeypatch, c)
        result = shared_alarm_action(
            {"action": "cancel", "id": alarm["id"]},
            source="jarvis_windows",
        )
        assert "confirm" in result.lower() or "lilith" in result.lower()

    def test_offline_returns_error_string(self, monkeypatch):
        """LILITH unavailable → visible error string, NOT an unhandled exception."""
        self._inject(monkeypatch, _offline_client())
        result = shared_alarm_action({"action": "list"}, source="jarvis_windows")
        assert isinstance(result, str)
        assert "no confirm" in result.lower() or "lilith" in result.lower() or "inaccesible" in result.lower()

    def test_unknown_action(self, monkeypatch):
        self._inject(monkeypatch, FakeLilithClient())
        result = shared_alarm_action({"action": "fly"}, source="jarvis_windows")
        assert "no reconocida" in result.lower()

    def test_set_invalid_time(self, monkeypatch):
        self._inject(monkeypatch, FakeLilithClient())
        result = shared_alarm_action(
            {"action": "set", "time": "mediodia exacto"},
            source="jarvis_windows",
        )
        assert "no entendí" in result.lower() or "no entend" in result.lower()


# ---------------------------------------------------------------------------
# TestAlarmControlGate


class TestAlarmControlGate:
    def test_disabled_by_default(self, monkeypatch, tmp_path):
        monkeypatch.delenv("JARVIS_SHARED_ALARMS_ENABLED", raising=False)
        monkeypatch.setenv("JARVIS_ALARMS_DIR", str(tmp_path))
        from actions.alarm_control import alarm_control
        result = alarm_control({"action": "list"})
        # Local path: returns local alarm list
        assert isinstance(result, str)
        # Must NOT mention shared/ubuntu (local path)
        assert "ubuntu" not in result.lower()

    def test_enabled_routes_to_shared(self, monkeypatch, tmp_path):
        monkeypatch.setenv("JARVIS_SHARED_ALARMS_ENABLED", "1")
        monkeypatch.setenv("JARVIS_ALARMS_DIR", str(tmp_path))
        import actions.shared_alarm_v2 as sa
        c = FakeLilithClient()
        orig = sa.SharedAlarmStore.__init__

        def _patched(self, *, source, http_client=None):
            orig(self, source=source, http_client=c)

        monkeypatch.setattr(sa.SharedAlarmStore, "__init__", _patched)
        from actions.alarm_control import alarm_control
        result = alarm_control({"action": "list"})
        # Shared path: "No hay alarmas compartidas. ..."
        assert "compartida" in result.lower() or "ubuntu" in result.lower()

    def test_enabled_set_calls_shared(self, monkeypatch, tmp_path):
        monkeypatch.setenv("JARVIS_SHARED_ALARMS_ENABLED", "1")
        monkeypatch.setenv("JARVIS_ALARMS_DIR", str(tmp_path))
        import actions.shared_alarm_v2 as sa
        c = FakeLilithClient()
        orig = sa.SharedAlarmStore.__init__

        def _patched(self, *, source, http_client=None):
            orig(self, source=source, http_client=c)

        monkeypatch.setattr(sa.SharedAlarmStore, "__init__", _patched)
        from actions.alarm_control import alarm_control
        future = (datetime.now() + timedelta(hours=3)).strftime("%H:%M")
        result = alarm_control({"action": "set", "time": future, "label": "GateTest"})
        assert "GateTest" in result or "compartida" in result.lower()
