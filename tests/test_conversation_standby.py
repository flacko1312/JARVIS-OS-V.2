import asyncio
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import main


class FakeUI:
    def __init__(self):
        self.states = []
        self.logs = []
        self.muted = False
        self.on_text_command = None
        self.on_conversation_toggle = None

    def set_state(self, state):
        self.states.append(state)

    def write_log(self, text):
        self.logs.append(text)


class ConversationStandbyTests(unittest.IsolatedAsyncioTestCase):
    def make_jarvis(self):
        ui = FakeUI()
        jarvis = main.JarvisLive(ui, cloud_safe=True, api_key="test")
        return jarvis, ui

    async def test_starts_in_standby_without_connecting_or_sending_audio(self):
        jarvis, ui = self.make_jarvis()
        jarvis._run_live = AsyncMock()
        jarvis._listen_audio = AsyncMock()
        jarvis._announce_startup = AsyncMock()
        with patch.object(main.genai, "Client") as client_factory:
            task = asyncio.create_task(jarvis.run())
            await asyncio.sleep(0.08)

            self.assertEqual(jarvis.conversation_state, main.ConversationState.STANDBY)
            jarvis._run_live.assert_not_awaited()
            jarvis._listen_audio.assert_not_awaited()
            jarvis._announce_startup.assert_not_awaited()
            client_factory.assert_not_called()
            self.assertFalse(await jarvis.send_audio_chunk(b"audio"))

            jarvis.request_shutdown()
            await asyncio.wait_for(task, 1)

    async def test_start_stop_and_start_again_reuses_runtime(self):
        jarvis, ui = self.make_jarvis()
        sessions = []

        async def fake_live():
            session = SimpleNamespace(close=AsyncMock())
            sessions.append(session)
            jarvis.session = session
            jarvis._set_conversation_state(main.ConversationState.LISTENING)
            while jarvis._conversation_requested.is_set():
                await asyncio.sleep(0.01)
            jarvis.session = None

        jarvis._run_live = fake_live
        task = asyncio.create_task(jarvis.run())
        await asyncio.sleep(0.02)

        self.assertTrue(jarvis.start_conversation())
        self.assertFalse(jarvis.start_conversation())
        await self._wait_for(lambda: len(sessions) == 1)
        self.assertEqual(jarvis.conversation_state, main.ConversationState.LISTENING)
        jarvis._session_resumption_handle = "logical-conversation-handle"
        conversation_id = jarvis._conversation_id
        jarvis._remember_conversation_text("user", "recuerda este contexto")
        self.assertTrue(jarvis.stop_conversation())
        self.assertEqual(jarvis._session_resumption_handle, "logical-conversation-handle")
        await self._wait_for(lambda: jarvis.conversation_state == main.ConversationState.STANDBY)
        self.assertEqual(jarvis._session_resumption_handle, "logical-conversation-handle")

        self.assertTrue(jarvis.start_conversation())
        await self._wait_for(lambda: len(sessions) == 2)
        self.assertEqual(jarvis.conversation_state, main.ConversationState.LISTENING)
        self.assertEqual(jarvis._conversation_id, conversation_id)
        self.assertEqual(jarvis._conversation_continuity[0]["text"], "recuerda este contexto")

        self.assertTrue(jarvis.stop_conversation())
        await self._wait_for(lambda: jarvis.conversation_state == main.ConversationState.STANDBY)
        self.assertTrue(jarvis.start_conversation())
        await self._wait_for(lambda: len(sessions) == 3)
        self.assertEqual(jarvis._conversation_id, conversation_id)
        self.assertEqual(jarvis._conversation_continuity[0]["text"], "recuerda este contexto")

        jarvis.request_shutdown()
        await asyncio.wait_for(task, 1)
        self.assertEqual(len(sessions), 3)

    async def test_connection_failure_returns_to_standby_and_reports_error(self):
        jarvis, ui = self.make_jarvis()
        jarvis._remember_conversation_text("user", "continuidad antes del fallo")
        continuity = list(jarvis._conversation_continuity)
        summary = jarvis._rolling_conversation_summary
        conversation_id = jarvis._conversation_id

        class BrokenConnect:
            async def __aenter__(self):
                raise RuntimeError("connect boom")

            async def __aexit__(self, *_args):
                return False

        client = SimpleNamespace(
            aio=SimpleNamespace(
                live=SimpleNamespace(connect=lambda **_kwargs: BrokenConnect())
            )
        )
        with (
            patch.object(main.genai, "Client", return_value=client),
            patch.object(main, "pick_live_model", return_value="models/test-live"),
        ):
            task = asyncio.create_task(jarvis.run())
            await asyncio.sleep(0.02)
            jarvis.start_conversation()
            await self._wait_for(
                lambda: jarvis.conversation_state == main.ConversationState.STANDBY
                and any("connect boom" in line for line in ui.logs)
            )
            jarvis.request_shutdown()
            await asyncio.wait_for(task, 1)
        self.assertEqual(jarvis._conversation_id, conversation_id)
        self.assertEqual(jarvis._conversation_continuity, continuity)
        self.assertEqual(jarvis._rolling_conversation_summary, summary)

    async def test_shutdown_works_from_standby_and_active(self):
        standby, _ = self.make_jarvis()
        standby.request_shutdown()
        self.assertTrue(standby._shutdown_requested.is_set())

        active, _ = self.make_jarvis()
        active._loop = asyncio.get_running_loop()
        active._conversation_requested.set()
        active.session = SimpleNamespace(close=AsyncMock())
        active.out_queue = asyncio.Queue()
        active.request_shutdown()
        await asyncio.sleep(0)
        self.assertTrue(active._shutdown_requested.is_set())
        self.assertFalse(active._conversation_requested.is_set())

    async def test_reconnects_are_silent_bounded_and_keep_resumption_handle(self):
        jarvis, ui = self.make_jarvis()
        jarvis.external_audio = True
        jarvis._conversation_requested.set()
        jarvis._wait_before_reconnect = AsyncMock()
        jarvis._announce_startup = AsyncMock()
        connects = []

        class FailingSession:
            async def receive(self):
                yield SimpleNamespace(
                    session_resumption_update=SimpleNamespace(
                        resumable=True, new_handle="resume-1"
                    ),
                    go_away=None,
                    server_content=None,
                    tool_call=None,
                )
                raise ConnectionResetError("network dropped")

            async def send_realtime_input(self, **_kwargs):
                return None

            async def close(self):
                return None

        class ConnectContext:
            async def __aenter__(self):
                connects.append(True)
                return FailingSession()

            async def __aexit__(self, *_args):
                return False

        client = SimpleNamespace(
            aio=SimpleNamespace(
                live=SimpleNamespace(connect=lambda **_kwargs: ConnectContext())
            )
        )
        with (
            patch.object(main.genai, "Client", return_value=client),
            patch.object(main, "pick_live_model", return_value="models/test-live"),
            patch.object(main.traceback, "print_exc") as print_traceback,
        ):
            await jarvis._run_live()

        self.assertEqual(len(connects), 1 + main.MAX_LIVE_RECONNECT_ATTEMPTS)
        jarvis._announce_startup.assert_awaited_once()
        self.assertEqual(jarvis._session_resumption_handle, "resume-1")
        self.assertIn("RECONNECTING", ui.states)
        self.assertTrue(any("reconnect attempts" in line for line in ui.logs))
        print_traceback.assert_not_called()

    async def test_stop_during_reconnect_backoff_cancels_without_new_connect(self):
        jarvis, ui = self.make_jarvis()
        jarvis.external_audio = True
        connects = []

        class EndedSession:
            async def receive(self):
                raise ConnectionResetError("network dropped")
                yield

            async def send_realtime_input(self, **_kwargs):
                return None

            async def close(self):
                return None

        class ConnectContext:
            async def __aenter__(self):
                connects.append(True)
                return EndedSession()

            async def __aexit__(self, *_args):
                return False

        client = SimpleNamespace(
            aio=SimpleNamespace(
                live=SimpleNamespace(connect=lambda **_kwargs: ConnectContext())
            )
        )
        with (
            patch.object(main.genai, "Client", return_value=client),
            patch.object(main, "pick_live_model", return_value="models/test-live"),
            patch.object(main.traceback, "print_exc") as print_traceback,
        ):
            task = asyncio.create_task(jarvis.run())
            await asyncio.sleep(0.02)
            self.assertTrue(jarvis.start_conversation())
            await self._wait_for(
                lambda: jarvis.conversation_state == main.ConversationState.RECONNECTING
            )
            self.assertTrue(jarvis.stop_conversation())
            await self._wait_for(
                lambda: jarvis.conversation_state == main.ConversationState.STANDBY
            )
            await asyncio.sleep(0.08)
            self.assertEqual(len(connects), 1)
            print_traceback.assert_not_called()
            jarvis.request_shutdown()
            await asyncio.wait_for(task, 1)

    async def test_receive_end_after_stop_never_reconnects(self):
        jarvis, _ = self.make_jarvis()
        jarvis.external_audio = True
        connects = []

        class StopSession:
            async def receive(self):
                jarvis.stop_conversation()
                if False:
                    yield None

            async def send_realtime_input(self, **_kwargs):
                return None

            async def close(self):
                return None

        class ConnectContext:
            async def __aenter__(self):
                connects.append(True)
                return StopSession()

            async def __aexit__(self, *_args):
                return False

        client = SimpleNamespace(
            aio=SimpleNamespace(
                live=SimpleNamespace(connect=lambda **_kwargs: ConnectContext())
            )
        )
        with (
            patch.object(main.genai, "Client", return_value=client),
            patch.object(main, "pick_live_model", return_value="models/test-live"),
        ):
            task = asyncio.create_task(jarvis.run())
            await asyncio.sleep(0.02)
            jarvis.start_conversation()
            await self._wait_for(
                lambda: jarvis.conversation_state == main.ConversationState.STANDBY
                and len(connects) == 1
            )
            await asyncio.sleep(0.05)
            self.assertEqual(len(connects), 1)
            jarvis.request_shutdown()
            await asyncio.wait_for(task, 1)

    async def test_single_live_runner_guard_prevents_parallel_sessions(self):
        jarvis, _ = self.make_jarvis()
        jarvis._conversation_requested.set()
        entered = asyncio.Event()
        release = asyncio.Event()
        loops = 0

        async def loop():
            nonlocal loops
            loops += 1
            entered.set()
            await release.wait()

        jarvis._run_live_session_loop = loop
        first = asyncio.create_task(jarvis._run_live())
        await entered.wait()
        await jarvis._run_live()
        self.assertEqual(loops, 1)
        release.set()
        await first

    async def test_shutdown_flag_wins_from_every_conversation_state(self):
        for state in main.ConversationState:
            jarvis, _ = self.make_jarvis()
            jarvis._conversation_requested.set()
            jarvis._set_conversation_state(state)
            jarvis.request_shutdown()
            self.assertTrue(jarvis._shutdown_requested.is_set(), state)
            self.assertFalse(jarvis._conversation_requested.is_set(), state)

    async def test_multiple_turns_share_one_live_connection_without_reconnect(self):
        jarvis, ui = self.make_jarvis()
        jarvis.external_audio = True
        connects = []

        def turn_response(text):
            return SimpleNamespace(
                session_resumption_update=None,
                go_away=None,
                server_content=SimpleNamespace(
                    output_transcription=None,
                    input_transcription=None,
                    turn_complete=True,
                ),
                tool_call=None,
            )

        class MultiTurnSession:
            def __init__(self):
                self.receive_calls = 0

            async def receive(self):
                self.receive_calls += 1
                yield turn_response(f"turn-{self.receive_calls}")
                if self.receive_calls == 3:
                    jarvis.stop_conversation()

            async def send_realtime_input(self, **_kwargs):
                return None

            async def send_client_content(self, **_kwargs):
                return None

            async def close(self):
                return None

        session = MultiTurnSession()

        class ConnectContext:
            async def __aenter__(self):
                connects.append(True)
                return session

            async def __aexit__(self, *_args):
                return False

        client = SimpleNamespace(
            aio=SimpleNamespace(
                live=SimpleNamespace(connect=lambda **_kwargs: ConnectContext())
            )
        )
        with (
            patch.object(main.genai, "Client", return_value=client),
            patch.object(main, "pick_live_model", return_value="models/test-live"),
            patch.object(main.traceback, "print_exc") as print_traceback,
        ):
            task = asyncio.create_task(jarvis.run())
            await asyncio.sleep(0.02)
            jarvis.start_conversation()
            await self._wait_for(
                lambda: jarvis.conversation_state == main.ConversationState.STANDBY
                and session.receive_calls >= 3
            )
            jarvis.request_shutdown()
            await asyncio.wait_for(task, 1)

        self.assertEqual(len(connects), 1)
        self.assertEqual(session.receive_calls, 3)
        self.assertNotIn("RECONNECTING", ui.states)
        print_traceback.assert_not_called()

    async def test_normal_receive_turn_exhaustion_keeps_same_session_open(self):
        jarvis, ui = self.make_jarvis()
        jarvis._conversation_requested.set()
        jarvis.audio_in_queue = asyncio.Queue()
        jarvis._turn_done_event = asyncio.Event()

        class ThreeTurnSession:
            def __init__(self):
                self.receive_calls = 0
                self.close = AsyncMock()

            async def receive(self):
                self.receive_calls += 1
                yield SimpleNamespace(
                    session_resumption_update=None,
                    go_away=None,
                    server_content=SimpleNamespace(
                        output_transcription=None,
                        input_transcription=None,
                        turn_complete=True,
                    ),
                    tool_call=None,
                )
                if self.receive_calls == 3:
                    jarvis._conversation_requested.clear()

        session = ThreeTurnSession()
        jarvis.session = session
        await jarvis._receive_audio()

        self.assertEqual(session.receive_calls, 3)
        session.close.assert_not_awaited()
        self.assertNotIn("RECONNECTING", ui.states)

    def test_live_config_enables_resumption_and_context_compression(self):
        jarvis, _ = self.make_jarvis()
        config = jarvis._build_config(resumption_handle=None)
        self.assertIsNotNone(config.session_resumption)
        self.assertIsNone(config.session_resumption.handle)
        self.assertIsNotNone(config.context_window_compression)
        self.assertIsNotNone(config.context_window_compression.sliding_window)

    async def test_newest_valid_resumption_handle_is_used_on_real_reconnect(self):
        jarvis, _ = self.make_jarvis()
        jarvis.external_audio = True
        jarvis._conversation_requested.set()
        jarvis._wait_before_reconnect = AsyncMock()
        configs = []

        class FirstSession:
            async def receive(self):
                for resumable, handle in ((True, "old"), (False, "ignored"), (True, "newest")):
                    yield SimpleNamespace(
                        session_resumption_update=SimpleNamespace(
                            resumable=resumable, new_handle=handle
                        ),
                        go_away=None,
                        server_content=None,
                        tool_call=None,
                    )
                raise ConnectionResetError("transport lost")

            async def send_realtime_input(self, **_kwargs):
                return None

            async def send_client_content(self, **_kwargs):
                return None

            async def close(self):
                return None

        class SecondSession(FirstSession):
            async def receive(self):
                jarvis.stop_conversation()
                if False:
                    yield None

        class ConnectContext:
            def __init__(self, session):
                self.session = session

            async def __aenter__(self):
                return self.session

            async def __aexit__(self, *_args):
                return False

        def connect(**kwargs):
            configs.append(kwargs["config"])
            session = FirstSession() if len(configs) == 1 else SecondSession()
            return ConnectContext(session)

        client = SimpleNamespace(
            aio=SimpleNamespace(live=SimpleNamespace(connect=connect))
        )
        with (
            patch.object(main.genai, "Client", return_value=client),
            patch.object(main, "pick_live_model", return_value="models/test-live"),
        ):
            await jarvis._run_live()

        self.assertGreaterEqual(len(configs), 2)
        self.assertIsNone(configs[0].session_resumption.handle)
        self.assertEqual(configs[1].session_resumption.handle, "newest")

    async def test_every_resumable_nonempty_handle_is_captured_without_logging_value(self):
        jarvis, _ = self.make_jarvis()
        jarvis._conversation_requested.set()
        jarvis.audio_in_queue = asyncio.Queue()
        jarvis._turn_done_event = asyncio.Event()

        class HandleSession:
            async def receive(self):
                yield SimpleNamespace(
                    session_resumption_update=SimpleNamespace(
                        resumable=True, new_handle="latest-secret-handle"
                    ),
                    go_away=None,
                    server_content=None,
                    tool_call=None,
                )
                jarvis._conversation_requested.clear()

        jarvis.session = HandleSession()
        with patch("builtins.print") as print_mock:
            await jarvis._receive_audio()

        self.assertEqual(jarvis._session_resumption_handle, "latest-secret-handle")
        printed = " ".join(str(call) for call in print_mock.call_args_list)
        self.assertNotIn("latest-secret-handle", printed)

    async def test_stop_preserves_handle_and_ignores_a_late_resumption_update(self):
        jarvis, _ = self.make_jarvis()
        jarvis._loop = asyncio.get_running_loop()
        jarvis._conversation_requested.set()
        jarvis._session_resumption_handle = "old-handle"
        jarvis.audio_in_queue = asyncio.Queue()
        jarvis._turn_done_event = asyncio.Event()

        class LateUpdateSession:
            close = AsyncMock()

            async def receive(self):
                jarvis.stop_conversation()
                yield SimpleNamespace(
                    session_resumption_update=SimpleNamespace(
                        resumable=True, new_handle="must-not-return"
                    ),
                    go_away=None,
                    server_content=None,
                    tool_call=None,
                )

        jarvis.session = LateUpdateSession()
        await jarvis._receive_audio()

        self.assertEqual(jarvis._session_resumption_handle, "old-handle")

    async def test_f8_pause_preserves_all_local_conversation_continuity(self):
        jarvis, _ = self.make_jarvis()
        jarvis._conversation_requested.set()
        jarvis._set_conversation_state(main.ConversationState.LISTENING)
        jarvis._session_resumption_handle = "resume-me"
        jarvis._remember_conversation_text("user", "mi proyecto se llama Helios")
        jarvis._remember_conversation_text("assistant", "Lo recordaré en esta conversación")
        jarvis._local_session_memory["notes"]["helios"] = {"value": "activo"}
        identity = jarvis._conversation_id
        continuity = list(jarvis._conversation_continuity)
        summary = jarvis._rolling_conversation_summary
        local_memory = dict(jarvis._local_session_memory["notes"])

        self.assertTrue(jarvis.stop_conversation())

        self.assertEqual(jarvis._conversation_id, identity)
        self.assertEqual(jarvis._session_resumption_handle, "resume-me")
        self.assertEqual(jarvis._conversation_continuity, continuity)
        self.assertEqual(jarvis._rolling_conversation_summary, summary)
        self.assertEqual(jarvis._local_session_memory["notes"], local_memory)

    async def test_expired_handle_falls_back_to_local_continuity(self):
        jarvis, _ = self.make_jarvis()
        jarvis.external_audio = True
        jarvis._conversation_requested.set()
        jarvis._logical_conversation_started = True
        jarvis._session_resumption_handle = "expired-secret"
        jarvis._remember_conversation_text("user", "seguimos con Helios")
        jarvis._wait_before_reconnect = AsyncMock()
        configs = []

        class RejectedContext:
            async def __aenter__(self):
                raise RuntimeError("session resumption handle expired")

            async def __aexit__(self, *_args):
                return False

        class ResumedSession:
            async def receive(self):
                jarvis.stop_conversation()
                if False:
                    yield None

            async def send_realtime_input(self, **_kwargs):
                return None

            async def send_client_content(self, **_kwargs):
                return None

            async def close(self):
                return None

        class AcceptedContext:
            async def __aenter__(self):
                return ResumedSession()

            async def __aexit__(self, *_args):
                return False

        def connect(**kwargs):
            configs.append(kwargs["config"])
            return RejectedContext() if len(configs) == 1 else AcceptedContext()

        client = SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=connect)))
        with (
            patch.object(main.genai, "Client", return_value=client),
            patch.object(main, "pick_live_model", return_value="models/test-live"),
        ):
            await jarvis._run_live()

        self.assertEqual(len(configs), 2)
        self.assertEqual(configs[0].session_resumption.handle, "expired-secret")
        self.assertIsNone(configs[1].session_resumption.handle)
        self.assertIn("[DURABLE JARVIS CONVERSATION CONTINUITY]", configs[1].system_instruction)
        self.assertIn("seguimos con Helios", configs[1].system_instruction)

    async def test_pause_resume_does_not_repeat_the_startup_greeting(self):
        jarvis, _ = self.make_jarvis()
        jarvis.external_audio = True
        jarvis._announce_startup = AsyncMock()
        connects = 0

        class PauseSession:
            async def receive(self):
                jarvis.stop_conversation()
                if False:
                    yield None

            async def send_realtime_input(self, **_kwargs):
                return None

            async def close(self):
                return None

        class ConnectContext:
            async def __aenter__(self):
                nonlocal connects
                connects += 1
                return PauseSession()

            async def __aexit__(self, *_args):
                return False

        client = SimpleNamespace(
            aio=SimpleNamespace(live=SimpleNamespace(connect=lambda **_kwargs: ConnectContext()))
        )
        with (
            patch.object(main.genai, "Client", return_value=client),
            patch.object(main, "pick_live_model", return_value="models/test-live"),
        ):
            self.assertTrue(jarvis.start_conversation())
            await jarvis._run_live()
            jarvis._set_conversation_state(main.ConversationState.STANDBY)
            self.assertTrue(jarvis.start_conversation())
            await jarvis._run_live()

        self.assertEqual(connects, 2)
        jarvis._announce_startup.assert_awaited_once()

    def test_local_continuity_only_clears_through_explicit_new_conversation(self):
        jarvis, _ = self.make_jarvis()
        jarvis._session_resumption_handle = "resume-me"
        jarvis._logical_conversation_started = True
        jarvis._remember_conversation_text("user", "contexto importante")
        jarvis._rolling_conversation_summary = "resumen importante"
        old_id = jarvis._conversation_id

        jarvis.request_shutdown()
        self.assertEqual(jarvis._conversation_id, old_id)
        self.assertTrue(jarvis._conversation_continuity)
        self.assertTrue(jarvis._rolling_conversation_summary)
        self.assertEqual(jarvis._session_resumption_handle, "resume-me")

        self.assertTrue(jarvis.new_conversation())
        self.assertNotEqual(jarvis._conversation_id, old_id)
        self.assertEqual(jarvis._conversation_continuity, [])
        self.assertEqual(jarvis._rolling_conversation_summary, "")
        self.assertIsNone(jarvis._session_resumption_handle)

    async def test_desktop_entrypoint_starts_in_standby_without_live_connect(self):
        observations = {}
        captured_targets = []
        real_thread = threading.Thread
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        store_path = main.Path(temp_dir.name) / "conversation_state.json"

        class Root:
            def mainloop(self):
                return None

        class DesktopUI(FakeUI):
            def __init__(self, _face):
                super().__init__()
                self.root = Root()
                self.on_quit_requested = None
                self.on_voice_change = None
                self.on_tts_provider_change = None

            def wait_for_api_key(self):
                return None

        class CapturingThread:
            def __init__(self, target, daemon=True):
                self.target = target

            def start(self):
                captured_targets.append(self.target)

        async def inspect_startup(runtime):
            observations["requested"] = runtime._conversation_requested.is_set()
            observations["state"] = runtime.conversation_state
            runtime.request_shutdown()

        with (
            patch.dict(main.os.environ, {"JARVIS_CLI": "1"}, clear=False),
            patch.object(main, "wait_for_startup_claps", return_value=True),
            patch.object(main, "_load_voice_name", return_value="Puck"),
            patch.object(main, "default_conversation_store_path", return_value=store_path),
            patch.object(main.threading, "Thread", CapturingThread),
            patch.object(main.JarvisLive, "run", inspect_startup),
            patch.object(main.genai, "Client") as client_factory,
            patch("ui.JarvisUI", DesktopUI),
        ):
            main.main()
            runner_targets = [
                target for target in captured_targets
                if getattr(target, "__name__", "") == "runner"
            ]
            self.assertEqual(len(runner_targets), 1)
            worker = real_thread(target=runner_targets[0], daemon=True)
            worker.start()
            for _ in range(100):
                if not worker.is_alive():
                    break
                await asyncio.sleep(0.01)
            self.assertFalse(worker.is_alive())
            worker.join(timeout=0.1)

        self.assertFalse(observations["requested"])
        self.assertEqual(observations["state"], main.ConversationState.STANDBY)
        client_factory.assert_not_called()

    async def test_goaway_is_a_recoverable_transport_event(self):
        jarvis, _ = self.make_jarvis()
        jarvis._conversation_requested.set()
        jarvis.audio_in_queue = asyncio.Queue()
        jarvis._turn_done_event = asyncio.Event()

        class GoAwaySession:
            async def receive(self):
                yield SimpleNamespace(
                    session_resumption_update=SimpleNamespace(
                        resumable=True, new_handle="goaway-handle"
                    ),
                    go_away=SimpleNamespace(time_left="1s"),
                    server_content=None,
                    tool_call=None,
                )

        jarvis.session = GoAwaySession()
        with self.assertRaises(main.RecoverableLiveDisconnect):
            await jarvis._receive_audio()
        self.assertEqual(jarvis._session_resumption_handle, "goaway-handle")

    async def _wait_for(self, predicate, timeout=1.0):
        async def wait():
            while not predicate():
                await asyncio.sleep(0.01)

        await asyncio.wait_for(wait(), timeout)


if __name__ == "__main__":
    unittest.main()
