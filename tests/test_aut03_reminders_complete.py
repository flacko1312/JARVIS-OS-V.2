"""AUT-03 natural parsing and persistent reminder lifecycle."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import main
from actions import reminder as module


MADRID = ZoneInfo("Europe/Madrid")
NOW = datetime(2026, 10, 15, 10, 0, tzinfo=MADRID)


class NaturalDateTests(unittest.TestCase):
    def test_relative_minutes_and_word_hours(self):
        target, error = module._parse_natural_datetime("en 30 minutos", now=NOW)
        self.assertIsNone(error)
        self.assertEqual(target, NOW + timedelta(minutes=30))
        target, error = module._parse_natural_datetime("dentro de dos horas", now=NOW)
        self.assertIsNone(error)
        self.assertEqual(target, NOW + timedelta(hours=2))

    def test_tomorrow_and_day_after_tomorrow(self):
        target, _ = module._parse_natural_datetime("mañana a las 3 de la tarde", now=NOW)
        self.assertEqual(target, datetime(2026, 10, 16, 15, 0, tzinfo=MADRID))
        target, _ = module._parse_natural_datetime("pasado mañana a las 9 de la noche", now=NOW)
        self.assertEqual(target, datetime(2026, 10, 17, 21, 0, tzinfo=MADRID))

    def test_ambiguous_clock_requests_clarification(self):
        target, error = module._parse_natural_datetime("mañana a las 5", now=NOW)
        self.assertIsNone(target)
        self.assertIn("ambigua", error)

    def test_recurring_phrase_is_not_a_local_reminder(self):
        target, error = module._parse_natural_datetime(
            "todos los días a las 9 de la noche", now=NOW
        )
        self.assertIsNone(target)
        self.assertIn("LILITH", error)

    def test_explicit_timezone_is_preserved(self):
        target, error = module._parse_natural_datetime(
            "mañana 21:15", timezone_name="Europe/Paris", now=NOW
        )
        self.assertIsNone(error)
        self.assertEqual(str(target.tzinfo), "Europe/Paris")


class RegistryLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict("os.environ", {"JARVIS_REMINDER_DIR": self.temp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    @staticmethod
    def _record(reminder_id: str, message: str = "prueba") -> dict:
        return {
            "id": reminder_id,
            "message": message,
            "target_at": (datetime.now(MADRID) + timedelta(hours=2)).isoformat(),
            "timezone": "Europe/Madrid",
            "job_id": f"JARVISReminder_{reminder_id}",
            "script_path": str(Path(tempfile.gettempdir()) / f"{reminder_id}.py"),
            "created_at": datetime.now(ZoneInfo("UTC")).isoformat(),
        }

    def test_atomic_registry_survives_reload(self):
        record = self._record("rem_abc123")
        module._save_registry([record])
        self.assertEqual(module._load_registry(), [record])

    def test_list_cancel_and_persistent_removal(self):
        record = self._record("rem_cancel")
        module._save_registry([record])
        self.assertIn("rem_cancel", module.reminder({"action": "list"}))
        with patch.object(module, "_cancel_job", return_value=True):
            result = module.reminder({"action": "cancel", "id": "rem_cancel"})
        self.assertIn("cancelado", result)
        self.assertEqual(module._load_registry(), [])

    def test_duplicate_is_rejected_before_scheduling(self):
        record = self._record("rem_existing", "llamar")
        module._save_registry([record])
        with patch.object(module, "_parse_natural_datetime", return_value=(
            datetime.fromisoformat(record["target_at"]), None
        )), patch.object(module, "_schedule_record") as schedule:
            result = module.reminder({"message": "Llamar", "text": "en dos horas"})
        self.assertIn("Ya existe", result)
        schedule.assert_not_called()

    def test_create_uses_safe_id_and_persists(self):
        record = self._record("rem_0123456789ab")
        with patch.object(module, "_schedule_record", return_value=(record, None)):
            result = module.reminder({"message": "prueba", "text": "en dos horas"})
        self.assertIn("rem_0123456789ab", result)
        self.assertEqual(module._load_registry()[0]["id"], "rem_0123456789ab")

    def test_modify_schedules_new_before_cancelling_old(self):
        old = self._record("rem_modify", "antes")
        new = self._record("rem_modify", "después")
        module._save_registry([old])
        events: list[str] = []
        with patch.object(
            module, "_schedule_record", side_effect=lambda *a, **k: (events.append("schedule") or new, None)
        ), patch.object(
            module, "_cancel_job", side_effect=lambda *a, **k: events.append("cancel") or True
        ):
            result = module.reminder({
                "action": "modify", "id": "rem_modify", "message": "después", "text": "en tres horas"
            })
        self.assertIn("programado", result)
        self.assertEqual(events, ["schedule", "cancel"])
        self.assertEqual(module._load_registry()[0]["message"], "después")

    def test_expired_and_malformed_records_are_cleaned(self):
        expired = self._record("rem_old")
        expired["target_at"] = (datetime.now(MADRID) - timedelta(days=1)).isoformat()
        module._save_registry([expired, {"broken": True}, self._record("rem_active")])
        active = module._cleanup_registry()
        self.assertEqual([item["id"] for item in active], ["rem_active"])


class LiveToolContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_schema_exposes_lifecycle_without_requiring_create_fields(self):
        declaration = next(item for item in main.TOOL_DECLARATIONS if item["name"] == "reminder")
        properties = declaration["parameters"]["properties"]
        self.assertIn("action", properties)
        self.assertIn("id", properties)
        self.assertIn("text", properties)
        self.assertEqual(declaration["parameters"]["required"], [])

    async def test_immediate_list_is_allowed_as_management_not_create(self):
        jarvis = main.JarvisLive.__new__(main.JarvisLive)
        jarvis._schedule_call_turns = {}
        jarvis._schedule_turn_id = "turn-1"
        jarvis._schedule_turn_sequence = 1
        jarvis._schedule_session_id = "session-1"
        jarvis._schedule_guard_routed = False
        jarvis._pending_routine = None
        jarvis._effective_schedule_text = MagicMock(return_value="lista mis recordatorios")
        jarvis._schedule_log = MagicMock()
        jarvis._execute_tool = AsyncMock(return_value=SimpleNamespace(response={"result": "ok"}))
        call = SimpleNamespace(id="fc-rem-list", name="reminder", args={"action": "list"})

        await jarvis._execute_tool_guarded(call)

        jarvis._execute_tool.assert_awaited_once_with(call)
        self.assertEqual(jarvis._schedule_log.call_args.kwargs["decision"], "allowed_reminder_management")


if __name__ == "__main__":
    unittest.main()
