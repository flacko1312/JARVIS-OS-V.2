"""Opt-in shared alarms over LILITH's existing semantic-memory API.

Not a distributed scheduler: both JARVIS instances edit the same v2 records;
only the Ubuntu watcher may deliver them. Legacy local alarms remain untouched.
No secrets are stored in the records. Enabled separately by
JARVIS_SHARED_ALARMS_ENABLED=1 after a supervised deployment.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

_CATEGORY = "jarvis_alarm"
_RECEIPT_CATEGORY = "jarvis_alarm_receipt"
_RECEIPT_PREFIX = "jarvis_shared_alarm_receipt_v2:"
_PREFIX = "jarvis_shared_alarm_v2:"
_DELIVERY_MODE = "ubuntu_only_v2"
_ROOT = "/api/v1/integration"


class SharedAlarmError(RuntimeError):
    """An operation was not confirmed by the authoritative LILITH store."""


def is_enabled() -> bool:
    return os.environ.get("JARVIS_SHARED_ALARMS_ENABLED", "").lower() in {"1", "true", "yes"}


def local_zone():
    try:
        return ZoneInfo(os.environ.get("JARVIS_ALARM_TIMEZONE", "Europe/Madrid"))
    except (KeyError, ImportError):
        return datetime.now().astimezone().tzinfo


def aware_iso(value: datetime) -> str:
    """Use an offset-aware timestamp so both hosts agree on the instant."""
    return (value if value.tzinfo else value.replace(tzinfo=local_zone())).isoformat()


def parse_instant(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("Shared alarm requires timezone offset")
    return result.astimezone(timezone.utc)


class SharedAlarmStore:
    """Strict shared record client. Errors are returned, never silently ignored.

    Inject a fake HTTP client for hermetic tests. Production builds an httpx
    client using the existing LILITH_API_URL/LILITH_API_KEY env configuration.
    """

    def __init__(self, *, source: str, http_client=None) -> None:
        if source not in {"jarvis_windows", "jarvis_ubuntu"}:
            raise ValueError("Invalid JARVIS source")
        self.source = source
        self._injected = http_client

    def _request(self, method: str, suffix: str, payload: dict | None = None) -> dict:
        close = False
        client = self._injected
        if client is None:
            base = os.environ.get("LILITH_API_URL", "").rstrip("/")
            key = os.environ.get("LILITH_API_KEY", "")
            if not base or not key:
                raise SharedAlarmError("LILITH no está configurada; ninguna alarma compartida modificada.")
            try:
                import httpx
                timeout = min(15.0, max(1.0, float(os.environ.get("JARVIS_ALARM_STORE_TIMEOUT", "4"))))
                client = httpx.Client(base_url=base, headers={"Authorization": f"Bearer {key}"}, timeout=timeout)
                close = True
            except (ImportError, ValueError) as exc:
                raise SharedAlarmError("No se puede inicializar conexión segura a LILITH.") from exc
        try:
            if method == "GET":
                response = client.get(_ROOT + suffix)
            else:
                response = client.post(_ROOT + suffix, json=payload)
            if response.status_code != 200:
                raise SharedAlarmError(f"LILITH rechazó {suffix} (HTTP {response.status_code}); sin confirmar.")
            body = response.json()
            if not isinstance(body, dict) or body.get("ok") is not True or not isinstance(body.get("data"), dict):
                raise SharedAlarmError("Respuesta de LILITH no válida; sin confirmar.")
            return body["data"]
        except SharedAlarmError:
            raise
        except Exception as exc:
            raise SharedAlarmError("LILITH inaccesible o respuesta inválida; operación sin confirmar.") from exc
        finally:
            if close:
                client.close()

    @staticmethod
    def _key(alarm_id: str) -> str:
        if not isinstance(alarm_id, str) or len(alarm_id) != 32 or any(c not in "0123456789abcdef" for c in alarm_id):
            raise SharedAlarmError("Identificador compartido inválido.")
        return _PREFIX + alarm_id

    @classmethod
    def _parse_fact(cls, fact: Any) -> dict | None:
        if not isinstance(fact, dict) or not isinstance(fact.get("key"), str):
            return None
        try:
            raw = json.loads(fact["value"])
            if not isinstance(raw, dict) or raw.get("delivery_mode") != _DELIVERY_MODE:
                return None
            alarm_id = raw.get("id")
            if fact["key"] != "jarvis:" + cls._key(alarm_id):
                return None
            if raw.get("source") not in {"jarvis_windows", "jarvis_ubuntu"}:
                return None
            if not isinstance(raw.get("label"), str) or not raw["label"].strip():
                return None
            parse_instant(raw["fire_at"])
            if not isinstance(raw.get("revision"), int) or raw["revision"] < 1:
                return None
            return raw
        except (ValueError, TypeError, KeyError, SharedAlarmError, json.JSONDecodeError):
            return None

    def list(self) -> list[dict]:
        data = self._request("GET", "/memory/context")
        cats = data.get("categories")
        if not isinstance(cats, dict) or not isinstance(cats.get(_CATEGORY, []), list):
            raise SharedAlarmError("LILITH no devolvió categorías de memoria válidas.")
        receipts = cats.get(_RECEIPT_CATEGORY, [])
        if not isinstance(receipts, list):
            raise SharedAlarmError("LILITH devolvió recibos de alarmas inválidos.")
        claimed = set()
        for fact in receipts:
            try:
                payload = json.loads(fact["value"])
                stamp = (payload["id"], payload["revision"])
                key = "jarvis:" + _RECEIPT_PREFIX + f"{stamp[0]}:{stamp[1]}"
                if fact.get("key") == key and payload.get("status") == "claimed":
                    claimed.add(stamp)
            except (KeyError, ValueError, TypeError, AttributeError):
                continue
        records = [self._parse_fact(f) for f in cats.get(_CATEGORY, [])]
        return sorted(
            (v for v in records if v is not None and (v["id"], v["revision"]) not in claimed),
            key=lambda a: a["fire_at"],
        )

    def claim_delivery(self, item: dict) -> bool:
        """Durable at-most-once attempt token; only Ubuntu may claim a delivery.

        This is NOT a transactional compare-and-swap. Only one supervised
        Ubuntu watcher is allowed; a concurrent modify during claim remains a
        documented limitation of LILITH's general-purpose memory API.
        """
        if self.source != "jarvis_ubuntu":
            raise SharedAlarmError("Windows no puede ejecutar alarmas compartidas.")
        latest = next((a for a in self.list() if a["id"] == item["id"]), None)
        if latest != item:
            return False
        receipt = {"id": item["id"], "revision": item["revision"], "status": "claimed"}
        self._request("POST", "/memory/store", {
            "key": _RECEIPT_PREFIX + f"{item['id']}:{item['revision']}",
            "value": json.dumps(receipt, separators=(",", ":")),
            "category": _RECEIPT_CATEGORY,
            "confidence": 1.0,
        })
        return not any(a["id"] == item["id"] and a["revision"] == item["revision"] for a in self.list())

    def _write(self, item: dict) -> None:
        self._request("POST", "/memory/store", {
            "key": self._key(item["id"]),
            "value": json.dumps(item, ensure_ascii=False, separators=(",", ":")),
            "category": _CATEGORY,
            "confidence": 1.0,
            "metadata": {"kind": "shared_alarm_v2", "source": item["source"]},
            "description": "JARVIS shared alarm (Ubuntu delivery owner)",
        })

    def _verify(self, alarm_id: str, expected: dict | None) -> None:
        found = next((item for item in self.list() if item["id"] == alarm_id), None)
        if (found is None) != (expected is None) or (found is not None and found != expected):
            raise SharedAlarmError("LILITH no confirmó el estado final; verificar antes de reintentar.")

    def create(self, label: str, fire_at: datetime) -> dict:
        if not label or not label.strip():
            raise SharedAlarmError("La alarma necesita un nombre.")
        instant = parse_instant(aware_iso(fire_at))
        if instant <= datetime.now(timezone.utc):
            raise SharedAlarmError("La hora indicada ya ha pasado.")
        self.list()  # refuse to claim a shared alarm while the store is offline
        record = {
            "id": uuid.uuid4().hex,
            "label": label.strip(),
            "fire_at": aware_iso(fire_at),
            "source": self.source,
            "revision": 1,
            "delivery_mode": _DELIVERY_MODE,
        }
        self._write(record)
        self._verify(record["id"], record)
        return record

    def find(self, *, alarm_id: str = "", label_match: str = "") -> dict:
        items = self.list()
        if alarm_id:
            matches = [a for a in items if a["id"] == alarm_id]
        elif label_match:
            matches = [a for a in items if label_match.casefold() in a["label"].casefold()]
        else:
            raise SharedAlarmError("Indica ID o nombre para modificar/cancelar.")
        if not matches:
            raise SharedAlarmError("No se encontró esa alarma compartida.")
        if len(matches) != 1:
            raise SharedAlarmError("Varias alarmas coinciden; indica el ID exacto.")
        return matches[0]

    def modify(self, *, alarm_id: str = "", label_match: str = "",
               fire_at: datetime, label: str = "") -> dict:
        old = self.find(alarm_id=alarm_id, label_match=label_match)
        if parse_instant(aware_iso(fire_at)) <= datetime.now(timezone.utc):
            raise SharedAlarmError("La nueva hora ya ha pasado.")
        updated = {
            **old, "fire_at": aware_iso(fire_at),
            "label": label.strip() or old["label"],
            "revision": old["revision"] + 1,
        }
        # Same key, no delete+reinsert (LILITH uses soft-deletes).
        self._write(updated)
        self._verify(old["id"], updated)
        return updated

    def cancel(self, *, alarm_id: str = "", label_match: str = "") -> dict:
        old = self.find(alarm_id=alarm_id, label_match=label_match)
        self._request("POST", "/memory/delete", {
            "key": self._key(old["id"]), "reason": "shared_alarm_cancelled",
        })
        self._verify(old["id"], None)
        return old


def shared_alarm_action(parameters: dict | None, *, source: str) -> str:
    """JARVIS tool routing; network errors are visible rather than false success."""
    params = parameters or {}
    action = str(params.get("action") or "list").strip().lower()
    store = SharedAlarmStore(source=source)
    try:
        if action in {"list", "show", "mostrar", "ver", "list_shared", "listar_compartidas", "todas"}:
            items = store.list()
            if not items:
                return "No hay alarmas compartidas. Las alarmas locales antiguas siguen separadas."
            return "Alarmas compartidas (sonido a cargo de Ubuntu):\n" + "\n".join(
                f"  [{a['id']}] {a['label']} — {a['fire_at']} ({a['source']})" for a in items
            )
        alarm_id = str(params.get("id") or params.get("alarm_id") or "").strip()
        label_match = str(params.get("label_match") or "").strip()
        if action in {"cancel", "cancelar", "delete", "remove", "borrar"}:
            removed = store.cancel(alarm_id=alarm_id, label_match=label_match)
            return f"Cancelación compartida confirmada en LILITH: {removed['label']}."
        if action in {"set", "crear", "poner", "add", "new", "modify", "modificar", "cambiar", "change", "update", "mover"}:
            time_text = str(params.get("time") or params.get("hora") or "").strip()
            # Reuse the already tested Spanish clock/relative parser without I/O.
            from actions.alarm_control import _parse_time_str
            parsed = _parse_time_str(time_text)
            if parsed is None:
                return "No entendí la hora indicada. Indica HH:MM o una duración."
            label = str(params.get("label") or params.get("nombre") or "").strip()
            if action in {"set", "crear", "poner", "add", "new"}:
                alarm = store.create(label or "Alarma compartida", parsed)
                return f"Alarma compartida guardada: {alarm['label']} ({alarm['id']}). La anunciará Ubuntu si está activo."
            alarm = store.modify(alarm_id=alarm_id, label_match=label_match, fire_at=parsed, label=label)
            return f"Alarma compartida modificada y confirmada: {alarm['label']} ({alarm['id']})."
        return f"Acción de alarma no reconocida: {action}."
    except SharedAlarmError as exc:
        return f"Alarma compartida NO confirmada: {exc}"
