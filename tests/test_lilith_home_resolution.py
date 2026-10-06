"""JL-H005: typed HOME commands -> LILITH resolver -> /home/action (fake LILITH).

JARVIS understands the intent (on/off + reference text); LILITH resolves the
reference and authorizes the action. These tests use the real router + runtime +
bridge with a fake LILITH client: no network, no Gemini, no real devices.
"""
import asyncio
import unittest
from types import SimpleNamespace

import httpx

import router.core as router_core
from core.lilith_gateway import LilithBridge
from lilith_client.client import LilithClient
from lilith_client.config import LilithConfig
from lilith_client.errors import (
    LilithConnectionError, LilithError, LilithForbiddenError, LilithServerError,
)
from router.core import JarvisRouter, _parse_home_command

router_core._HOME_CONFIRM_DELAY = 0  # no sleeping in tests


class FakeLilith:
    """Fake LILITH client. `resolve` maps reference -> resolver response."""

    def __init__(self, resolve=None, state_after="on", action_exc=None, resolve_exc=None):
        self._resolve = resolve or {}
        self._state_after = state_after
        self._action_exc = action_exc
        self._resolve_exc = resolve_exc
        self.resolved, self.actions, self.entity_reads = [], [], []

    async def home_resolve(self, query):
        self.resolved.append(query)
        if self._resolve_exc:
            raise self._resolve_exc
        return self._resolve.get(query, {"status": "unknown", "query": query})

    async def home_action(self, entity_id, action, **kw):
        self.actions.append((entity_id, action))
        if self._action_exc:
            raise self._action_exc
        return {"entity_id": entity_id, "action": action}

    async def home_entity(self, entity_id):
        self.entity_reads.append(entity_id)
        return {"entity_id": entity_id, "state": self._state_after}


MUEBLE = {"status": "resolved", "entity_id": "light.bombilla_mueble",
          "friendly_name": "bombilla habitación", "state": "off", "available": True}
AMBIGUOUS = {"status": "ambiguous", "candidates": [
    {"entity_id": "light.bombilla_mueble", "friendly_name": "bombilla habitación"},
    {"entity_id": "light.bombilla_tv", "friendly_name": "Bombilla tv"}]}


def _bridge(fake, available=True):
    from runtime import JarvisRuntime
    from lilith_client.config import LilithConfig
    rt = JarvisRuntime(LilithConfig(base_url="http://127.0.0.1:9", api_key="test-key"))
    rt.router._client = fake
    rt.router._monitor = SimpleNamespace(status=SimpleNamespace(is_available=available))
    rt._monitor = rt.router._monitor
    bridge = LilithBridge(rt)
    bridge._started = True
    return bridge


def _say(fake, text, **kw):
    return asyncio.run(_bridge(fake, **kw).route_typed(text))


class ParseTests(unittest.TestCase):
    def test_parse_on_off_and_reference(self):
        cases = {
            "enciende la luz del mueble": ("turn_on", "la luz del mueble"),
            "Apaga la luz del mueble, por favor": ("turn_off", "la luz del mueble"),
            "desactiva la luz del mueble": ("turn_off", "la luz del mueble"),   # not 'activa'
            "prende la luz de la tv": ("turn_on", "la luz de la tv"),
            "enciéndeme la bombilla": ("turn_on", "la bombilla"),
            "la luz del mueble apágala": ("turn_off", "la luz del mueble"),
            "baja la luz de la pantalla": (None, ""),
            "apaga": ("turn_off", ""),
        }
        for text, expected in cases.items():
            self.assertEqual(_parse_home_command(text), expected, text)


class HomeResolutionFlowTests(unittest.TestCase):
    def test_turn_on_resolves_through_lilith_and_confirms_readback(self):
        fake = FakeLilith({"la luz del mueble": MUEBLE}, state_after="on")
        out = _say(fake, "enciende la luz del mueble")
        self.assertTrue(out.handled)                      # NOT sent to Gemini
        self.assertEqual(fake.resolved, ["la luz del mueble"])
        self.assertEqual(fake.actions, [("light.bombilla_mueble", "turn_on")])
        self.assertIn("confirmado: on", out.message)
        self.assertEqual(fake.entity_reads, ["light.bombilla_mueble"])

    def test_turn_off(self):
        fake = FakeLilith({"la luz del mueble": MUEBLE}, state_after="off")
        out = _say(fake, "apaga la luz del mueble")
        self.assertEqual(fake.actions, [("light.bombilla_mueble", "turn_off")])
        self.assertIn("confirmado: off", out.message)

    def test_desactiva_turns_off_not_on(self):
        fake = FakeLilith({"la luz del mueble": MUEBLE}, state_after="off")
        _say(fake, "desactiva la luz del mueble")
        self.assertEqual(fake.actions, [("light.bombilla_mueble", "turn_off")])

    def test_only_turn_on_and_turn_off_are_ever_requested(self):
        fake = FakeLilith({"la luz del mueble": MUEBLE})
        for text in ("enciende la luz del mueble", "apaga la luz del mueble",
                     "prende la luz del mueble", "desactiva la luz del mueble"):
            _say(fake, text)
        self.assertTrue({a for _, a in fake.actions} <= {"turn_on", "turn_off"})

    def test_state_not_confirmed_is_reported_honestly(self):
        fake = FakeLilith({"la luz del mueble": MUEBLE}, state_after="off")
        out = _say(fake, "enciende la luz del mueble")
        self.assertTrue(out.handled)
        self.assertIn("no pude confirmar", out.message)
        self.assertNotIn("Hecho", out.message)

    def test_ambiguous_asks_for_clarification_and_does_nothing(self):
        fake = FakeLilith({"la bombilla": AMBIGUOUS})
        out = _say(fake, "enciende la bombilla")
        self.assertTrue(out.handled)
        self.assertIn("¿A cuál", out.message)
        self.assertIn("bombilla habitación", out.message)
        self.assertIn("Bombilla tv", out.message)
        self.assertEqual(fake.actions, [])

    def test_unknown_device_does_not_execute(self):
        fake = FakeLilith()
        out = _say(fake, "enciende la luz del baño")
        self.assertTrue(out.handled)
        self.assertIn("No conozco", out.message)
        self.assertEqual(fake.actions, [])

    def test_not_allowlisted_domain_does_not_execute(self):
        fake = FakeLilith({"el servidor": {"status": "not_allowed"}})
        out = _say(fake, "apaga el servidor")  # 'servidor' is not a HOME word, 'apaga' alone is not HOME
        # Not classified as HOME at all -> goes to Gemini; and with a HOME word:
        out = _say(fake, "apaga la luz del servidor")
        self.assertEqual(fake.actions, [])

    def test_not_allowed_status_message(self):
        fake = FakeLilith({"la luz del servidor": {"status": "not_allowed"}})
        out = _say(fake, "apaga la luz del servidor")
        self.assertTrue(out.handled)
        self.assertIn("No tengo permiso", out.message)
        self.assertEqual(fake.actions, [])

    def test_unexpected_resolver_payload_does_nothing(self):
        fake = FakeLilith({"la luz del mueble": {"status": "resolved"}})  # no entity_id
        out = _say(fake, "enciende la luz del mueble")
        self.assertTrue(out.handled)
        self.assertEqual(fake.actions, [])

    def test_no_on_off_verb_still_reaches_gemini(self):
        fake = FakeLilith()
        for text in ("baja la luz de la pantalla", "cierra la puerta del garaje"):
            out = _say(fake, text)
            self.assertFalse(out.handled, text)
        self.assertEqual((fake.resolved, fake.actions), ([], []))

    def test_no_device_names_are_hardcoded_in_jarvis(self):
        import inspect
        src = inspect.getsource(router_core)
        for name in ("bombilla_mueble", "bombilla_tv", "light.", "switch."):
            self.assertNotIn(name, src)


class HomeFailureTests(unittest.TestCase):
    def _fail(self, exc, text="enciende la luz del mueble"):
        fake = FakeLilith({"la luz del mueble": MUEBLE}, action_exc=exc)
        out = _say(fake, text)
        self.assertTrue(out.handled, "a failed physical action must not fall through to Gemini")
        self.assertEqual(fake.entity_reads, [])      # no readback after a rejected action
        return out.message

    def test_unavailable_entity(self):
        msg = self._fail(LilithServerError("x"))      # code defaults to server_error
        self.assertIn("No he hecho nada", msg)
        err = LilithServerError("x"); err.code = "entity_unavailable"
        self.assertIn("no está disponible", self._fail(err))

    def test_entity_not_found(self):
        err = LilithServerError("x"); err.code = "entity_not_found"
        self.assertIn("No encuentro", self._fail(err))

    def test_policy_denials(self):
        for code in ("domain_not_allowed", "service_not_allowed",
                     "prohibited_by_decision_level", "approval_required"):
            self.assertIn("No tengo permiso", self._fail(LilithForbiddenError("x", code=code)), code)

    def test_home_assistant_down(self):
        err = LilithServerError("x"); err.code = "home_assistant_error"
        self.assertIn("Home Assistant no responde", self._fail(err))

    def test_unknown_error_code_is_reported_not_swallowed(self):
        self.assertIn("rechazó", self._fail(LilithError("x", code="weird")))

    def test_lilith_unreachable_during_action_is_reported_not_sent_to_gemini(self):
        fake = FakeLilith({"la luz del mueble": MUEBLE}, action_exc=LilithConnectionError())
        out = _say(fake, "enciende la luz del mueble")
        self.assertTrue(out.handled)
        self.assertIn("no está disponible", out.message)

    def test_lilith_offline_for_home_is_reported_not_sent_to_gemini(self):
        out = _say(FakeLilith(), "enciende la luz del mueble", available=False)
        self.assertTrue(out.handled)
        self.assertIn("No puedo controlar la casa", out.message)

    def test_lilith_offline_for_memory_still_passes_through(self):
        out = _say(FakeLilith(), "recuerda que mi test es azul", available=False)
        self.assertFalse(out.handled)

    def test_malformed_reference_is_rejected_by_lilith(self):
        fake = FakeLilith(resolve_exc=LilithError("x", code="invalid_query"))
        out = _say(fake, "enciende la luz del mueble")
        self.assertTrue(out.handled)
        self.assertIn("No entendí", out.message)
        self.assertEqual(fake.actions, [])

    def test_verb_without_reference_asks_and_does_nothing(self):
        fake = FakeLilith()
        res = asyncio.run(JarvisRouter(fake, SimpleNamespace())._handle_home(
            SimpleNamespace(params={"raw_input": "apaga"})))
        self.assertTrue(res["needs_clarification"])
        self.assertEqual((fake.resolved, fake.actions), ([], []))


class ClientErrorCodeTests(unittest.TestCase):
    def _resp(self, status, detail):
        return httpx.Response(status, json={"detail": detail})

    def test_5xx_keeps_lilith_error_code(self):
        resp = self._resp(502, {"ok": False, "code": "entity_unavailable", "message": "no disponible", "retryable": True})
        with self.assertRaises(LilithServerError) as ctx:
            LilithClient._handle_response(resp)
        self.assertEqual(ctx.exception.code, "entity_unavailable")

    def test_400_keeps_code(self):
        resp = self._resp(400, {"ok": False, "code": "invalid_query", "message": "query vacío"})
        with self.assertRaises(LilithError) as ctx:
            LilithClient._handle_response(resp)
        self.assertEqual(ctx.exception.code, "invalid_query")

    def test_403_keeps_code(self):
        resp = self._resp(403, {"ok": False, "code": "domain_not_allowed", "message": "no"})
        with self.assertRaises(LilithForbiddenError) as ctx:
            LilithClient._handle_response(resp)
        self.assertEqual(ctx.exception.code, "domain_not_allowed")

    def test_plain_5xx_without_detail_still_raises(self):
        with self.assertRaises(LilithServerError):
            LilithClient._handle_response(httpx.Response(500, text="boom"))

    def test_home_resolve_posts_the_query(self):
        seen = {}

        class C(LilithClient):
            async def _request(self, method, path, *, json=None):
                seen.update(method=method, path=path, json=json)
                return {"status": "unknown"}
        cfg = LilithConfig(base_url="http://127.0.0.1:9", api_key="test-key")
        asyncio.run(C(cfg).home_resolve("luz del mueble"))
        self.assertEqual(seen, {"method": "POST", "path": "/api/v1/integration/home/resolve",
                                "json": {"query": "luz del mueble"}})

    def test_runtime_status_gets_integration_endpoint(self):
        seen = {}

        class C(LilithClient):
            async def _request(self, method, path, *, json=None):
                seen.update(method=method, path=path, json=json)
                return {"health": {"status": "online"}}

        cfg = LilithConfig(base_url="http://127.0.0.1:9", api_key="test-key")
        out = asyncio.run(C(cfg).runtime_status())
        self.assertEqual(out["health"]["status"], "online")
        self.assertEqual(seen, {
            "method": "GET",
            "path": "/api/v1/integration/runtime/status",
            "json": None,
        })

    def test_docs_methods_use_integration_endpoints(self):
        seen = []

        class C(LilithClient):
            async def _request(self, method, path, *, json=None):
                seen.append((method, path, json))
                return {"ok": True}

        cfg = LilithConfig(base_url="http://127.0.0.1:9", api_key="test-key")
        client = C(cfg)
        asyncio.run(client.docs_list(prefix="AI_MEMORY"))
        asyncio.run(client.docs_read("TASKS.md", max_bytes=1234))
        asyncio.run(client.docs_search("AUT-7", limit=4, max_matches_per_file=2))

        self.assertEqual(seen, [
            ("GET", "/api/v1/integration/docs/list?prefix=AI_MEMORY", None),
            ("POST", "/api/v1/integration/docs/read", {"path": "TASKS.md", "max_bytes": 1234}),
            ("POST", "/api/v1/integration/docs/search", {
                "query": "AUT-7", "limit": 4, "max_matches_per_file": 2,
            }),
        ])

    def test_source_methods_use_integration_endpoints(self):
        seen = []

        class C(LilithClient):
            async def _request(self, method, path, *, json=None):
                seen.append((method, path, json))
                return {"ok": True}

        cfg = LilithConfig(base_url="http://127.0.0.1:9", api_key="test-key")
        client = C(cfg)
        asyncio.run(client.source_list(prefix="core/routers"))
        asyncio.run(client.source_read("core/routers/integration.py", max_bytes=4321))
        asyncio.run(client.source_search("DecisionLevel", limit=6, max_matches_per_file=2))

        self.assertEqual(seen, [
            ("GET", "/api/v1/integration/source/list?prefix=core%2Frouters", None),
            ("POST", "/api/v1/integration/source/read", {
                "path": "core/routers/integration.py", "max_bytes": 4321,
            }),
            ("POST", "/api/v1/integration/source/search", {
                "query": "DecisionLevel", "limit": 6, "max_matches_per_file": 2,
            }),
        ])


if __name__ == "__main__":
    unittest.main()
