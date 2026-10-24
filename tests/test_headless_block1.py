"""Block 1 tests for JARVIS Headless V1.

Validates:
- HeadlessClient implements JarvisClient Protocol
- HEADLESS_ACTIONS tool profile is correct
- get_tool_declarations(headless=True) returns only allowed tools
- JarvisLive accepts headless=True without importing PyQt
- headless_conversation_store_path is independent from desktop
- No PyQt import contamination when using headless path
"""
from __future__ import annotations

import importlib
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class TestHeadlessClient(unittest.TestCase):
    """HeadlessClient implements JarvisClient Protocol."""

    def test_implements_jarvis_client_protocol(self):
        from core.jarvis_client import JarvisClient
        from headless_client import HeadlessClient

        client = HeadlessClient()
        self.assertIsInstance(client, JarvisClient)

    def test_initial_state(self):
        from headless_client import HeadlessClient

        client = HeadlessClient()
        self.assertFalse(client.muted)
        self.assertIsNone(client.current_file)
        self.assertIsNone(client.on_text_command)
        self.assertEqual(client._state, "STANDBY")

    def test_mute_toggle(self):
        from headless_client import HeadlessClient

        client = HeadlessClient()
        self.assertFalse(client.muted)
        result = client.toggle_mute()
        self.assertTrue(result)
        self.assertTrue(client.muted)
        result = client.toggle_mute()
        self.assertFalse(result)
        self.assertFalse(client.muted)

    def test_muted_setter(self):
        from headless_client import HeadlessClient

        client = HeadlessClient()
        client.muted = True
        self.assertTrue(client.muted)
        client.muted = False
        self.assertFalse(client.muted)

    def test_set_state(self):
        from headless_client import HeadlessClient

        client = HeadlessClient()
        client.set_state("LISTENING")
        self.assertEqual(client._state, "LISTENING")
        client.set_state("standby")
        self.assertEqual(client._state, "STANDBY")

    def test_write_log_no_crash(self):
        from headless_client import HeadlessClient

        client = HeadlessClient()
        client.write_log("SYS: test message")
        client.write_log("")

    def test_noop_methods_no_crash(self):
        from headless_client import HeadlessClient

        client = HeadlessClient()
        client.show_subtitle("hello")
        client.clear_subtitle()
        client.set_theme("dark")
        client.set_graphics_quality("low")
        client.sync_voice_display("Puck")
        client.handle_ui_command("some_action")

    def test_voice_combo_returns_selector(self):
        from headless_client import HeadlessClient

        client = HeadlessClient()
        combo = client._voice_combo
        self.assertEqual(combo.currentIndex(), 0)
        self.assertIsNone(combo.itemData(0))
        self.assertEqual(combo.currentText(), "")

    def test_on_text_command_settable(self):
        from headless_client import HeadlessClient

        client = HeadlessClient()
        called = []
        client.on_text_command = called.append
        client.on_text_command("test")
        self.assertEqual(called, ["test"])

    def test_on_conversation_toggle_settable(self):
        from headless_client import HeadlessClient

        client = HeadlessClient()
        called = []
        client.on_conversation_toggle = lambda: called.append(True) or True
        client.on_conversation_toggle()
        self.assertEqual(called, [True])


class TestHeadlessToolProfile(unittest.TestCase):
    """HEADLESS_ACTIONS allowlist and get_tool_declarations(headless=True)."""

    def test_headless_actions_defined(self):
        from main import HEADLESS_ACTIONS

        self.assertIsInstance(HEADLESS_ACTIONS, frozenset)
        self.assertGreater(len(HEADLESS_ACTIONS), 0)

    def test_headless_actions_are_subset_of_all_tools(self):
        from main import HEADLESS_ACTIONS, TOOL_DECLARATIONS

        all_names = {d["name"] for d in TOOL_DECLARATIONS}
        missing = HEADLESS_ACTIONS - all_names
        self.assertEqual(missing, set(), f"HEADLESS_ACTIONS contains unknown tools: {missing}")

    def test_headless_excludes_windows_tools(self):
        from main import HEADLESS_ACTIONS, LOCAL_MACHINE_ONLY_ACTIONS

        overlap = HEADLESS_ACTIONS & LOCAL_MACHINE_ONLY_ACTIONS
        self.assertEqual(overlap, set(), f"Headless must not include Windows-only tools: {overlap}")

    def test_headless_excludes_dangerous_tools(self):
        from main import HEADLESS_ACTIONS

        forbidden = {
            "browser_control", "screen_process", "code_helper",
            "dev_agent", "agent_task", "game_updater",
        }
        overlap = HEADLESS_ACTIONS & forbidden
        self.assertEqual(overlap, set(), f"Headless must not include: {overlap}")

    def test_headless_includes_required_lilith_tools(self):
        from main import HEADLESS_ACTIONS

        required = {
            "lilith_memory_search",
            "lilith_memory_store",
            "lilith_memory_delete",
            "lilith_home_action",
            "lilith_routine",
        }
        missing = required - HEADLESS_ACTIONS
        self.assertEqual(missing, set(), f"Missing required LILITH tools: {missing}")

    def test_headless_exact_inventory(self):
        from main import HEADLESS_ACTIONS

        EXPECTED_HEADLESS_TOOLS = {
            "web_search",
            "date_time",
            "system_status",
            "disk_status",
            "docker_status",
            "infrastructure_status",
            "service_logs",
            "process_list",
            "process_info",
            "systemd_status",
            "systemd_action",
            "systemd_list_failed",
            "journal_read",
            "lilith_memory_search",
            "lilith_memory_store",
            "lilith_memory_delete",
            "lilith_home_action",
            "lilith_home_status",
            "lilith_health",
            "lilith_routine",
            "open_capabilities_catalog",
        }
        self.assertEqual(
            HEADLESS_ACTIONS,
            EXPECTED_HEADLESS_TOOLS,
            f"Extra: {HEADLESS_ACTIONS - EXPECTED_HEADLESS_TOOLS}, "
            f"Missing: {EXPECTED_HEADLESS_TOOLS - HEADLESS_ACTIONS}",
        )

    def test_get_tool_declarations_headless(self):
        from main import HEADLESS_ACTIONS, get_tool_declarations

        declarations = get_tool_declarations(headless=True)
        names = {d["name"] for d in declarations}
        self.assertEqual(names, HEADLESS_ACTIONS)

    def test_get_tool_declarations_default_unchanged(self):
        from main import TOOL_DECLARATIONS, get_tool_declarations

        declarations = get_tool_declarations()
        self.assertEqual(len(declarations), len(TOOL_DECLARATIONS))

    def test_get_tool_declarations_cloud_safe_unchanged(self):
        from main import CLOUD_SAFE_ACTIONS, get_tool_declarations

        declarations = get_tool_declarations(cloud_safe=True)
        names = {d["name"] for d in declarations}
        self.assertEqual(names, CLOUD_SAFE_ACTIONS)

    def test_headless_flag_wins_over_cloud_safe(self):
        from main import HEADLESS_ACTIONS, get_tool_declarations

        declarations = get_tool_declarations(headless=True, cloud_safe=True)
        names = {d["name"] for d in declarations}
        self.assertEqual(names, HEADLESS_ACTIONS)


class TestJarvisLiveHeadless(unittest.TestCase):
    """JarvisLive accepts headless flag and configures correctly."""

    def test_jarvis_live_accepts_headless(self):
        from headless_client import HeadlessClient
        from main import JarvisLive

        client = HeadlessClient()
        jarvis = JarvisLive(client, "Puck", headless=True)
        self.assertTrue(jarvis.headless)

    def test_jarvis_live_headless_has_correct_tools(self):
        from headless_client import HeadlessClient
        from main import HEADLESS_ACTIONS, JarvisLive

        client = HeadlessClient()
        jarvis = JarvisLive(client, "Puck", headless=True)
        names = {d["name"] for d in jarvis.tool_declarations}
        self.assertEqual(names, HEADLESS_ACTIONS)

    def test_jarvis_live_default_has_all_tools(self):
        from headless_client import HeadlessClient
        from main import TOOL_DECLARATIONS, JarvisLive

        client = HeadlessClient()
        jarvis = JarvisLive(client, "Puck")
        self.assertFalse(jarvis.headless)
        self.assertEqual(len(jarvis.tool_declarations), len(TOOL_DECLARATIONS))

    def test_jarvis_live_headless_conversation_store(self):
        import tempfile
        from headless_client import HeadlessClient
        from main import JarvisLive

        with tempfile.TemporaryDirectory() as tmp:
            store_path = Path(tmp) / "conversation_state_headless.json"
            jarvis = JarvisLive(
                HeadlessClient(),
                "Puck",
                headless=True,
                conversation_store_path=store_path,
            )
            self.assertIsNotNone(jarvis._conversation_store)
            self.assertEqual(jarvis._conversation_store.path, store_path)


class TestHeadlessConversationStorePath(unittest.TestCase):
    """Headless conversation store is separate from desktop."""

    def test_paths_differ(self):
        from headless_main import headless_conversation_store_path
        from memory.conversation_store import default_store_path

        desktop = default_store_path()
        headless = headless_conversation_store_path()
        self.assertNotEqual(desktop, headless)
        self.assertIn("headless", str(headless))

    def test_headless_path_in_memory_dir(self):
        from headless_main import headless_conversation_store_path

        path = headless_conversation_store_path()
        self.assertEqual(path.parent.name, "memory")


class TestNoAudioMode(unittest.TestCase):
    """Block 2: --no-audio skips microphone and speaker."""

    def test_jarvis_live_accepts_no_audio(self):
        from headless_client import HeadlessClient
        from main import JarvisLive

        jarvis = JarvisLive(HeadlessClient(), "Puck", headless=True, no_audio=True)
        self.assertTrue(jarvis.no_audio)

    def test_jarvis_live_no_audio_default_false(self):
        from headless_client import HeadlessClient
        from main import JarvisLive

        jarvis = JarvisLive(HeadlessClient(), "Puck", headless=True)
        self.assertFalse(jarvis.no_audio)

    def test_parse_args_no_audio(self):
        from headless_main import _parse_args

        with patch("sys.argv", ["headless_main.py", "--no-audio"]):
            args = _parse_args()
        self.assertTrue(args.no_audio)

    def test_parse_args_default(self):
        from headless_main import _parse_args

        with patch("sys.argv", ["headless_main.py"]):
            args = _parse_args()
        self.assertFalse(args.no_audio)

    def test_sounddevice_import_is_optional(self):
        import main
        # sd may be None if sounddevice is not available — that's fine for no_audio
        # Just verify main module loads without crashing
        self.assertTrue(hasattr(main, "sd"))


class TestAudioDeviceResolution(unittest.TestCase):
    """Block 3: name-based device selection for headless audio."""

    def test_resolve_device_by_name_returns_none_when_sd_is_none(self):
        import main
        original_sd = main.sd
        try:
            main.sd = None
            from main import _resolve_device_by_name
            self.assertIsNone(_resolve_device_by_name("input", ("anything",)))
        finally:
            main.sd = original_sd

    def test_resolve_device_by_name_returns_index_or_none(self):
        from main import _resolve_device_by_name, sd
        if sd is None:
            self.skipTest("sounddevice not available")
        result = _resolve_device_by_name("input", ("nonexistent-device-xyz",))
        self.assertIsNone(result)

    def test_resolve_skips_device_failing_rate_check(self):
        import main
        original_sd = main.sd
        fake_sd = types.ModuleType("sounddevice")
        fake_sd.query_devices = lambda: [
            {"name": "BadDev (hw:0,0)", "max_input_channels": 2, "max_output_channels": 2},
            {"name": "GoodDev pulse", "max_input_channels": 32, "max_output_channels": 32},
        ]
        def _check_input_ok(device=None, samplerate=None, channels=None, dtype=None):
            if device == 0:
                raise Exception("PaErrorCode -9997")
        fake_sd.check_input_settings = _check_input_ok
        fake_sd.check_output_settings = _check_input_ok
        main.sd = fake_sd
        try:
            from main import _resolve_device_by_name
            result = _resolve_device_by_name("input", ("BadDev",), required_rate=16000)
            self.assertIsNone(result)
            result = _resolve_device_by_name("input", ("BadDev", "GoodDev"), required_rate=16000)
            self.assertEqual(result, 1)
        finally:
            main.sd = original_sd

    def test_device_supports_rate_false_when_sd_none(self):
        import main
        original_sd = main.sd
        main.sd = None
        try:
            from main import _device_supports_rate
            self.assertFalse(_device_supports_rate(0, "input", 16000))
        finally:
            main.sd = original_sd

    def test_headless_input_device_falls_back_to_default(self):
        from main import _headless_input_device, sd
        if sd is None:
            self.skipTest("sounddevice not available")
        idx, name = _headless_input_device()
        self.assertIsInstance(name, str)
        self.assertTrue(len(name) > 0)

    def test_headless_audio_sets_resolvers(self):
        from headless_client import HeadlessClient
        from main import JarvisLive, sd
        if sd is None:
            self.skipTest("sounddevice not available")
        jarvis = JarvisLive(HeadlessClient(), "Puck", headless=True, no_audio=False)
        self.assertTrue(hasattr(jarvis, "_audio_input_device_resolver"))
        self.assertTrue(hasattr(jarvis, "_audio_output_device_id"))

    def test_no_audio_does_not_set_resolvers(self):
        from headless_client import HeadlessClient
        from main import JarvisLive
        jarvis = JarvisLive(HeadlessClient(), "Puck", headless=True, no_audio=True)
        self.assertFalse(hasattr(jarvis, "_audio_output_device_id"))

    def test_headless_hints_include_pulse_fallback(self):
        from main import _HEADLESS_INPUT_HINTS, _HEADLESS_OUTPUT_HINTS
        self.assertIn("pulse", _HEADLESS_INPUT_HINTS)
        self.assertIn("pulse", _HEADLESS_OUTPUT_HINTS)
        self.assertIn("default", _HEADLESS_INPUT_HINTS)
        self.assertIn("default", _HEADLESS_OUTPUT_HINTS)


class TestNoPyQtContamination(unittest.TestCase):
    """Importing headless modules must not pull in PyQt."""

    def test_headless_client_no_pyqt(self):
        pyqt_modules = {k for k in sys.modules if "PyQt" in k}
        import headless_client  # noqa: F401
        new_pyqt = {k for k in sys.modules if "PyQt" in k} - pyqt_modules
        self.assertEqual(new_pyqt, set(), f"headless_client imported PyQt: {new_pyqt}")

    def test_headless_main_module_no_pyqt(self):
        pyqt_before = {k for k in sys.modules if "PyQt" in k}
        from headless_main import headless_conversation_store_path  # noqa: F401
        new_pyqt = {k for k in sys.modules if "PyQt" in k} - pyqt_before
        self.assertEqual(new_pyqt, set(), f"headless_main imported PyQt: {new_pyqt}")


class TestDailyTimeFromText(unittest.TestCase):
    """Block 3 regression: PM→24h conversion in schedule_safety."""

    def _parse(self, text):
        from core.schedule_safety import daily_time_from_text
        return daily_time_from_text(text)

    def test_930_de_la_noche(self):
        self.assertEqual(self._parse("9:30 de la noche"), (21, 30))

    def test_930_pm(self):
        self.assertEqual(self._parse("9:30 PM"), (21, 30))

    def test_930_de_la_manana(self):
        self.assertEqual(self._parse("9:30 de la mañana"), (9, 30))

    def test_930_am(self):
        self.assertEqual(self._parse("9:30 AM"), (9, 30))

    def test_12_de_la_noche(self):
        self.assertEqual(self._parse("12 de la noche"), (0, 0))

    def test_12_del_mediodia(self):
        self.assertEqual(self._parse("12 del mediodía"), (12, 0))

    def test_10_de_la_noche(self):
        self.assertEqual(self._parse("10 de la noche"), (22, 0))

    def test_1_de_la_tarde(self):
        self.assertEqual(self._parse("1 de la tarde"), (13, 0))

    def test_6_de_la_manana(self):
        self.assertEqual(self._parse("6 de la mañana"), (6, 0))

    def test_2130_unambiguous(self):
        self.assertEqual(self._parse("21:30"), (21, 30))

    def test_0930_no_period_ambiguous(self):
        self.assertIsNone(self._parse("9:30"))

    def test_todos_los_dias_a_las_9_de_la_noche(self):
        self.assertEqual(self._parse("todos los días a las 9 de la noche"), (21, 0))

    def test_a_las_nueve_de_la_noche(self):
        self.assertEqual(self._parse("a las nueve de la noche"), (21, 0))

    def test_12_pm(self):
        self.assertEqual(self._parse("12 PM"), (12, 0))

    def test_12_am(self):
        self.assertEqual(self._parse("12 AM"), (0, 0))

    def test_1130_pm(self):
        self.assertEqual(self._parse("11:30 PM"), (23, 30))

    def test_1130_am(self):
        self.assertEqual(self._parse("11:30 AM"), (11, 30))

    def test_a_las_3_de_la_tarde(self):
        self.assertEqual(self._parse("a las 3 de la tarde"), (15, 0))

    def test_encender_bombilla_a_las_930_de_la_noche(self):
        self.assertEqual(
            self._parse("encender bombilla lila a las 9:30 de la noche"),
            (21, 30),
        )


class TestAbsorbCallTimeNormalization(unittest.TestCase):
    """Block 3 regression: absorb_call must not trust raw 12h schedule from Gemini."""

    def _make_pending(self, text=""):
        from main import PendingRoutineState
        p = PendingRoutineState(
            session_id="test", origin_turn=0, last_turn=0,
        )
        if text:
            p.observe_text(text, 0)
        return p

    def test_observe_text_overrides_gemini_schedule(self):
        p = self._make_pending("encender bombilla a las 9:30 de la noche todos los días")
        self.assertEqual(p.hour, 21)
        self.assertEqual(p.minute, 30)
        p.absorb_call({"schedule": {"hour": 9, "minute": 30}})
        self.assertEqual(p.hour, 21)
        self.assertEqual(p.minute, 30)

    def test_absorb_call_normalizes_schedule_with_description(self):
        p = self._make_pending()
        p.absorb_call({
            "schedule": {"hour": 9, "minute": 30},
            "description": "encender bombilla a las 9:30 de la noche",
        })
        self.assertEqual(p.hour, 21)
        self.assertEqual(p.minute, 30)

    def test_absorb_call_uses_raw_hour_when_no_period_context(self):
        p = self._make_pending()
        p.absorb_call({"schedule": {"hour": 14, "minute": 0}})
        self.assertEqual(p.hour, 14)
        self.assertEqual(p.minute, 0)


class TestUserConfirmed(unittest.TestCase):
    """Block 3 regression: deterministic confirmation detection."""

    def _check(self, text):
        from core.schedule_safety import user_confirmed
        return user_confirmed(text)

    def test_si_confirms(self):
        self.assertTrue(self._check("sí"))

    def test_yes_confirms(self):
        self.assertTrue(self._check("yes"))

    def test_ok_confirms(self):
        self.assertTrue(self._check("ok"))

    def test_vale_confirms(self):
        self.assertTrue(self._check("vale"))

    def test_dale_confirms(self):
        self.assertTrue(self._check("dale"))

    def test_hazlo_confirms(self):
        self.assertTrue(self._check("hazlo"))

    def test_no_rejects(self):
        self.assertFalse(self._check("no"))

    def test_cancela_rejects(self):
        self.assertFalse(self._check("cancela"))

    def test_cancelalo_rejects(self):
        self.assertFalse(self._check("cancélalo"))

    def test_mejor_no_rejects(self):
        self.assertFalse(self._check("mejor no"))

    def test_empty_ambiguous(self):
        self.assertIsNone(self._check(""))

    def test_random_ambiguous(self):
        self.assertIsNone(self._check("cuéntame más"))


class TestRoutineConfirmationGate(unittest.TestCase):
    """Block 3 regression: routine mutations require explicit confirmation."""

    def _make_jarvis(self):
        from headless_client import HeadlessClient
        from main import JarvisLive
        jarvis = JarvisLive(HeadlessClient(), "Puck", headless=True, no_audio=True)
        jarvis._schedule_session_id = "test-session"
        jarvis._schedule_turn_id = "turn-1"
        jarvis._schedule_turn_sequence = 1
        jarvis._schedule_turn_source = "voice"
        jarvis._current_input_transcript = "crear rutina encender bombilla a las 9 de la noche todos los días"
        jarvis._schedule_guard_routed = False
        return jarvis

    def test_stash_creates_pending_confirmation(self):
        jarvis = self._make_jarvis()
        args = {
            "operation": "create",
            "name": "encender bombilla",
            "schedule": {"hour": 21, "minute": 0},
            "timezone": "Europe/Madrid",
        }
        conf = jarvis._stash_routine_confirmation("fc-1", "lilith_routine", "create", args)
        self.assertIsNotNone(conf)
        self.assertEqual(conf.operation, "create")
        self.assertIsNone(conf.confirmed)
        self.assertIn("encender bombilla", conf.summary)

    def test_confirmation_accepts_si(self):
        jarvis = self._make_jarvis()
        jarvis._stash_routine_confirmation("fc-1", "lilith_routine", "create", {"operation": "create"})
        result = jarvis._check_routine_confirmation("sí")
        self.assertTrue(result)

    def test_confirmation_rejects_no(self):
        jarvis = self._make_jarvis()
        jarvis._stash_routine_confirmation("fc-1", "lilith_routine", "create", {"operation": "create"})
        result = jarvis._check_routine_confirmation("no")
        self.assertFalse(result)
        self.assertIsNone(jarvis._routine_confirmation)

    def test_confirmation_expires_after_turn_gap(self):
        jarvis = self._make_jarvis()
        jarvis._stash_routine_confirmation("fc-1", "lilith_routine", "create", {"operation": "create"})
        jarvis._schedule_turn_sequence = 10
        result = jarvis._check_routine_confirmation("sí")
        self.assertIsNone(result)
        self.assertIsNone(jarvis._routine_confirmation)

    def test_confirmation_clears_on_session_mismatch(self):
        jarvis = self._make_jarvis()
        jarvis._stash_routine_confirmation("fc-1", "lilith_routine", "create", {"operation": "create"})
        jarvis._schedule_session_id = "different-session"
        result = jarvis._check_routine_confirmation("sí")
        self.assertIsNone(result)

    def test_double_confirmation_does_not_duplicate(self):
        jarvis = self._make_jarvis()
        jarvis._stash_routine_confirmation("fc-1", "lilith_routine", "create", {"operation": "create"})
        result1 = jarvis._check_routine_confirmation("sí")
        self.assertTrue(result1)
        self.assertIsNone(jarvis._check_routine_confirmation("sí"))

    def test_pending_confirmation_summary_delete(self):
        jarvis = self._make_jarvis()
        conf = jarvis._stash_routine_confirmation("fc-2", "lilith_routine", "delete", {"routine_id": 5})
        self.assertIn("Eliminar", conf.summary)
        self.assertIn("5", conf.summary)

    def test_pending_confirmation_summary_enable(self):
        jarvis = self._make_jarvis()
        conf = jarvis._stash_routine_confirmation("fc-3", "lilith_routine", "enable", {"routine_id": 7})
        self.assertIn("Activar", conf.summary)

    def test_pending_confirmation_summary_disable(self):
        jarvis = self._make_jarvis()
        conf = jarvis._stash_routine_confirmation("fc-4", "lilith_routine", "disable", {"routine_id": 3})
        self.assertIn("Desactivar", conf.summary)


class TestPlaybackStreamLifecycle(unittest.TestCase):
    """Block 3: headless playback stream opens lazily and closes on drain."""

    def test_headless_uses_lazy_lifecycle(self):
        from headless_client import HeadlessClient
        from main import JarvisLive
        jarvis = JarvisLive(HeadlessClient(), "Puck", headless=True, no_audio=False)
        self.assertTrue(jarvis.headless)
        self.assertFalse(jarvis.no_audio)
        self.assertFalse(jarvis.external_audio)

    def test_desktop_does_not_use_lazy_lifecycle(self):
        from headless_client import HeadlessClient
        from main import JarvisLive
        jarvis = JarvisLive(HeadlessClient(), "Puck", headless=False, no_audio=False)
        self.assertFalse(jarvis.headless)

    def test_close_playback_stream_handles_none(self):
        import threading
        from main import JarvisLive
        jarvis = object.__new__(JarvisLive)
        jarvis._playback_stream_lock = threading.Lock()
        jarvis._close_playback_stream(None)

    def test_close_playback_stream_handles_exception(self):
        import threading
        from main import JarvisLive

        class FakeStream:
            def stop(self): raise RuntimeError("test")
            def close(self): pass

        jarvis = object.__new__(JarvisLive)
        jarvis._playback_stream_lock = threading.Lock()
        jarvis._close_playback_stream(FakeStream())

    def test_silence_prime_headless(self):
        """Headless _open_playback_stream writes silence to prime the buffer."""
        from unittest.mock import patch, MagicMock
        from main import JarvisLive, CHUNK_SIZE, CHANNELS

        expected_bytes = CHUNK_SIZE * CHANNELS * 2
        fake_stream = MagicMock()
        with patch("main.sd") as mock_sd:
            mock_sd.RawOutputStream.return_value = fake_stream
            jarvis = object.__new__(JarvisLive)
            jarvis.headless = True
            jarvis._audio_output_device_id = None
            stream = jarvis._open_playback_stream()
            fake_stream.start.assert_called_once()
            fake_stream.write.assert_called_once()
            written = fake_stream.write.call_args[0][0]
            self.assertEqual(len(written), expected_bytes)
            self.assertEqual(written, b"\x00" * expected_bytes)

    def test_silence_prime_not_desktop(self):
        """Desktop _open_playback_stream does NOT write silence."""
        from unittest.mock import patch, MagicMock
        from main import JarvisLive

        fake_stream = MagicMock()
        with patch("main.sd") as mock_sd:
            mock_sd.RawOutputStream.return_value = fake_stream
            jarvis = object.__new__(JarvisLive)
            jarvis.headless = False
            jarvis._audio_output_device_id = None
            stream = jarvis._open_playback_stream()
            fake_stream.start.assert_called_once()
            fake_stream.write.assert_not_called()


class Test1008RecoverableDisconnect(unittest.TestCase):
    """Block 3: error 1008 'Requested entity was not found' triggers reconnection."""

    def test_session_not_found_classic(self):
        from main import _is_session_not_found_1008
        exc = Exception("1008 None. Session not found.")
        self.assertTrue(_is_session_not_found_1008(exc))

    def test_requested_entity_not_found(self):
        from main import _is_session_not_found_1008
        exc = Exception("1008 None. Requested entity was not found.")
        self.assertTrue(_is_session_not_found_1008(exc))

    def test_1008_unrelated_message_not_matched(self):
        from main import _is_session_not_found_1008
        exc = Exception("1008 policy violation: rate limit")
        self.assertFalse(_is_session_not_found_1008(exc))

    def test_recoverable_includes_entity_not_found(self):
        from main import _is_recoverable_live_disconnect
        exc = Exception("1008 None. Requested entity was not found.")
        self.assertTrue(_is_recoverable_live_disconnect(exc))

    def test_exception_group_with_entity_not_found(self):
        from main import _is_recoverable_live_disconnect
        inner = Exception("1008 None. Requested entity was not found.")
        group = ExceptionGroup("unhandled errors", [inner])
        self.assertTrue(_is_recoverable_live_disconnect(group))


class TestSingleInstanceLock(unittest.TestCase):
    """Block 3: headless single-instance protection via PID lockfile."""

    def test_acquire_lock_succeeds_when_no_file(self):
        import tempfile
        from unittest.mock import patch
        from headless_main import _acquire_instance_lock, _release_instance_lock, _LOCK_PATH
        with tempfile.TemporaryDirectory() as tmp:
            fake_lock = Path(tmp) / ".headless.pid"
            with patch("headless_main._LOCK_PATH", fake_lock):
                self.assertTrue(_acquire_instance_lock())
                self.assertTrue(fake_lock.exists())
                self.assertEqual(fake_lock.read_text().strip(), str(os.getpid()))
                _release_instance_lock()
                self.assertFalse(fake_lock.exists())

    def test_acquire_lock_fails_when_pid_alive(self):
        import tempfile
        from unittest.mock import patch
        from headless_main import _acquire_instance_lock
        with tempfile.TemporaryDirectory() as tmp:
            fake_lock = Path(tmp) / ".headless.pid"
            fake_lock.write_text(str(os.getpid()))
            with patch("headless_main._LOCK_PATH", fake_lock):
                if sys.platform == "linux":
                    self.assertFalse(_acquire_instance_lock())
                else:
                    self.assertTrue(_acquire_instance_lock())

    def test_acquire_lock_succeeds_when_pid_stale(self):
        import tempfile
        from unittest.mock import patch
        from headless_main import _acquire_instance_lock, _release_instance_lock
        with tempfile.TemporaryDirectory() as tmp:
            fake_lock = Path(tmp) / ".headless.pid"
            fake_lock.write_text("999999999")
            with patch("headless_main._LOCK_PATH", fake_lock):
                self.assertTrue(_acquire_instance_lock())
                _release_instance_lock()

    def test_release_only_own_pid(self):
        import tempfile
        from unittest.mock import patch
        from headless_main import _release_instance_lock
        with tempfile.TemporaryDirectory() as tmp:
            fake_lock = Path(tmp) / ".headless.pid"
            fake_lock.write_text("12345")
            with patch("headless_main._LOCK_PATH", fake_lock):
                _release_instance_lock()
                self.assertTrue(fake_lock.exists())


class TestLiveModelMigration(unittest.TestCase):
    """Block 3: headless uses the working native-audio model; desktop stays unchanged."""

    def test_headless_default_model(self):
        from core.live_model import HEADLESS_LIVE_MODEL
        self.assertEqual(HEADLESS_LIVE_MODEL, "models/gemini-2.5-flash-native-audio-latest")

    def test_desktop_default_model(self):
        from core.live_model import DEFAULT_LIVE_MODEL
        self.assertEqual(DEFAULT_LIVE_MODEL, "models/gemini-2.5-flash-native-audio-preview-12-2025")

    def test_configured_live_model_headless(self):
        import tempfile
        from core.live_model import configured_live_model, HEADLESS_LIVE_MODEL
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "api_keys.json"
            cfg.write_text("{}")
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("GEMINI_LIVE_MODEL", None)
                result = configured_live_model(cfg, headless=True)
                self.assertEqual(result, HEADLESS_LIVE_MODEL)

    def test_configured_live_model_desktop(self):
        import tempfile
        from core.live_model import configured_live_model, DEFAULT_LIVE_MODEL
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "api_keys.json"
            cfg.write_text("{}")
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("GEMINI_LIVE_MODEL", None)
                result = configured_live_model(cfg, headless=False)
                self.assertEqual(result, DEFAULT_LIVE_MODEL)

    def test_env_override_wins(self):
        import tempfile
        from core.live_model import configured_live_model
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "api_keys.json"
            cfg.write_text("{}")
            with patch.dict(os.environ, {"GEMINI_LIVE_MODEL": "models/custom-model"}, clear=False):
                result = configured_live_model(cfg, headless=True)
                self.assertEqual(result, "models/custom-model")

    def test_thinking_config_omitted_for_38_live(self):
        from unittest.mock import MagicMock
        from main import JarvisLive
        from headless_client import HeadlessClient
        jarvis = JarvisLive(HeadlessClient(), "Kore", headless=True, no_audio=True)
        config = jarvis._build_config(live_model_id="gemini-3.8-live")
        self.assertIsNone(config.thinking_config)

    def test_thinking_config_present_for_old_model(self):
        from unittest.mock import MagicMock
        from main import JarvisLive
        from headless_client import HeadlessClient
        jarvis = JarvisLive(HeadlessClient(), "Kore", headless=True, no_audio=True)
        config = jarvis._build_config(
            live_model_id="gemini-2.5-flash-native-audio-preview-12-2025"
        )
        self.assertIsNotNone(config.thinking_config)

    def test_voice_preserved_kore(self):
        from main import JarvisLive
        from headless_client import HeadlessClient
        jarvis = JarvisLive(HeadlessClient(), "Kore", headless=True, no_audio=True)
        config = jarvis._build_config(live_model_id="gemini-3.8-live")
        voice = config.speech_config.voice_config.prebuilt_voice_config.voice_name
        self.assertEqual(voice.lower(), "kore")

    def test_tool_declarations_unchanged_after_migration(self):
        from main import JarvisLive, HEADLESS_ACTIONS
        from headless_client import HeadlessClient
        jarvis = JarvisLive(HeadlessClient(), "Kore", headless=True, no_audio=True)
        self.assertEqual(
            {d["name"] for d in jarvis.tool_declarations},
            HEADLESS_ACTIONS,
        )

    def test_session_resumption_config_present(self):
        from main import JarvisLive
        from headless_client import HeadlessClient
        jarvis = JarvisLive(HeadlessClient(), "Kore", headless=True, no_audio=True)
        config = jarvis._build_config(live_model_id="gemini-3.8-live")
        self.assertIsNotNone(config.session_resumption)


if __name__ == "__main__":
    unittest.main()
