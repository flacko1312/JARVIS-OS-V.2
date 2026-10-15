"""Safe, verifiable top-level window targeting for Windows."""

from __future__ import annotations

import ctypes
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ctypes import wintypes


WM_CLOSE = 0x0010


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    class_name: str
    process_id: int
    process_name: str


@dataclass(frozen=True)
class AppIdentity:
    key: str
    display_name: str
    aliases: frozenset[str]
    processes: frozenset[str]
    classes: frozenset[str] = frozenset()


def _normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value).casefold())
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_accents).split())


def _identity(
    key: str,
    display_name: str,
    aliases: tuple[str, ...],
    processes: tuple[str, ...],
    classes: tuple[str, ...] = (),
) -> AppIdentity:
    return AppIdentity(
        key=key,
        display_name=display_name,
        aliases=frozenset(_normalized(item) for item in aliases),
        processes=frozenset(item.casefold() for item in processes),
        classes=frozenset(item.casefold() for item in classes),
    )


_APP_IDENTITIES = (
    _identity(
        "notepad",
        "Bloc de notas",
        ("notepad", "bloc de notas", "bloc notas"),
        ("notepad.exe",),
        ("notepad",),
    ),
    _identity("spotify", "Spotify", ("spotify",), ("spotify.exe",)),
    _identity("chrome", "Chrome", ("chrome", "google chrome"), ("chrome.exe",)),
    _identity("edge", "Microsoft Edge", ("edge", "microsoft edge"), ("msedge.exe",)),
    _identity("firefox", "Firefox", ("firefox",), ("firefox.exe",)),
)

_PROTECTED_ALIASES = frozenset(("jarvis", "aurora"))
_PROTECTED_PROCESSES = frozenset(("jarvis.exe", "aurora.exe"))


def extract_named_target(value: str) -> str:
    """Remove common close-command framing while preserving the requested app name."""
    target = str(value or "").strip().strip(" .!?¿¡\"'")
    patterns = (
        r"^(?:cierra|cerrar)\s+(?:la\s+ventana\s+(?:de|del)\s+|el\s+|la\s+)?",
        r"^(?:close|quit)\s+(?:the\s+)?(?:window\s+(?:for|of)\s+)?",
    )
    for pattern in patterns:
        updated = re.sub(pattern, "", target, flags=re.IGNORECASE).strip()
        if updated != target:
            return updated.strip(" .!?¿¡\"'")
    return target


def _resolve_identity(requested: str) -> AppIdentity | None:
    key = _normalized(requested)
    for identity in _APP_IDENTITIES:
        if key in identity.aliases:
            return identity
    return None


def _window_process_name(process_id: int) -> str:
    kernel32 = ctypes.windll.kernel32
    process_query_limited_information = 0x1000
    handle = kernel32.OpenProcess(process_query_limited_information, False, process_id)
    if not handle:
        return ""
    try:
        capacity = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(capacity.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(capacity)):
            return ""
        return Path(buffer.value).name
    finally:
        kernel32.CloseHandle(handle)


def enumerate_windows() -> list[WindowInfo]:
    """Return visible, titled top-level windows and their owning process identity."""
    user32 = ctypes.windll.user32
    windows: list[WindowInfo] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def collect(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        title_length = user32.GetWindowTextLengthW(hwnd)
        if title_length <= 0:
            return True
        title_buffer = ctypes.create_unicode_buffer(title_length + 1)
        user32.GetWindowTextW(hwnd, title_buffer, title_length + 1)
        class_buffer = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_buffer, len(class_buffer))
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        windows.append(WindowInfo(
            hwnd=int(hwnd),
            title=title_buffer.value,
            class_name=class_buffer.value,
            process_id=int(process_id.value),
            process_name=_window_process_name(int(process_id.value)),
        ))
        return True

    callback = callback_type(collect)
    user32.EnumWindows(callback, 0)
    return windows


def _is_protected_window(window: WindowInfo) -> bool:
    title = _normalized(window.title)
    process = window.process_name.casefold()
    return (
        process in _PROTECTED_PROCESSES
        or title in _PROTECTED_ALIASES
        or (
            process in {"python.exe", "pythonw.exe"}
            and any(alias in title.split() for alias in _PROTECTED_ALIASES)
        )
    )


def _matches(window: WindowInfo, requested: str, identity: AppIdentity | None) -> bool:
    process = window.process_name.casefold()
    class_name = window.class_name.casefold()
    title = _normalized(window.title)
    if identity:
        if process in identity.processes or class_name in identity.classes:
            return True
        # Title matching is only a fallback when process identity was unavailable;
        # browser document titles must never impersonate another application.
        return not process and any(alias and alias in title for alias in identity.aliases)
    generic = _normalized(requested)
    process_stem = _normalized(Path(process).stem)
    return bool(generic and (generic == process_stem or generic in title))


def matching_windows(requested: str, windows: list[WindowInfo]) -> tuple[str, list[WindowInfo]]:
    identity = _resolve_identity(requested)
    display_name = identity.display_name if identity else requested.strip()
    matches = [window for window in windows if _matches(window, requested, identity)]
    return display_name, matches


def _post_close(hwnd: int) -> bool:
    return bool(ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0))


def _window_exists(hwnd: int) -> bool:
    return bool(ctypes.windll.user32.IsWindow(hwnd))


def _foreground_window() -> int:
    return int(ctypes.windll.user32.GetForegroundWindow() or 0)


def close_named_window(
    requested: str,
    *,
    timeout_seconds: float = 2.0,
    poll_interval: float = 0.05,
    enumerate_fn: Callable[[], list[WindowInfo]] = enumerate_windows,
    post_close_fn: Callable[[int], bool] = _post_close,
    exists_fn: Callable[[int], bool] = _window_exists,
    foreground_fn: Callable[[], int] = _foreground_window,
) -> str:
    """Close exactly one intended window and report success only after it disappears."""
    requested = extract_named_target(requested)
    normalized_request = _normalized(requested)
    if normalized_request in _PROTECTED_ALIASES:
        return "No puedo cerrar la ventana protegida de JARVIS."

    windows = enumerate_fn()
    if requested:
        display_name, matches = matching_windows(requested, windows)
    else:
        foreground = foreground_fn()
        matches = [window for window in windows if window.hwnd == foreground]
        display_name = matches[0].title if matches else "la ventana activa"

    if not matches:
        return f"No hay ninguna ventana abierta de {display_name or 'esa aplicación'}."
    if any(_is_protected_window(window) for window in matches):
        return "No puedo cerrar la ventana protegida de JARVIS."
    if len(matches) > 1:
        return (
            f"Hay varias ventanas que coinciden con {display_name}. "
            "Indica cuál quieres cerrar."
        )

    target = matches[0]
    if not post_close_fn(target.hwnd):
        return f"No he podido cerrar {display_name}."

    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while exists_fn(target.hwnd) and time.monotonic() < deadline:
        time.sleep(max(0.0, poll_interval))

    if exists_fn(target.hwnd):
        return f"No he podido cerrar {display_name}."

    remaining_name, remaining = matching_windows(requested, enumerate_fn()) if requested else (display_name, [])
    if remaining:
        return f"No he podido cerrar {remaining_name}: sigue abierta otra ventana coincidente."
    return f"Cerrado: {display_name}."
