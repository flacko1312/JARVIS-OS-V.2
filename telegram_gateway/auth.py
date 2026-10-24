from __future__ import annotations


class ChatAuthorizer:
    def __init__(self, allowed_chat_ids: frozenset[int]):
        self._allowed = allowed_chat_ids

    def is_allowed(self, chat_id: object) -> bool:
        if isinstance(chat_id, bool):
            return False
        try:
            numeric = int(chat_id)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
        return numeric in self._allowed
