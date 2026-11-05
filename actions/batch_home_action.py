"""Batch home control — B23/B24: agrupación por habitación y control simultáneo.

Sends the same action to multiple home devices in one call, resolving each
target via LILITH's home.resolve endpoint. Each sub-action is independent —
a failure on one device does not stop the rest.

No external credentials required; uses the existing LILITH client passed at
call time (same bridge as lilith_home_action).
"""
from __future__ import annotations

import asyncio
from typing import Any


async def _resolve_and_act(client: Any, target: str, action: str, ha_params: dict | None) -> str:
    """Resolve one target and perform the action. Returns a result line."""
    try:
        res = await client.home_resolve(target)
        status = res.get("status")
        if status == "ambiguous":
            names = ", ".join(
                c.get("friendly_name") or c.get("entity_id")
                for c in res.get("candidates", [])
            )
            return f"⚠ '{target}': ambiguo ({names})"
        if status == "unknown":
            return f"⚠ '{target}': dispositivo desconocido"
        if status == "not_allowed":
            return f"⚠ '{target}': acceso denegado por LILITH"
        if status == "resolved" and res.get("entity_id"):
            entity_id = res["entity_id"]
            friendly = res.get("friendly_name") or target
            await client.home_action(entity_id, action, parameters=ha_params)
            verb = "encendido" if action == "turn_on" else "apagado"
            return f"✓ {friendly} — {verb}"
        return f"⚠ '{target}': respuesta inesperada ({status})"
    except Exception as exc:  # noqa: BLE001
        return f"✗ '{target}': error ({exc})"


async def batch_home_action_async(
    targets: list[str],
    action: str,
    client: Any,
    ha_params: dict | None = None,
) -> str:
    """Execute action on each target concurrently and return a summary."""
    if not targets:
        return "No devices specified."
    if action not in ("turn_on", "turn_off"):
        return f"Only turn_on and turn_off are supported, not '{action}'."

    tasks = [_resolve_and_act(client, t.strip(), action, ha_params) for t in targets if t.strip()]
    results = await asyncio.gather(*tasks)

    ok = [r for r in results if r.startswith("✓")]
    warn = [r for r in results if not r.startswith("✓")]

    verb = "encendidos" if action == "turn_on" else "apagados"
    summary = f"{len(ok)}/{len(results)} dispositivos {verb}."
    lines = [summary] + list(results)
    return "\n".join(lines)


def batch_home_action(
    parameters: dict[str, Any] | None = None,
    response: Any = None,
    player: Any = None,
    lilith_client: Any = None,
) -> str:
    """Synchronous wrapper — called from the tool dispatch with lilith_client injected."""
    params = parameters or {}
    targets_raw = params.get("targets", [])
    action = str(params.get("action", "turn_on"))
    ha_params_raw = params.get("parameters") or None

    # Accept comma-separated string or list
    if isinstance(targets_raw, str):
        targets = [t.strip() for t in targets_raw.split(",") if t.strip()]
    elif isinstance(targets_raw, list):
        targets = [str(t).strip() for t in targets_raw if t]
    else:
        targets = []

    if not targets:
        return "No devices specified. Pass 'targets' as a list of device names."

    if lilith_client is None:
        return "LILITH is not available. Cannot control home devices."

    ha_params: dict | None = None
    if isinstance(ha_params_raw, dict):
        ha_params = {k: v for k, v in ha_params_raw.items() if v is not None} or None

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(
            batch_home_action_async(targets, action, lilith_client, ha_params)
        )
    finally:
        loop.close()
