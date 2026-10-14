"""Durable, bounded local continuity for the desktop conversation.

This is transport-independent conversation state. It is intentionally separate
from LILITH persistent memory and from the legacy personal-memory JSON file.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
MAX_RECENT_ENTRIES = 24
MAX_TOOL_RESULTS = 12
MAX_ENTRY_CHARS = 2000
MAX_SUMMARY_CHARS = 8000

_LOCK = threading.RLock()
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_ -]?key|access[_ -]?token|refresh[_ -]?token|oauth|password|"
    r"secret|authorization|credential|cookie)\b\s*[:=]?\s*([^\s,;]+)"
)
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_store_path() -> Path:
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    return base / "memory" / "conversation_state.json"


def redact_sensitive_text(value: Any) -> str:
    text = " ".join(str(value or "").split()).strip()
    text = _PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", text)
    text = _BEARER.sub("Bearer [REDACTED]", text)
    return _SENSITIVE_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)


def empty_state(conversation_id: str | None = None) -> dict[str, Any]:
    now = _utc_now()
    return {
        "schema_version": SCHEMA_VERSION,
        "conversation_id": conversation_id or uuid.uuid4().hex,
        "summary": "",
        "recent_turns": [],
        "recent_tool_results": [],
        "metadata": {
            "created_at": now,
            "updated_at": now,
            "last_activity_at": None,
        },
    }


def _clean_entry(entry: Any, *, tool: bool = False) -> dict[str, str] | None:
    if not isinstance(entry, dict):
        return None
    text_key = "summary" if tool else "text"
    text = redact_sensitive_text(entry.get(text_key, ""))[:MAX_ENTRY_CHARS].strip()
    if not text:
        return None
    cleaned = {
        text_key: text,
        "timestamp": str(entry.get("timestamp") or _utc_now()),
    }
    if tool:
        cleaned["tool"] = redact_sensitive_text(entry.get("tool", "tool"))[:120]
    else:
        role = str(entry.get("role") or "user").lower()
        cleaned["role"] = role if role in {"user", "assistant"} else "user"
        turn_id = str(entry.get("turn_id") or "").strip()
        if turn_id:
            cleaned["turn_id"] = turn_id[:64]
    return cleaned


def normalize_state(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        return empty_state()
    conversation_id = str(value.get("conversation_id") or "").strip()
    if not conversation_id:
        conversation_id = uuid.uuid4().hex
    metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
    state = empty_state(conversation_id)
    state["summary"] = redact_sensitive_text(value.get("summary", ""))[-MAX_SUMMARY_CHARS:]
    state["recent_turns"] = [
        cleaned
        for entry in list(value.get("recent_turns") or [])[-MAX_RECENT_ENTRIES:]
        if (cleaned := _clean_entry(entry)) is not None
    ]
    state["recent_tool_results"] = [
        cleaned
        for entry in list(value.get("recent_tool_results") or [])[-MAX_TOOL_RESULTS:]
        if (cleaned := _clean_entry(entry, tool=True)) is not None
    ]
    state["metadata"] = {
        "created_at": str(metadata.get("created_at") or state["metadata"]["created_at"]),
        "updated_at": str(metadata.get("updated_at") or state["metadata"]["updated_at"]),
        "last_activity_at": metadata.get("last_activity_at"),
    }
    return state


class ConversationStore:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path is not None else default_store_path()
        self._load_failed = False

    def load(self) -> dict[str, Any]:
        with _LOCK:
            if not self.path.exists():
                self._load_failed = False
                return empty_state()
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
                    raise ValueError("unsupported conversation store schema")
                state = normalize_state(raw)
                self._load_failed = False
                return state
            except (OSError, ValueError, TypeError):
                # Never delete or overwrite unreadable state during startup.
                self._load_failed = True
                return empty_state()

    def save(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._save(state, replace_unreadable=False)

    def _save(
        self,
        state: dict[str, Any],
        *,
        replace_unreadable: bool,
    ) -> dict[str, Any]:
        if self._load_failed and not replace_unreadable:
            raise ValueError("refusing to overwrite unreadable conversation store")
        normalized = normalize_state(state)
        normalized["metadata"]["updated_at"] = _utc_now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(normalized, ensure_ascii=False, indent=2)
        with _LOCK:
            temp_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self.path.parent,
                    prefix=f".{self.path.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                    temp_path = Path(handle.name)
                os.replace(temp_path, self.path)
            finally:
                if temp_path is not None and temp_path.exists():
                    temp_path.unlink(missing_ok=True)
        self._load_failed = False
        return normalized

    def new_conversation(self) -> dict[str, Any]:
        # This is the sole explicit authorization to replace unreadable or old
        # durable continuity with a fresh logical conversation.
        return self._save(empty_state(), replace_unreadable=True)


def append_turn(state: dict[str, Any], role: str, text: str) -> dict[str, Any]:
    return upsert_turn(state, role, text)


def upsert_turn(
    state: dict[str, Any],
    role: str,
    text: str,
    *,
    turn_id: str | None = None,
) -> dict[str, Any]:
    state = normalize_state(state)
    cleaned = _clean_entry(
        {
            "role": role,
            "text": text,
            "timestamp": _utc_now(),
            "turn_id": turn_id,
        }
    )
    if cleaned is None:
        return state
    turns = state["recent_turns"]
    existing = next(
        (
            entry
            for entry in reversed(turns)
            if turn_id
            and entry.get("turn_id") == turn_id
            and entry.get("role") == cleaned["role"]
        ),
        None,
    )
    if existing is not None:
        existing.update(cleaned)
    else:
        turns.append(cleaned)
    while len(turns) > MAX_RECENT_ENTRIES:
        older = turns.pop(0)
        label = "User" if older["role"] == "user" else "Jarvis"
        folded = f"{label}: {older['text']}"
        state["summary"] = "\n".join(part for part in (state["summary"], folded) if part)[-MAX_SUMMARY_CHARS:]
    state["metadata"]["last_activity_at"] = cleaned["timestamp"]
    return state


def append_tool_result(state: dict[str, Any], tool: str, summary: str) -> dict[str, Any]:
    state = normalize_state(state)
    cleaned = _clean_entry(
        {"tool": tool, "summary": summary, "timestamp": _utc_now()},
        tool=True,
    )
    if cleaned is not None:
        state["recent_tool_results"].append(cleaned)
        state["recent_tool_results"] = state["recent_tool_results"][-MAX_TOOL_RESULTS:]
        state["metadata"]["last_activity_at"] = cleaned["timestamp"]
    return state
