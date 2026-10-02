"""JL-W003: typed-input wiring between JarvisLive and LILITH (runtime + router).

Offline tests: no network, no Gemini, no real LILITH. Uses unittest/asyncio only
(no extra test dependencies). Verifies that:
  * LILITH unconfigured -> JARVIS behaves exactly as before;
  * text executed by LILITH is NOT also sent to Gemini;
  * everything else (offline, clarification, not handled, errors, internal
    prompts, self-quit) continues to Gemini unchanged;
  * the runtime lives inside run() and is always stopped;
  * the hosted/cloud_safe mode never starts the bridge.
"""
import asyncio
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import main
from core.lilith_gateway import LilithBridge, TypedRouteOutcome


# ── fakes ────────────────────────────────────────────────────────────────

class StubClient:
    def __init__(self):
        self.on_text_command = None
        self.muted = False
        self.current_file = None
        self._voice_combo = None
        self.logs = []

    def write_log(self, text):
        self.logs.append(text)

    def set_state(self, state):
        pass


class FakeSession:
    def __init__(self):
        self.sent = []

    async def send_client_content(self, turns, turn_complete):
        self.sent.append(turns["parts"][0]["text"])


class FakeBridge:
    """Stands in for LilithBridge inside JarvisLive."""

    def __init__(self, outcome=None, raises=None):
        self.outcome = outcome or TypedRouteOutcome(handled=False)
        self.raises = raises
        self.calls = []
        self.started = False
        self.stopped = False
        self.lilith_available = True

    async def route_typed(self, text):
        self.calls.append(text)
        if self.raises:
            raise self.raises
        return self.outcome

    async def start(self):
        self.started = True
        return True

    async def stop(self):
        self.stopped = True


class FakeRuntime:
    """Minimal JarvisRuntime stand-in for the LilithBridge unit tests."""

    def __init__(self, result=None, exc=None, delay=0.0):
        self._result = result
        self._exc = exc
        self._delay = delay
        self.lilith_available = True
        self.started = self.stopped = False
        self.inputs = []

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True

    async def process_input(self, text):
        self.inputs.append(text)
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._exc:
            raise self._exc
        return self._result


def _started_bridge(runtime, **kw):
    bridge = LilithBridge(runtime, **kw)
    bridge._started = True
    return bridge


def _live(bridge=None, cloud_safe=False):
    client = StubClient()
    jarvis = main.JarvisLive(client, cloud_safe=cloud_safe)
    jarvis.session = FakeSession()
    jarvis._lilith = bridge
    return jarvis, client


# ── LilithBridge ─────────────────────────────────────────────────────────

class BridgeConstructionTests(unittest.TestCase):
    def test_from_env_is_none_when_not_configured(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LILITH_API_URL", None)
            os.environ.pop("LILITH_API_KEY", None)
            self.assertIsNone(LilithBridge.from_env())

    def test_from_env_is_none_when_only_url_is_set(self):
        with patch.dict(os.environ, {"LILITH_API_URL": "http://x:8000"}):
            os.environ.pop("LILITH_API_KEY", None)
            self.assertIsNone(LilithBridge.from_env())

    def test_from_env_survives_missing_runtime_dependency(self):
        env = {"LILITH_API_URL": "http://x:8000", "LILITH_API_KEY": "k"}
        with patch.dict(os.environ, env), patch.dict(sys.modules, {"runtime": None}):
            self.assertIsNone(LilithBridge.from_env())

    def test_from_env_builds_a_bridge_when_configured(self):
        env = {"LILITH_API_URL": "http://127.0.0.1:9", "LILITH_API_KEY": "test-key"}
        with patch.dict(os.environ, env):
            bridge = LilithBridge.from_env()
        self.assertIsInstance(bridge, LilithBridge)
        self.assertFalse(bridge.is_running)


class BridgeLifecycleTests(unittest.TestCase):
    def test_start_stop(self):
        rt = FakeRuntime()
        bridge = LilithBridge(rt)
        self.assertTrue(asyncio.run(bridge.start()))
        self.assertTrue(rt.started and bridge.is_running)
        asyncio.run(bridge.stop())
        self.assertTrue(rt.stopped and not bridge.is_running)

    def test_start_failure_is_swallowed(self):
        class Boom(FakeRuntime):
            async def start(self):
                raise RuntimeError("boom")
        bridge = LilithBridge(Boom())
        self.assertFalse(asyncio.run(bridge.start()))
        self.assertFalse(bridge.is_running)


class BridgeRoutingTests(unittest.TestCase):
    def _route(self, runtime, text="recuerda que mi test es azul", **kw):
        return asyncio.run(_started_bridge(runtime, **kw).route_typed(text))

    def test_not_started_passes_through_without_calling_runtime(self):
        rt = FakeRuntime(result={"handled": True})
        out = asyncio.run(LilithBridge(rt).route_typed("hola"))
        self.assertFalse(out.handled)
        self.assertEqual(rt.inputs, [])

    def test_internal_prompts_are_never_offered_to_lilith(self):
        rt = FakeRuntime(result={"handled": True, "data": {}})
        for text in ("[UI EVENT] apaga la luz", "[VERIFIED LOCAL SELF-SHUTDOWN] x", ""):
            self.assertFalse(self._route(rt, text).handled)
        self.assertEqual(rt.inputs, [])

    def test_not_handled_passes_through(self):
        out = self._route(FakeRuntime(result={"handled": False, "domain": "conversation"}))
        self.assertFalse(out.handled)
        self.assertEqual(out.reason, "not_handled")

    def test_offline_passes_through_with_notice(self):
        out = self._route(FakeRuntime(result={
            "handled": True, "domain": "memory", "data": {"offline": True},
            "message": "LILITH no disponible"}))
        self.assertFalse(out.handled)
        self.assertEqual(out.reason, "lilith_offline")
        self.assertTrue(out.notice)

    def test_needs_clarification_passes_through(self):
        out = self._route(FakeRuntime(result={
            "handled": True, "domain": "home",
            "data": {"needs_clarification": True}, "message": "¿Qué dispositivo?"}))
        self.assertFalse(out.handled)
        self.assertEqual(out.reason, "needs_clarification")

    def test_runtime_exception_passes_through(self):
        out = self._route(FakeRuntime(exc=RuntimeError("x")))
        self.assertFalse(out.handled)
        self.assertEqual(out.reason, "error")

    def test_timeout_passes_through(self):
        out = self._route(FakeRuntime(result={"handled": True, "data": {}}, delay=1.0),
                          route_timeout=0.05)
        self.assertFalse(out.handled)
        self.assertEqual(out.reason, "error")

    def test_handled_store_message(self):
        out = self._route(FakeRuntime(result={"handled": True, "domain": "memory", "data": {"key": "k"}}))
        self.assertTrue(out.handled)
        self.assertIn("Guardado", out.message)

    def test_handled_search_message_lists_results(self):
        data = [{"value": "mi test es azul"}, {"content": "otro"}]
        out = self._route(FakeRuntime(result={"handled": True, "domain": "memory", "data": data}))
        self.assertTrue(out.handled)
        self.assertIn("mi test es azul", out.message)
        self.assertIn("otro", out.message)

    def test_handled_search_uses_text_field_of_real_results(self):
        """Real LILITH items are {key, score, source, text, ts}; show the text, not the key."""
        data = [{"key": "jarvis:el_codigo", "score": 0.9, "source": "jarvis",
                 "text": "el codigo de prueba es naranja", "ts": "2026-10-02"}]
        out = self._route(FakeRuntime(result={"handled": True, "domain": "memory", "data": data}))
        self.assertIn("el codigo de prueba es naranja", out.message)
        self.assertNotIn("jarvis:el_codigo", out.message)

    def test_handled_empty_search_message(self):
        out = self._route(FakeRuntime(result={"handled": True, "domain": "memory", "data": []}))
        self.assertTrue(out.handled)
        self.assertIn("No encuentro", out.message)

    def test_handled_home_action_message(self):
        data = {"entity_id": "light.x", "action": "turn_on"}
        out = self._route(FakeRuntime(result={"handled": True, "domain": "home", "data": data}))
        self.assertIn("light.x", out.message)

    def test_explicit_message_is_preferred(self):
        out = self._route(FakeRuntime(result={"handled": True, "data": {}, "message": "texto"}))
        self.assertEqual(out.message, "texto")


# ── Real router through the real runtime (fake LILITH client) ─────────────

class FakeLilithClient:
    def __init__(self):
        self.stored = []
        self.searched = []

    async def store_memory(self, key, value, **kw):
        self.stored.append((key, value))
        return {"key": f"jarvis:{key}"}

    async def search_memory(self, query, **kw):
        self.searched.append(query)
        return [{"value": "mi test es azul"}]

    async def home_action(self, *a, **kw):  # must never be reached without an entity
        raise AssertionError("home_action must not run without entity resolution")


def _real_runtime_bridge(available=True):
    from runtime import JarvisRuntime
    from lilith_client.config import LilithConfig
    rt = JarvisRuntime(LilithConfig(base_url="http://127.0.0.1:9", api_key="test-key"))
    fake = FakeLilithClient()
    rt.router._client = fake
    rt.router._monitor = SimpleNamespace(status=SimpleNamespace(is_available=available))
    rt._monitor = rt.router._monitor
    return _started_bridge(rt), fake


class RealRouterThroughBridgeTests(unittest.TestCase):
    def test_remember_is_stored_in_lilith(self):
        bridge, fake = _real_runtime_bridge()
        out = asyncio.run(bridge.route_typed("recuerda que mi test es azul"))
        self.assertTrue(out.handled)
        self.assertEqual(fake.stored[0][1], "mi test es azul")

    def test_memory_question_is_answered_from_lilith(self):
        bridge, fake = _real_runtime_bridge()
        out = asyncio.run(bridge.route_typed("qué sabes de mi test"))
        self.assertTrue(out.handled)
        self.assertIn("mi test es azul", out.message)

    def test_home_like_texts_still_reach_gemini(self):
        """HOME words ('luz', 'bombilla', 'puerta', ...) are classified as HOME but
        entity resolution is JL-H005, so LILITH does nothing: these must keep going
        to Gemini instead of being swallowed by a clarification question."""
        bridge, fake = _real_runtime_bridge()
        for text in ("enciende la luz del salón", "baja la luz de la pantalla",
                     "cierra la puerta del garaje"):
            out = asyncio.run(bridge.route_typed(text))
            self.assertFalse(out.handled, text)
            self.assertEqual(out.reason, "needs_clarification", text)
        # Not classified as HOME at all ('apag'/'encien' need a standalone word match)
        for text in ("apaga el wifi", "apaga el ordenador"):
            self.assertFalse(asyncio.run(bridge.route_typed(text)).handled, text)

    def test_conversation_and_other_domains_reach_gemini(self):
        bridge, fake = _real_runtime_bridge()
        for text in ("hola, ¿cómo estás?", "abre chrome", "busca en google el tiempo", "cuéntame un chiste"):
            self.assertFalse(asyncio.run(bridge.route_typed(text)).handled, text)
        self.assertEqual((fake.stored, fake.searched), ([], []))

    def test_lilith_offline_passes_through_with_notice(self):
        bridge, fake = _real_runtime_bridge(available=False)
        out = asyncio.run(bridge.route_typed("recuerda que mi test es azul"))
        self.assertFalse(out.handled)
        self.assertEqual(out.reason, "lilith_offline")
        self.assertEqual(fake.stored, [])


# ── JarvisLive.send_text hook ────────────────────────────────────────────

class SendTextHookTests(unittest.TestCase):
    def test_without_bridge_behaviour_is_unchanged(self):
        jarvis, client = _live(bridge=None)
        self.assertTrue(asyncio.run(jarvis.send_text("hola")))
        self.assertEqual(jarvis.session.sent, ["hola"])
        self.assertEqual(client.logs, [])

    def test_passthrough_sends_the_original_text_to_gemini_once(self):
        bridge = FakeBridge(TypedRouteOutcome(handled=False, reason="not_handled"))
        jarvis, client = _live(bridge)
        asyncio.run(jarvis.send_text("hola, ¿qué tal?"))
        self.assertEqual(bridge.calls, ["hola, ¿qué tal?"])
        self.assertEqual(jarvis.session.sent, ["hola, ¿qué tal?"])

    def test_handled_by_lilith_is_not_sent_to_gemini(self):
        bridge = FakeBridge(TypedRouteOutcome(handled=True, message="Guardado.", reason="handled"))
        jarvis, client = _live(bridge)
        self.assertTrue(asyncio.run(jarvis.send_text("recuerda que mi test es azul")))
        self.assertEqual(jarvis.session.sent, [])
        self.assertIn("LILITH: Guardado.", client.logs)

    def test_offline_notice_is_logged_and_gemini_still_receives_text(self):
        bridge = FakeBridge(TypedRouteOutcome(handled=False, reason="lilith_offline", notice="LILITH no disponible"))
        jarvis, client = _live(bridge)
        asyncio.run(jarvis.send_text("recuerda que x"))
        self.assertEqual(jarvis.session.sent, ["recuerda que x"])
        self.assertIn("SYS: LILITH no disponible", client.logs)

    def test_self_quit_is_never_offered_to_lilith(self):
        bridge = FakeBridge(raises=AssertionError("bridge must not be consulted"))
        jarvis, client = _live(bridge)
        with patch.object(main.JarvisLive, "_is_explicit_self_quit_transcript", return_value=True), \
             patch.object(main.JarvisLive, "_queue_self_quit_after_farewell"):
            asyncio.run(jarvis.send_text("apágate"))
        self.assertEqual(bridge.calls, [])
        self.assertEqual(len(jarvis.session.sent), 1)
        self.assertIn("VERIFIED LOCAL SELF-SHUTDOWN", jarvis.session.sent[0])

    def test_internal_ui_prompts_reach_gemini(self):
        real_bridge = _started_bridge(FakeRuntime(result={"handled": True, "data": {}}))
        jarvis, client = _live(real_bridge)
        asyncio.run(jarvis.send_text('[UI EVENT] Say exactly: "luz"'))
        self.assertEqual(len(jarvis.session.sent), 1)

    def test_empty_text_and_missing_session_keep_previous_behaviour(self):
        bridge = FakeBridge()
        jarvis, _ = _live(bridge)
        self.assertFalse(asyncio.run(jarvis.send_text("   ")))
        jarvis.session = None
        self.assertFalse(asyncio.run(jarvis.send_text("hola")))
        self.assertEqual(bridge.calls, [])


# ── JarvisLive.run lifecycle ─────────────────────────────────────────────

class RunLifecycleTests(unittest.TestCase):
    def _run(self, jarvis, bridge, live=None):
        async def fake_live(self_):
            if live:
                await live()
        with patch.object(main.JarvisLive, "_run_live", fake_live), \
             patch.object(main.LilithBridge, "from_env", return_value=bridge) as from_env:
            try:
                asyncio.run(jarvis.run())
            finally:
                self.from_env = from_env

    def test_bridge_is_started_before_and_stopped_after_the_live_loop(self):
        bridge = FakeBridge()
        jarvis, client = _live()
        seen = {}

        async def live():
            seen["started_during"] = bridge.started
            seen["attached"] = jarvis._lilith is bridge
        self._run(jarvis, bridge, live)
        self.assertEqual(seen, {"started_during": True, "attached": True})
        self.assertTrue(bridge.stopped)
        self.assertIsNone(jarvis._lilith)
        self.assertTrue(any("LILITH integration online" in l for l in client.logs))

    def test_bridge_is_stopped_even_if_the_live_loop_fails(self):
        bridge = FakeBridge()
        jarvis, _ = _live()

        async def live():
            raise RuntimeError("gemini down")
        with self.assertRaises(RuntimeError):
            self._run(jarvis, bridge, live)
        self.assertTrue(bridge.stopped)

    def test_unconfigured_lilith_leaves_run_untouched(self):
        jarvis, client = _live()
        ran = []

        async def live():
            ran.append(True)
        self._run(jarvis, None, live)
        self.assertEqual(ran, [True])
        self.assertEqual(client.logs, [])

    def test_cloud_safe_never_starts_the_bridge(self):
        bridge = FakeBridge()
        jarvis, _ = _live(cloud_safe=True)
        self._run(jarvis, bridge)
        self.from_env.assert_not_called()
        self.assertFalse(bridge.started)


if __name__ == "__main__":
    unittest.main()