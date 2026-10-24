from __future__ import annotations

import html
import re


TELEGRAM_TEXT_LIMIT = 4096
SAFE_CHUNK_SIZE = 3500

_INLINE_MARKUP = re.compile(r"\*\*(.+?)\*\*|`([^`\n]+)`")


def _format_prose_line(line: str) -> str:
    """Render a conservative Markdown subset as Telegram-safe HTML."""
    heading = re.match(r"^#{1,4}\s+(.+)$", line)
    if heading:
        return f"<b>{html.escape(heading.group(1))}</b>"
    if line.startswith("- "):
        line = "• " + line[2:]

    rendered: list[str] = []
    cursor = 0
    for match in _INLINE_MARKUP.finditer(line):
        rendered.append(html.escape(line[cursor : match.start()]))
        if match.group(1) is not None:
            rendered.append(f"<b>{html.escape(match.group(1))}</b>")
        else:
            rendered.append(f"<code>{html.escape(match.group(2) or '')}</code>")
        cursor = match.end()
    rendered.append(html.escape(line[cursor:]))
    return "".join(rendered)


def to_telegram_html(text: str) -> str:
    """Escape model output and retain only Telegram's safe, useful formatting."""
    output: list[str] = []
    code_lines: list[str] = []
    in_code = False
    for line in str(text).splitlines():
        if line.strip().startswith("```"):
            if in_code:
                output.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
                code_lines = []
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
        else:
            output.append(_format_prose_line(line))
    if in_code:
        # An unclosed fence must remain harmless and readable.
        output.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
    return "\n".join(output).strip()


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


def telegram_html_chunks(text: str) -> list[str]:
    """Return independently valid HTML chunks within Telegram's hard limit."""
    pending = split_message(text)
    rendered: list[str] = []
    while pending:
        raw = pending.pop(0)
        formatted = to_telegram_html(raw) or "No he podido generar una respuesta."
        if len(formatted) <= TELEGRAM_TEXT_LIMIT:
            rendered.append(formatted)
            continue
        if len(raw) <= 1:
            rendered.append(formatted[:TELEGRAM_TEXT_LIMIT])
            continue
        midpoint = len(raw) // 2
        boundary = raw.rfind("\n", 0, midpoint)
        if boundary < midpoint // 2:
            boundary = raw.rfind(" ", 0, midpoint)
        if boundary <= 0:
            boundary = midpoint
        pending[0:0] = [raw[:boundary].rstrip(), raw[boundary:].lstrip()]
    return rendered
