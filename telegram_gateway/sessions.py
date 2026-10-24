from __future__ import annotations

import json
import os
import uuid
from pathlib import Path


class SessionStore:
    """Persist only chat-to-JARVIS session identity, never conversation content."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    def _load(self) -> dict[str, str]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def for_chat(self, chat_id: int) -> str:
        sessions = self._load()
        key = str(chat_id)
        if key not in sessions:
            sessions[key] = f"telegram:{chat_id}:{uuid.uuid4().hex}"
            self._save(sessions)
        return sessions[key]

    def _save(self, sessions: dict[str, str]) -> None:
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(sessions, sort_keys=True), encoding="utf-8")
        os.chmod(temp, 0o600)
        os.replace(temp, self.path)


class OffsetStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    def load(self) -> int:
        try:
            return max(0, int(self.path.read_text(encoding="ascii").strip()))
        except (OSError, ValueError):
            return 0

    def save(self, offset: int) -> None:
        temp = self.path.with_suffix(".tmp")
        temp.write_text(str(max(0, int(offset))), encoding="ascii")
        os.chmod(temp, 0o600)
        os.replace(temp, self.path)
