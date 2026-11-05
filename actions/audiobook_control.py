"""C30 — Internet audiobook streaming via LibriVox public API.

Searches public-domain audiobooks, lists chapters, and streams them
through ffplay (or os.startfile fallback). No API key required.
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

# ---------------------------------------------------------------------------
# Module-level playback state

_CURRENT_PROC: Optional[subprocess.Popen] = None
_CURRENT_TITLE: str = ""
_CURRENT_URL: str = ""
_LOCK = threading.Lock()

_SYSTEM = platform.system()

# LibriVox catalog API (JSON feed, no key required)
_LIBRIVOX_API = "https://librivox.org/api/feed/audiobooks/"

# ---------------------------------------------------------------------------
# Internal helpers


def _http_get(url: str, timeout: int = 10) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "JARVIS-AURORA/1.0 (audiobook_control)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _search_books(query: str, limit: int = 5) -> list[dict]:
    """Search LibriVox by title (falls back to author if no results)."""
    encoded = urllib.parse.quote(query)
    url = f"{_LIBRIVOX_API}?title={encoded}&format=json&extended=1&limit={limit}"
    data = json.loads(_http_get(url).decode("utf-8", errors="replace"))
    books = data.get("books", []) or []
    if not books:
        # retry by author
        url2 = f"{_LIBRIVOX_API}?author={encoded}&format=json&extended=1&limit={limit}"
        data2 = json.loads(_http_get(url2).decode("utf-8", errors="replace"))
        books = data2.get("books", []) or []
    return books if isinstance(books, list) else []


def _get_chapters(book_id: str) -> list[dict]:
    """Return chapter list for a LibriVox book id."""
    url = f"https://librivox.org/api/feed/audiotracks/?extended=1&project_id={book_id}&format=json"
    data = json.loads(_http_get(url).decode("utf-8", errors="replace"))
    return data.get("sections", []) or []


def _find_ffplay() -> Optional[str]:
    for candidate in ["ffplay",
                       r"C:\ffmpeg\bin\ffplay.exe",
                       r"C:\Program Files\ffmpeg\bin\ffplay.exe",
                       r"C:\Tools\ffmpeg\bin\ffplay.exe"]:
        try:
            subprocess.run([candidate, "-version"],
                           capture_output=True, check=True, timeout=3)
            return candidate
        except Exception:
            pass
    return None


def _play_audio(url: str, title: str) -> str:
    global _CURRENT_PROC, _CURRENT_TITLE, _CURRENT_URL
    ffplay = _find_ffplay()
    with _LOCK:
        if _CURRENT_PROC is not None:
            try:
                _CURRENT_PROC.terminate()
            except Exception:
                pass
        _CURRENT_PROC = None
        _CURRENT_TITLE = ""
        _CURRENT_URL = ""

    if ffplay:
        try:
            proc = subprocess.Popen(
                [ffplay, "-nodisp", "-loglevel", "quiet", "-autoexit", "-i", url],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            with _LOCK:
                _CURRENT_PROC = proc
                _CURRENT_TITLE = title
                _CURRENT_URL = url
            return f"Reproduciendo '{title}'."
        except Exception:
            pass

    # Fallback: OS media player
    try:
        if _SYSTEM == "Windows":
            os.startfile(url)  # type: ignore[attr-defined]
        elif _SYSTEM == "Darwin":
            subprocess.Popen(["open", url])
        else:
            subprocess.Popen(["xdg-open", url])
        with _LOCK:
            _CURRENT_PROC = None
            _CURRENT_TITLE = title
            _CURRENT_URL = url
        return f"Abriendo '{title}' en el reproductor del sistema."
    except Exception as exc:
        return f"No se pudo reproducir '{title}': {exc}"


def _fmt_book(book: dict) -> str:
    title = book.get("title", "?")
    authors = book.get("authors", [])
    author_str = ", ".join(a.get("last_name", "") + ", " + a.get("first_name", "")
                           for a in authors if isinstance(a, dict)) or "Autor desconocido"
    sections = book.get("num_sections", "?")
    lang = book.get("language", "?")
    return f"• {title} — {author_str} [{lang}, {sections} capítulos]"


# ---------------------------------------------------------------------------
# Actions


def _action_search(query: str) -> str:
    if not query.strip():
        return "Especifica el título o autor del audiolibro que buscas."
    try:
        books = _search_books(query.strip())
    except Exception as exc:
        return f"Error buscando audiolibros: {exc}"
    if not books:
        return f"No encontré audiolibros para '{query}' en LibriVox."
    lines = [f"Audiolibros encontrados para '{query}':"]
    for b in books:
        lines.append(_fmt_book(b))
        lines.append(f"  ID: {b.get('id', '?')}  |  {b.get('url_librivox', '')}")
    return "\n".join(lines)


def _action_chapters(query: str = "", book_id: str = "") -> str:
    if not query.strip() and not book_id.strip():
        return "Especifica el título o el ID del audiolibro."
    if not book_id.strip():
        try:
            books = _search_books(query.strip(), limit=1)
        except Exception as exc:
            return f"Error buscando audiolibros: {exc}"
        if not books:
            return f"No encontré '{query}' en LibriVox."
        book_id = str(books[0].get("id", ""))
        title = books[0].get("title", query)
    else:
        title = f"libro {book_id}"

    try:
        chapters = _get_chapters(book_id)
    except Exception as exc:
        return f"Error obteniendo capítulos: {exc}"
    if not chapters:
        return "No encontré capítulos descargables para ese audiolibro."

    lines = [f"Capítulos de '{title}':"]
    for ch in chapters[:10]:
        num = ch.get("section_number", "?")
        name = ch.get("title", f"Capítulo {num}")
        dur = ch.get("playtime", "")
        url = ch.get("listen_url", "")
        lines.append(f"  {num}. {name} ({dur})  — {url}")
    if len(chapters) > 10:
        lines.append(f"  ... y {len(chapters) - 10} capítulos más.")
    return "\n".join(lines)


def _action_play(query: str = "", book_id: str = "", chapter: int = 1,
                 chapter_url: str = "") -> str:
    if chapter_url.strip():
        title = f"capítulo (URL directa)"
        return _play_audio(chapter_url.strip(), title)

    if not query.strip() and not book_id.strip():
        return "Especifica el título o el ID del audiolibro."

    if not book_id.strip():
        try:
            books = _search_books(query.strip(), limit=1)
        except Exception as exc:
            return f"Error buscando audiolibros: {exc}"
        if not books:
            return f"No encontré '{query}' en LibriVox."
        book_id = str(books[0].get("id", ""))
        query = books[0].get("title", query)

    try:
        chapters = _get_chapters(book_id)
    except Exception as exc:
        return f"Error obteniendo capítulos: {exc}"
    if not chapters:
        return "No encontré capítulos descargables."

    # Find by chapter number (1-indexed)
    chapter_idx = max(0, int(chapter) - 1)
    if chapter_idx >= len(chapters):
        chapter_idx = 0
    ch = chapters[chapter_idx]
    url = ch.get("listen_url", "")
    if not url:
        return "El capítulo no tiene URL de audio descargable."
    title = f"{query} — {ch.get('title', f'Capítulo {chapter}')}"
    return _play_audio(url, title)


def _action_stop() -> str:
    global _CURRENT_PROC, _CURRENT_TITLE, _CURRENT_URL
    with _LOCK:
        if _CURRENT_PROC is None and not _CURRENT_TITLE:
            return "No hay ningún audiolibro reproduciéndose."
        name = _CURRENT_TITLE or "audiolibro"
        if _CURRENT_PROC is not None:
            try:
                _CURRENT_PROC.terminate()
            except Exception:
                pass
        _CURRENT_PROC = None
        _CURRENT_TITLE = ""
        _CURRENT_URL = ""
    return f"Reproducción de '{name}' detenida."


def _action_status() -> str:
    with _LOCK:
        if _CURRENT_PROC is None and not _CURRENT_TITLE:
            return "No hay ningún audiolibro reproduciéndose actualmente."
        alive = _CURRENT_PROC is not None and _CURRENT_PROC.poll() is None
        state = "en reproducción" if alive else "finalizado"
        return f"Audiolibro {state}: '{_CURRENT_TITLE}'"


# ---------------------------------------------------------------------------
# Entry point


def audiobook_control(parameters=None, response=None, player=None, session_memory=None) -> str:
    """NEST 68 C30 — Audiobook search and playback via LibriVox."""
    if not parameters:
        return _action_status()

    action = str(parameters.get("action", "status")).strip().lower()
    query = str(parameters.get("query") or parameters.get("book") or "").strip()
    book_id = str(parameters.get("book_id") or "").strip()
    chapter = int(parameters.get("chapter") or 1)
    chapter_url = str(parameters.get("chapter_url") or "").strip()

    if action in ("search", "buscar", "find"):
        return _action_search(query)
    elif action in ("chapters", "capitulos", "capítulos", "list_chapters"):
        return _action_chapters(query=query, book_id=book_id)
    elif action in ("play", "reproducir", "escuchar"):
        return _action_play(query=query, book_id=book_id, chapter=chapter,
                            chapter_url=chapter_url)
    elif action in ("stop", "parar", "detener"):
        return _action_stop()
    elif action == "status":
        return _action_status()
    else:
        return f"Acción '{action}' no reconocida. Usa: search, chapters, play, stop, status."
