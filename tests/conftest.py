"""Global pytest isolation for process-level JARVIS state."""

from __future__ import annotations

from pathlib import Path
import os

import pytest

from api import status as api_status


@pytest.fixture(autouse=True, scope="session")
def isolate_runtime_status(tmp_path_factory: pytest.TempPathFactory):
    """Keep simulated Live sessions from overwriting the running app status."""

    original_path = api_status.STATUS_PATH
    api_status.STATUS_PATH = Path(tmp_path_factory.mktemp("runtime-status")) / "status.json"
    try:
        yield
    finally:
        api_status.STATUS_PATH = original_path


@pytest.fixture(autouse=True, scope="session")
def isolate_reminder_registry(tmp_path_factory: pytest.TempPathFactory):
    """Prevent reminder tests from writing into the user's real scheduler registry."""
    original = os.environ.get("JARVIS_REMINDER_DIR")
    os.environ["JARVIS_REMINDER_DIR"] = str(tmp_path_factory.mktemp("reminders"))
    try:
        yield
    finally:
        if original is None:
            os.environ.pop("JARVIS_REMINDER_DIR", None)
        else:
            os.environ["JARVIS_REMINDER_DIR"] = original


def _has_display() -> bool:
    """Check if a working X11/Wayland display is available."""
    import os
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return False
    return True


collect_ignore_glob = []
if not _has_display():
    collect_ignore_glob.extend([
        "test_action_helpers.py",
        "test_core_resilience.py",
        "test_phy2_009_named_window_close.py",
        "test_phy2_010_windows_focus_stability.py",
        "test_phy2_010_windows_safe_text_entry.py",
    ])
