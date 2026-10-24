from __future__ import annotations


TELEGRAM_TEXT_LIMIT = 4096
SAFE_CHUNK_SIZE = 3900


def split_message(text: str, limit: int = SAFE_CHUNK_SIZE) -> list[str]:
    """Split plain text at paragraph/line/word boundaries without dropping content."""
    remaining = str(text or "").strip()
    if not remaining:
        return ["No he podido generar una respuesta."]
    chunks: list[str] = []
    while len(remaining) > limit:
        window = remaining[: limit + 1]
        split_at = window.rfind("\n\n")
        if split_at < limit // 3:
            split_at = window.rfind("\n")
        if split_at < limit // 3:
            split_at = window.rfind(" ")
        if split_at <= 0:
            split_at = limit
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks
