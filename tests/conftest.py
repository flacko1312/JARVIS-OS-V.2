"""Global pytest isolation for process-level JARVIS state."""

from __future__ import annotations

from pathlib import Path

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
