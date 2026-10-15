"""Containment and optional local Git operations for development workspaces."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


def contained_path(root: Path, relative: str) -> Path:
    root = root.resolve()
    candidate = (root / str(relative)).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Path escapes the approved project root.")
    return candidate


def git_operation(project_root: Path, action: str, *, branch: str = "", message: str = "", timeout: int = 20) -> str:
    root = project_root.resolve()
    if not (root / ".git").exists():
        return "The approved project root is not a Git repository."
    commands = {
        "status": ["git", "status", "--short", "--branch"],
        "diff": ["git", "diff", "--"],
        "branch": ["git", "branch", "--show-current"],
    }
    if action == "create_branch":
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,80}", branch) or ".." in branch:
            return "Invalid local branch name."
        command = ["git", "switch", "-c", branch]
    elif action == "commit":
        if not message.strip():
            return "A commit message is required."
        command = ["git", "commit", "-m", message.strip()[:200]]
    elif action in commands:
        command = commands[action]
    else:
        return "Unsupported Git action. Allowed: status, diff, branch, create_branch, commit."
    try:
        result = subprocess.run(
            command, cwd=str(root), capture_output=True, text=True,
            timeout=max(1, min(int(timeout), 60)), check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"Git action failed safely: {type(exc).__name__}."
    output = (result.stdout or result.stderr or "").strip()
    return output if result.returncode == 0 else f"Git action failed ({result.returncode}): {output}"
