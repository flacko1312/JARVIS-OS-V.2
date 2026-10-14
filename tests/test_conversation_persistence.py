import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import main
from memory.conversation_store import (
    MAX_RECENT_ENTRIES,
    MAX_SUMMARY_CHARS,
    MAX_TOOL_RESULTS,
    ConversationStore,
)


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

    def clear_subtitle(self):
        return None

    def show_subtitle(self, _text):
        return None


class ConversationPersistenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store_path = Path(self.temp.name) / "conversation_state.json"

    def tearDown(self):
        self.temp.cleanup()

    def make_jarvis(self):
        return main.JarvisLive(
            FakeUI(),
            api_key="test",
            external_audio=True,
            conversation_store_path=self.store_path,
        )

    async def test_completed_turn_is_persisted_and_restored_after_process_restart(self):
        jarvis = self.make_jarvis()
        original_id = jarvis._conversation_id
        jarvis._conversation_requested.set()
        jarvis.audio_in_queue = asyncio.Queue()
        jarvis._turn_done_event = asyncio.Event()

        class OneTurnSession:
            async def receive(self):
                yield SimpleNamespace(
                    session_resumption_update=None,
                    go_away=None,
                    server_content=SimpleNamespace(
                        input_transcription=SimpleNamespace(
                            text="Mi número de prueba es 88 y hablamos de JARVIS."
                        ),
                        output_transcription=SimpleNamespace(
                            text="Entendido, recordaré el número 88 y el proyecto JARVIS."
                        ),
                        turn_complete=True,
                    ),
                    tool_call=None,
                )
                jarvis._conversation_requested.clear()

        jarvis.session = OneTurnSession()
        await jarvis._receive_audio()

        restarted = self.make_jarvis()
        self.assertEqual(restarted.conversation_state, main.ConversationState.STANDBY)
        self.assertEqual(restarted._conversation_id, original_id)
        prompt = restarted._local_continuity_prompt()
        self.assertIn("88", prompt)
        self.assertIn("JARVIS", prompt)
        self.assertIsNone(restarted._session_resumption_handle)
        self.assertTrue(restarted._resume_from_local_continuity)

    async def test_restored_current_conversation_blocks_memory_tool_fallbacks(self):
        first = self.make_jarvis()
        first._remember_conversation_text(
            "user", "Mi código es 6427 y la palabra es NEBULA.", turn_id="fact-turn"
        )
        first._remember_conversation_text(
            "assistant", "Entendido: 6427 y NEBULA.", turn_id="fact-turn"
        )

        restarted = self.make_jarvis()
        self.assertIn("6427", restarted._local_continuity_prompt())
        self.assertIn("NEBULA", restarted._local_continuity_prompt())
        with patch.object(restarted, "_execute_tool", new_callable=AsyncMock) as execute:
            for turn_number, text in enumerate((
                "¿Cuál era mi código y palabra?",
                "Multiplica el código por dos.",
            ), start=1):
                restarted._begin_schedule_turn(text, "voice")
                for index, tool in enumerate((
                    "local_memory_search", "lilith_memory_search",
                )):
                    call = SimpleNamespace(
                        id=f"restored-{turn_number}-{index}",
                        name=tool,
                        args={"query": text},
                    )
                    response = await restarted._execute_tool_guarded(call)
                    self.assertIn("suppressed", response.response["result"].lower())
            execute.assert_not_awaited()

    async def test_live_transcriptions_write_through_before_turn_complete(self):
        jarvis = self.make_jarvis()
        identity = jarvis._conversation_id
        jarvis._conversation_requested.set()
        jarvis.audio_in_queue = asyncio.Queue()
        jarvis._turn_done_event = asyncio.Event()

        class InterruptedAfterTranscriptionSession:
            async def receive(self):
                yield SimpleNamespace(
                    session_resumption_update=None,
                    go_away=None,
                    server_content=SimpleNamespace(
                        input_transcription=SimpleNamespace(
                            text="Mi número es", finished=False
                        ),
                        output_transcription=None,
                        turn_complete=False,
                    ),
                    tool_call=None,
                )
                yield SimpleNamespace(
                    session_resumption_update=None,
                    go_away=None,
                    server_content=SimpleNamespace(
                        input_transcription=SimpleNamespace(
                            text="Mi número es 88 y estamos trabajando en JARVIS.",
                            finished=True,
                        ),
                        output_transcription=SimpleNamespace(
                            text="Entendido: 88 y JARVIS.", finished=True
                        ),
                        turn_complete=False,
                    ),
                    tool_call=None,
                )
                jarvis._conversation_requested.clear()

        jarvis.session = InterruptedAfterTranscriptionSession()
        await jarvis._receive_audio()

        restarted = self.make_jarvis()
        self.assertEqual(restarted._conversation_id, identity)
        self.assertEqual(len(restarted._conversation_continuity), 2)
        self.assertEqual(
            [item["role"] for item in restarted._conversation_continuity],
            ["user", "assistant"],
        )
        prompt = restarted._local_continuity_prompt()
        self.assertIn("88", prompt)
        self.assertIn("JARVIS", prompt)
        self.assertNotIn("Mi número es Mi número es", prompt)

    def test_full_retention_window_rotates_while_new_turns_persist(self):
        jarvis = self.make_jarvis()
        for index in range(MAX_RECENT_ENTRIES):
            role = "user" if index % 2 == 0 else "assistant"
            jarvis._remember_conversation_text(role, f"turno histórico {index}")

        jarvis._remember_conversation_text(
            "user", "Mi número es 88.", turn_id="new-live-turn"
        )
        jarvis._remember_conversation_text(
            "assistant", "El número es 88.", turn_id="new-live-turn"
        )

        restarted = self.make_jarvis()
        self.assertEqual(len(restarted._conversation_continuity), MAX_RECENT_ENTRIES)
        self.assertEqual(
            [item["role"] for item in restarted._conversation_continuity[-2:]],
            ["user", "assistant"],
        )
        self.assertTrue(
            all("88" in item["text"] for item in restarted._conversation_continuity[-2:])
        )
        self.assertIn("turno histórico 0", restarted._rolling_conversation_summary)

    async def test_f8_and_clean_shutdown_preserve_persisted_state(self):
        jarvis = self.make_jarvis()
        jarvis._remember_conversation_text("user", "seguimos con el número 88")
        identity = jarvis._conversation_id
        jarvis._conversation_requested.set()
        jarvis._set_conversation_state(main.ConversationState.LISTENING)

        self.assertTrue(jarvis.stop_conversation())
        jarvis.request_shutdown()

        restarted = self.make_jarvis()
        self.assertEqual(restarted._conversation_id, identity)
        self.assertIn("88", restarted._local_continuity_prompt())

    async def test_restored_startup_stays_standby_without_live_or_microphone(self):
        first = self.make_jarvis()
        first._remember_conversation_text("user", "continuidad anterior")
        identity = first._conversation_id

        restarted = self.make_jarvis()
        restarted._run_live = AsyncMock()
        restarted._listen_audio = AsyncMock()
        task = asyncio.create_task(restarted.run())
        await asyncio.sleep(0.08)

        self.assertEqual(restarted._conversation_id, identity)
        self.assertEqual(restarted.conversation_state, main.ConversationState.STANDBY)
        restarted._run_live.assert_not_awaited()
        restarted._listen_audio.assert_not_awaited()
        restarted.request_shutdown()
        await asyncio.wait_for(task, timeout=1)

    async def test_goaway_and_nonresumable_update_preserve_good_handle_and_continuity(self):
        jarvis = self.make_jarvis()
        jarvis._remember_conversation_text("user", "contexto durable")
        jarvis._conversation_requested.set()
        jarvis.audio_in_queue = asyncio.Queue()
        jarvis._turn_done_event = asyncio.Event()
        jarvis._session_resumption_handle = "known-good"

        class GoAwaySession:
            async def receive(self):
                yield SimpleNamespace(
                    session_resumption_update=SimpleNamespace(
                        resumable=False, new_handle="must-be-ignored"
                    ),
                    go_away=SimpleNamespace(time_left="1s"),
                    server_content=None,
                    tool_call=None,
                )

        jarvis.session = GoAwaySession()
        with self.assertRaises(main.RecoverableLiveDisconnect):
            await jarvis._receive_audio()

        self.assertEqual(jarvis._session_resumption_handle, "known-good")
        restarted = self.make_jarvis()
        self.assertIn("contexto durable", restarted._local_continuity_prompt())

    async def test_repeated_goaway_falls_back_once_to_clean_local_continuity(self):
        jarvis = self.make_jarvis()
        jarvis.external_audio = True
        jarvis._remember_conversation_text("user", "número 88 proyecto JARVIS")
        jarvis._logical_conversation_started = True
        jarvis._conversation_requested.set()
        jarvis._wait_before_reconnect = AsyncMock()
        jarvis._announce_startup = AsyncMock()
        real_restore = jarvis._restore_durable_continuity
        jarvis._restore_durable_continuity = AsyncMock(wraps=real_restore)
        configs = []

        class GoAwaySession:
            def __init__(self, resumable, handle):
                self.resumable = resumable
                self.handle = handle

            async def receive(self):
                yield SimpleNamespace(
                    session_resumption_update=SimpleNamespace(
                        resumable=self.resumable, new_handle=self.handle
                    ),
                    go_away=SimpleNamespace(time_left="1s"),
                    server_content=None,
                    tool_call=None,
                )

            async def send_realtime_input(self, **_kwargs):
                return None

            async def send_client_content(self, **_kwargs):
                return None

            async def close(self):
                return None

        class FinalSession(GoAwaySession):
            async def receive(self):
                jarvis.stop_conversation()
                if False:
                    yield None

        class Context:
            def __init__(self, session):
                self.session = session

            async def __aenter__(self):
                return self.session

            async def __aexit__(self, *_args):
                return False

        def connect(**kwargs):
            configs.append(kwargs["config"])
            if len(configs) == 1:
                return Context(GoAwaySession(True, "known-good"))
            if len(configs) == 2:
                return Context(GoAwaySession(False, "must-be-ignored"))
            return Context(FinalSession(False, None))

        client = SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=connect)))
        with (
            patch.object(main.genai, "Client", return_value=client),
            patch.object(main, "pick_live_model", return_value="models/test-live"),
        ):
            await jarvis._run_live()

        self.assertEqual(len(configs), 3)
        self.assertIsNone(configs[0].session_resumption.handle)
        self.assertEqual(configs[1].session_resumption.handle, "known-good")
        self.assertIsNone(configs[2].session_resumption.handle)
        self.assertIn("número 88 proyecto JARVIS", configs[2].system_instruction)
        self.assertEqual(jarvis._restore_durable_continuity.await_count, 2)
        jarvis._announce_startup.assert_not_awaited()

    async def test_process_restart_prefills_live_history_without_memory_tools(self):
        process1 = self.make_jarvis()
        identity = process1._conversation_id
        process1._remember_conversation_text(
            "user", "Mi número es 88 y estamos trabajando en JARVIS."
        )
        process1._remember_conversation_text(
            "assistant", "Entendido: 88 y proyecto JARVIS."
        )
        process1._remember_conversation_tool_result(
            "project_status", {"current_topic": "continuidad durable de JARVIS"}
        )

        with patch.object(main.genai, "Client") as client_factory:
            process2 = self.make_jarvis()
        client_factory.assert_not_called()
        self.assertEqual(process2._conversation_id, identity)
        self.assertEqual(process2.conversation_state, main.ConversationState.STANDBY)
        self.assertEqual(len(process2._conversation_continuity), 2)

        class CapturingSession:
            def __init__(self):
                self.calls = []

            async def send_client_content(self, **kwargs):
                self.calls.append(kwargs)

        session2 = CapturingSession()
        process2._execute_tool = AsyncMock()
        await process2._restore_durable_continuity(session2)
        history2 = session2.calls[0]["turns"]
        history2_text = " ".join(part.text for turn in history2 for part in turn.parts)
        self.assertEqual([turn.role for turn in history2], ["user", "model"])
        self.assertIn("88", history2_text)
        self.assertIn("JARVIS", history2_text)
        self.assertTrue(session2.calls[0]["turn_complete"])
        config2 = process2._build_config(
            local_continuity=process2._local_continuity_prompt(),
            initial_history=True,
        )
        self.assertTrue(config2.history_config.initial_history_in_client_content)
        self.assertIn("project_status", config2.system_instruction)
        self.assertIn("continuidad durable", config2.system_instruction)

        process2.session = session2
        await process2.send_text(
            "¿Qué número te dije y en qué proyecto estamos trabajando?"
        )
        process2._execute_tool.assert_not_awaited()
        process2._remember_conversation_text(
            "assistant", "Me dijiste 88 y estamos trabajando en JARVIS."
        )

        process3 = self.make_jarvis()
        self.assertEqual(process3._conversation_id, identity)
        session3 = CapturingSession()
        process3._execute_tool = AsyncMock()
        await process3._restore_durable_continuity(session3)
        history3_text = " ".join(
            part.text for turn in session3.calls[0]["turns"] for part in turn.parts
        )
        self.assertIn("88", history3_text)
        process3.session = session3
        await process3.send_text("¿Cuánto es aquel número multiplicado por dos?")
        process3._execute_tool.assert_not_awaited()
        self.assertIn("multiplicado por dos", session3.calls[-1]["turns"]["parts"][0]["text"])

    async def test_restore_finishes_before_listening_receive_and_microphone(self):
        process1 = self.make_jarvis()
        process1._remember_conversation_text("user", "contexto antes del reinicio")
        process2 = self.make_jarvis()
        process2.external_audio = False
        process2._conversation_requested.set()
        process2._wait_before_reconnect = AsyncMock()
        events = []
        process2.ui.set_state = lambda state: events.append(f"state:{state}")

        class Session:
            async def send_client_content(self, **kwargs):
                self.prefill = kwargs
                self.session_visible_during_restore = process2.session
                events.append("restore")

            async def close(self):
                return None

        session = Session()

        class Context:
            async def __aenter__(self):
                events.append("transport")
                return session

            async def __aexit__(self, *_args):
                return False

        async def receive():
            events.append("receive")
            process2.stop_conversation()

        async def microphone():
            events.append("microphone")

        async def no_op():
            return None

        process2._receive_audio = receive
        process2._listen_audio = microphone
        process2._send_realtime = no_op
        process2._play_audio = no_op
        client = SimpleNamespace(
            aio=SimpleNamespace(live=SimpleNamespace(connect=lambda **_kwargs: Context()))
        )
        with (
            patch.object(main.genai, "Client", return_value=client),
            patch.object(main, "pick_live_model", return_value="models/test-live"),
        ):
            await process2._run_live()

        self.assertIsNone(session.session_visible_during_restore)
        self.assertLess(events.index("transport"), events.index("restore"))
        self.assertLess(events.index("restore"), events.index("state:LISTENING"))
        self.assertLess(events.index("state:LISTENING"), events.index("receive"))
        self.assertLess(events.index("state:LISTENING"), events.index("microphone"))

    def test_history_conversion_filters_malformed_items_and_empty_parts(self):
        jarvis = self.make_jarvis()
        jarvis._conversation_continuity = [
            {"role": "user", "text": "hola"},
            {"role": "assistant", "text": "respuesta\x00 válida"},
            {"role": "system", "text": "unsupported"},
            {"role": "assistant", "text": "   "},
            {"role": "user", "text": SimpleNamespace(raw="object")},
        ]

        turns = jarvis._durable_continuity_turns()
        diagnostics = jarvis._durable_history_diagnostics()

        self.assertEqual([turn.role for turn in turns], ["user", "model"])
        self.assertTrue(all(turn.parts for turn in turns))
        self.assertTrue(all(part.text.strip() for turn in turns for part in turn.parts))
        self.assertNotIn("\x00", turns[1].parts[0].text)
        self.assertEqual(diagnostics["items"], 2)
        self.assertEqual(diagnostics["empty"], 0)

    async def test_initial_history_1007_retries_once_without_history_before_mic(self):
        jarvis = self.make_jarvis()
        jarvis.external_audio = False
        jarvis._remember_conversation_text("user", "contexto durable 88")
        identity = jarvis._conversation_id
        jarvis._logical_conversation_started = True
        jarvis._conversation_requested.set()
        configs = []
        events = []

        class RejectedWebSocket:
            close_code = 1007
            close_reason = "Request contains an invalid argument"

            async def wait_closed(self):
                return None

        class RejectedSession:
            _ws = RejectedWebSocket()

            async def send_client_content(self, **_kwargs):
                events.append("history:first")

            async def close(self):
                return None

        class AcceptedSession:
            async def close(self):
                return None

        sessions = [RejectedSession(), AcceptedSession()]

        class Context:
            def __init__(self, session):
                self.session = session

            async def __aenter__(self):
                events.append(f"connect:{len(configs)}")
                return self.session

            async def __aexit__(self, *_args):
                return False

        def connect(**kwargs):
            configs.append(kwargs["config"])
            return Context(sessions[len(configs) - 1])

        async def microphone():
            events.append(f"mic:{len(configs)}")

        async def receive():
            events.append(f"receive:{len(configs)}")
            jarvis.stop_conversation()

        async def no_op():
            return None

        jarvis._listen_audio = microphone
        jarvis._receive_audio = receive
        jarvis._send_realtime = no_op
        jarvis._play_audio = no_op
        client = SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=connect)))
        with (
            patch.object(main.genai, "Client", return_value=client),
            patch.object(main, "pick_live_model", return_value="models/future-live"),
        ):
            await jarvis._run_live()

        self.assertEqual(len(configs), 2)
        self.assertIsNotNone(configs[0].history_config)
        self.assertIsNone(configs[0].session_resumption.handle)
        self.assertIsNone(configs[1].history_config)
        self.assertEqual(events.count("history:first"), 1)
        self.assertNotIn("mic:1", events)
        self.assertIn("mic:2", events)
        restarted = self.make_jarvis()
        self.assertEqual(restarted._conversation_id, identity)
        self.assertIn("88", restarted._local_continuity_prompt())

    async def test_known_unsupported_model_uses_compact_context_without_replay(self):
        jarvis = self.make_jarvis()
        jarvis.external_audio = True
        jarvis._remember_conversation_text("user", "continuidad compacta 88")
        jarvis._logical_conversation_started = True
        jarvis._conversation_requested.set()
        configs = []

        class Session:
            send_client_content = AsyncMock()

            async def close(self):
                return None

        session = Session()

        class Context:
            async def __aenter__(self):
                return session

            async def __aexit__(self, *_args):
                return False

        def connect(**kwargs):
            configs.append(kwargs["config"])
            return Context()

        async def receive():
            jarvis.stop_conversation()

        async def no_op():
            return None

        jarvis._receive_audio = receive
        jarvis._send_realtime = no_op
        jarvis._play_audio = no_op
        client = SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=connect)))
        with (
            patch.object(main.genai, "Client", return_value=client),
            patch.object(
                main,
                "pick_live_model",
                return_value="models/gemini-2.5-flash-native-audio-preview-12-2025",
            ),
        ):
            await jarvis._run_live()

        self.assertEqual(len(configs), 1)
        self.assertIsNone(configs[0].history_config)
        self.assertIsNone(configs[0].session_resumption.handle)
        self.assertIn("continuidad compacta 88", configs[0].system_instruction)
        session.send_client_content.assert_not_awaited()

    async def test_normal_goaway_resumes_natively_with_latest_good_handle(self):
        jarvis = self.make_jarvis()
        jarvis.external_audio = True
        jarvis._remember_conversation_text("user", "contexto previo")
        jarvis._logical_conversation_started = True
        jarvis._conversation_requested.set()
        jarvis._wait_before_reconnect = AsyncMock()
        jarvis._announce_startup = AsyncMock()
        real_restore = jarvis._restore_durable_continuity
        jarvis._restore_durable_continuity = AsyncMock(wraps=real_restore)
        configs = []

        class FirstSession:
            async def receive(self):
                yield SimpleNamespace(
                    session_resumption_update=SimpleNamespace(
                        resumable=True, new_handle="latest-good"
                    ),
                    go_away=SimpleNamespace(time_left="1s"),
                    server_content=None,
                    tool_call=None,
                )

            async def send_realtime_input(self, **_kwargs):
                return None

            async def send_client_content(self, **_kwargs):
                return None

            async def close(self):
                return None

        class ResumedSession(FirstSession):
            async def receive(self):
                jarvis.stop_conversation()
                if False:
                    yield None

        class Context:
            def __init__(self, session):
                self.session = session

            async def __aenter__(self):
                return self.session

            async def __aexit__(self, *_args):
                return False

        def connect(**kwargs):
            configs.append(kwargs["config"])
            return Context(FirstSession() if len(configs) == 1 else ResumedSession())

        client = SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=connect)))
        with (
            patch.object(main.genai, "Client", return_value=client),
            patch.object(main, "pick_live_model", return_value="models/test-live"),
        ):
            await jarvis._run_live()

        self.assertEqual(len(configs), 2)
        self.assertIsNone(configs[0].session_resumption.handle)
        self.assertEqual(configs[1].session_resumption.handle, "latest-good")
        self.assertIsNone(configs[1].history_config)
        self.assertEqual(jarvis._restore_durable_continuity.await_count, 1)
        jarvis._announce_startup.assert_not_awaited()

    async def test_exhausted_reconnect_attempts_preserve_durable_continuity(self):
        jarvis = self.make_jarvis()
        jarvis._remember_conversation_text("user", "dato tras fallo de red")
        identity = jarvis._conversation_id
        jarvis._logical_conversation_started = True
        jarvis._conversation_requested.set()
        jarvis._wait_before_reconnect = AsyncMock()
        connects = 0

        class BrokenContext:
            async def __aenter__(self):
                raise main.RecoverableLiveDisconnect("transport unavailable")

            async def __aexit__(self, *_args):
                return False

        def connect(**_kwargs):
            nonlocal connects
            connects += 1
            return BrokenContext()

        client = SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=connect)))
        with (
            patch.object(main.genai, "Client", return_value=client),
            patch.object(main, "pick_live_model", return_value="models/test-live"),
        ):
            await jarvis._run_live()

        self.assertEqual(connects, 1 + main.MAX_LIVE_RECONNECT_ATTEMPTS)
        restarted = self.make_jarvis()
        self.assertEqual(restarted._conversation_id, identity)
        self.assertIn("dato tras fallo de red", restarted._local_continuity_prompt())

    async def test_restart_without_handle_builds_config_from_local_continuity(self):
        first = self.make_jarvis()
        first._remember_conversation_text("user", "El dato inmediato es 88")
        identity = first._conversation_id

        restarted = self.make_jarvis()
        self.assertEqual(restarted._conversation_id, identity)
        self.assertIsNone(restarted._session_resumption_handle)
        config = restarted._build_config(
            resumption_handle=None,
            local_continuity=restarted._local_continuity_prompt(),
        )
        self.assertIn("El dato inmediato es 88", config.system_instruction)
        self.assertNotIn("lilith_memory_search", restarted._local_continuity_prompt())

    async def test_rejected_native_handle_does_not_delete_persisted_continuity(self):
        jarvis = self.make_jarvis()
        jarvis.external_audio = True
        jarvis._remember_conversation_text("user", "persistir pese al handle")
        identity = jarvis._conversation_id
        jarvis._logical_conversation_started = True
        jarvis._session_resumption_handle = "expired-handle"
        jarvis._conversation_requested.set()
        jarvis._wait_before_reconnect = AsyncMock()
        configs = []

        class Rejected:
            async def __aenter__(self):
                raise RuntimeError("session resumption handle expired")

            async def __aexit__(self, *_args):
                return False

        class AcceptedSession:
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

        class Accepted:
            async def __aenter__(self):
                return AcceptedSession()

            async def __aexit__(self, *_args):
                return False

        def connect(**kwargs):
            configs.append(kwargs["config"])
            return Rejected() if len(configs) == 1 else Accepted()

        client = SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=connect)))
        with (
            patch.object(main.genai, "Client", return_value=client),
            patch.object(main, "pick_live_model", return_value="models/test-live"),
        ):
            await jarvis._run_live()

        self.assertEqual(len(configs), 2)
        self.assertEqual(configs[0].session_resumption.handle, "expired-handle")
        self.assertIsNone(configs[1].session_resumption.handle)
        self.assertIn("persistir pese al handle", configs[1].system_instruction)
        restarted = self.make_jarvis()
        self.assertEqual(restarted._conversation_id, identity)
        self.assertIn("persistir pese al handle", restarted._local_continuity_prompt())

    def test_explicit_new_conversation_is_the_only_clear_path(self):
        jarvis = self.make_jarvis()
        jarvis._remember_conversation_text("user", "no borrar automáticamente")
        old_id = jarvis._conversation_id

        self.assertTrue(jarvis.new_conversation())

        restarted = self.make_jarvis()
        self.assertNotEqual(restarted._conversation_id, old_id)
        self.assertEqual(restarted._conversation_continuity, [])
        self.assertEqual(restarted._rolling_conversation_summary, "")
        self.assertEqual(restarted._recent_conversation_tool_results, [])

    def test_late_old_conversation_writes_cannot_resurrect_cleared_state(self):
        jarvis = self.make_jarvis()
        jarvis._remember_conversation_text("user", "estado antiguo")
        old_id = jarvis._conversation_id
        self.assertTrue(jarvis.new_conversation())
        new_id = jarvis._conversation_id

        jarvis._remember_conversation_text(
            "assistant", "respuesta antigua tardía", expected_conversation_id=old_id
        )
        jarvis._remember_conversation_tool_result(
            "old_tool", {"result": "resultado antiguo"}, expected_conversation_id=old_id
        )

        restarted = self.make_jarvis()
        self.assertEqual(restarted._conversation_id, new_id)
        self.assertEqual(restarted._conversation_continuity, [])
        self.assertEqual(restarted._recent_conversation_tool_results, [])
        self.assertNotIn("antigu", self.store_path.read_text(encoding="utf-8"))

    def test_corrupt_store_fails_safe_without_overwriting_it_on_load(self):
        corrupt = "{not valid json"
        self.store_path.write_text(corrupt, encoding="utf-8")

        jarvis = self.make_jarvis()
        jarvis._remember_conversation_text("user", "must not replace corrupt data")
        jarvis.request_shutdown()

        self.assertEqual(jarvis.conversation_state, main.ConversationState.STANDBY)
        self.assertTrue(jarvis._conversation_id)
        self.assertEqual(self.store_path.read_text(encoding="utf-8"), corrupt)

        self.assertTrue(jarvis.new_conversation())
        persisted = ConversationStore(self.store_path).load()
        self.assertEqual(persisted["conversation_id"], jarvis._conversation_id)
        self.assertEqual(persisted["recent_turns"], [])

    def test_store_is_bounded_and_folds_older_turns_into_summary(self):
        jarvis = self.make_jarvis()
        for index in range(MAX_RECENT_ENTRIES + 10):
            jarvis._remember_conversation_text("user", f"dato semántico {index}")

        persisted = ConversationStore(self.store_path).load()
        self.assertEqual(len(persisted["recent_turns"]), MAX_RECENT_ENTRIES)
        self.assertLessEqual(len(persisted["summary"]), MAX_SUMMARY_CHARS)
        self.assertIn("dato semántico 0", persisted["summary"])
        self.assertIn(f"dato semántico {MAX_RECENT_ENTRIES + 9}", persisted["recent_turns"][-1]["text"])
        restarted = self.make_jarvis()
        self.assertEqual(restarted._rolling_conversation_summary, persisted["summary"])

    def test_tool_results_are_bounded_persisted_and_restored(self):
        jarvis = self.make_jarvis()
        for index in range(MAX_TOOL_RESULTS + 5):
            jarvis._remember_conversation_tool_result(
                "screen_process", {"result": f"El proyecto visible es JARVIS {index}"}
            )
        restarted = self.make_jarvis()
        self.assertEqual(len(restarted._recent_conversation_tool_results), MAX_TOOL_RESULTS)
        self.assertIn("screen_process", restarted._local_continuity_prompt())
        self.assertIn("JARVIS", restarted._local_continuity_prompt())

    def test_sensitive_values_are_redacted_before_persistence(self):
        jarvis = self.make_jarvis()
        jarvis._remember_conversation_text(
            "user", "api_key=super-secret-value password: hunter2 dato 88"
        )
        jarvis._remember_conversation_tool_result(
            "test_tool", {"authorization": "Bearer abc.def.ghi", "result": "ok"}
        )

        raw = self.store_path.read_text(encoding="utf-8")
        self.assertNotIn("super-secret-value", raw)
        self.assertNotIn("hunter2", raw)
        self.assertNotIn("abc.def.ghi", raw)
        self.assertIn("[REDACTED]", raw)

    def test_atomic_save_leaves_valid_json_and_no_temporary_file(self):
        jarvis = self.make_jarvis()
        jarvis._remember_conversation_text("user", "estado atómico")
        json.loads(self.store_path.read_text(encoding="utf-8"))
        self.assertEqual(list(self.store_path.parent.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
