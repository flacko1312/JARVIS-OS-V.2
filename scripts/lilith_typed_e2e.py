"""Manual E2E for typed-input LILITH routing (JL-W004).

Runs the REAL ``JarvisLive.run()`` (real .env, real Gemini Live session, real
LilithBridge/JarvisRuntime/router/client, real LILITH over the network). Only the
HUD is stubbed. Side effects: stores one test memory in LILITH, makes a short
low-brightness change on one light entity and restores its original state, makes
one short Gemini turn. Usage:  .venv\\Scripts\\python.exe scripts\\lilith_typed_e2e.py
Never prints the credential.
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx  # noqa: E402
import main  # noqa: E402  (loads .env)
from core.lilith_gateway import LilithBridge  # noqa: E402
from lilith_client.config import LilithConfig  # noqa: E402
from lilith_client.errors import LilithForbiddenError  # noqa: E402
from runtime import JarvisRuntime  # noqa: E402

LIGHT = os.environ.get("JL_E2E_LIGHT", "light.bombilla_mueble")
MARK = f"JL-W004-{int(time.time()) % 100000}"
VALUE = f"el codigo de prueba {MARK} es naranja"
RESULTS: list[tuple[str, bool, str]] = []


def check(name, ok, evidence=""):
    RESULTS.append((name, bool(ok), str(evidence)[:160]))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{evidence}]" if evidence else ""), flush=True)


class HudStub:
    """Permissive stand-in for the desktop HUD; records log lines."""
    def __init__(self):
        self.on_text_command = None
        self.muted = False
        self.current_file = None
        self._voice_combo = None
        self.logs: list[str] = []

    def write_log(self, text):
        self.logs.append(str(text))

    def __getattr__(self, name):
        return lambda *a, **k: None


async def wait_for(pred, timeout, step=0.5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        await asyncio.sleep(step)
    return pred()


async def light_state(client):
    return (await client.home_entity(LIGHT))["state"]


async def light_settle(client, want, timeout=15):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if await light_state(client) == want:
            return True
        await asyncio.sleep(1)
    return False


async def scenario(jarvis, hud):
    gemini_sent: list[str] = []
    if not await wait_for(lambda: jarvis.session is not None and jarvis._lilith is not None, 60):
        check("0 JARVIS live session + bridge up", False, "timeout")
        return
    session = jarvis.session
    orig = session.send_client_content

    async def recording(*a, **k):
        try:
            gemini_sent.append(k["turns"]["parts"][0]["text"])
        except Exception:
            pass
        return await orig(*a, **k)
    try:
        session.send_client_content = recording
    except Exception:
        type(session).send_client_content = recording
    bridge = jarvis._lilith
    client = bridge._runtime.client

    # 2/3. runtime up, LILITH health
    check("2 runtime started with LILITH available", bridge.is_running and bridge.lilith_available)
    check("2b HUD announced integration online", any("LILITH integration online" in l for l in hud.logs))
    h = await client.health()
    check("3 LILITH health via client", h.get("status") in ("online", "degraded"), h.get("status"))

    # 1. normal typed conversation reaches Gemini (and Gemini answers)
    n_logs = len(hud.logs)
    prompt = "Responde unicamente con la palabra OK."
    await jarvis.send_text(prompt)
    got = await wait_for(lambda: any(l.startswith("Jarvis:") for l in hud.logs[n_logs:]), 45)
    check("1 normal typed text reached Gemini", prompt in gemini_sent, "sent to Gemini")
    check("1b Gemini answered (real Live round-trip)", got,
          next((l for l in hud.logs[n_logs:] if l.startswith("Jarvis:")), "no reply"))

    # 4. store allowed test memory (typed -> router -> LILITH), NOT sent to Gemini
    before = len(gemini_sent)
    await jarvis.send_text(f"recuerda que {VALUE}")
    check("4 memory stored via typed input", any(l.startswith("LILITH: Guardado") for l in hud.logs), "HUD: Guardado")
    check("4b stored text NOT sent to Gemini", len(gemini_sent) == before)

    # 5. retrieve the same memory
    before = len(gemini_sent); n_logs = len(hud.logs)
    await jarvis.send_text(f"que sabes de {MARK}")
    found = any(l.startswith("LILITH:") and MARK in l for l in hud.logs[n_logs:])
    if not found:  # direct API as evidence if the typed phrasing did not retrieve it
        res = await client.search_memory(MARK)
        found_api = any(MARK in json.dumps(r) for r in res)
        check("5 memory retrieved via typed input", False, "typed search did not surface it")
        check("5b memory retrievable via client.search_memory", found_api, f"{len(res)} results")
    else:
        check("5 memory retrieved via typed input", True, "HUD shows stored value")
    check("5c search text NOT sent to Gemini", len(gemini_sent) == before)

    # 6-8. light: read, safe change, readback, restore
    init = await light_state(client)
    ent = await client.home_entity(LIGHT)
    check("6 HA light entity read", ent.get("entity_id") == LIGHT, f"{LIGHT}={init}")
    target = "off" if init == "on" else "on"
    try:
        r = await client.home_action(LIGHT, "turn_on" if target == "on" else "turn_off",
                                     parameters={"brightness_pct": 10} if target == "on" else None)
        ok_call = r.get("action") in ("turn_on", "turn_off")
        check("7 allowlisted light action accepted", ok_call, r.get("decision_level"))
        check("7b readback shows new state", await light_settle(client, target), f"{init} -> {target}")
    finally:
        await client.home_action(LIGHT, "turn_on" if init == "on" else "turn_off")
        restored = await light_settle(client, init)
        check("12 light restored to original state (readback)", restored, f"final={await light_state(client)} initial={init}")

    # 9. non-allowlisted action rejected
    for action, ent_id, code in (("toggle", LIGHT, "service_not_allowed"),
                                 ("turn_off", "switch.control_servidor_lilith", "domain_not_allowed")):
        try:
            await client.home_action(ent_id, action)
            check(f"9 rejected {ent_id}.{action}", False, "was accepted!")
        except LilithForbiddenError as exc:
            check(f"9 rejected {ent_id}.{action}", getattr(exc, "code", "") == code, getattr(exc, "code", ""))

    # 10. integration credential cannot use raw HA services
    cfg = client._cfg
    async with httpx.AsyncClient(base_url=cfg.base_url, timeout=10,
                                 headers={"Authorization": f"Bearer {cfg.api_key}"}) as raw:
        r = await raw.post("/api/ha/services/light/turn_on", json={"entity_id": LIGHT})
        r2 = await raw.post("/api/ha/services/switch/turn_off", json={"entity_id": "switch.control_servidor_lilith"})
    check("10 integration token blocked on /api/ha/services/*", r.status_code == 403 and r2.status_code == 403,
          f"{r.status_code}/{r2.status_code}")

    # 11. LILITH unavailable (simulated: unreachable endpoint) -> JARVIS keeps working
    dead = LilithBridge(JarvisRuntime(LilithConfig(base_url="http://127.0.0.1:9", api_key="x",
                                                   timeout_seconds=2, max_retries=0)))
    await dead.start()
    await dead._runtime.monitor.check_now()
    jarvis._lilith = dead
    before = len(gemini_sent); n_logs = len(hud.logs)
    text = f"que sabes de {MARK} sin conexion"
    await jarvis.send_text(text)
    check("11 offline: text passed through to Gemini", text in gemini_sent[before:], "sent to Gemini")
    check("11b offline: HUD notice shown", any("LILITH no disponible" in l for l in hud.logs[n_logs:]))
    got = await wait_for(lambda: any(l.startswith("Jarvis:") for l in hud.logs[n_logs:]), 45)
    check("11c offline: JARVIS/Gemini kept answering", got)
    await dead.stop()
    jarvis._lilith = bridge
    # restore: real bridge handles memory again
    n_logs = len(hud.logs)
    await jarvis.send_text(f"que sabes de {MARK}")
    check("12b LILITH restored: typed memory query handled by LILITH again",
          any(l.startswith("LILITH:") for l in hud.logs[n_logs:]))

    jarvis.request_shutdown()


async def main_async():
    hud = HudStub()
    jarvis = main.JarvisLive(hud, external_audio=True)
    async def no_announce(*a, **k):
        return None
    jarvis._announce_startup = no_announce   # no spoken greeting during the test
    task = asyncio.create_task(jarvis.run())
    try:
        await asyncio.wait_for(scenario(jarvis, hud), 300)
    except Exception as exc:  # noqa: BLE001
        check("scenario completed without exception", False, f"{type(exc).__name__}: {exc}")
        jarvis.request_shutdown()
    try:
        await asyncio.wait_for(task, 30)
        check("13 JARVIS run() exited cleanly; bridge stopped", jarvis._lilith is None)
    except Exception as exc:  # noqa: BLE001
        check("13 JARVIS run() exited cleanly", False, type(exc).__name__)
    bad = [r for r in RESULTS if not r[1]]
    print(f"\nSUMMARY: {len(RESULTS) - len(bad)}/{len(RESULTS)} PASS, {len(bad)} FAIL", flush=True)


if __name__ == "__main__":
    asyncio.run(main_async())