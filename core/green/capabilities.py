"""Capabilities — vocabulary for describing what tools, agents, and skills can do.

Capabilities are metadata; they do NOT replace existing JARVIS authority guards.
Initially used for validation, documentation, and safety information.
Unknown capabilities are rejected during registration.
"""
from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger("jarvis.green.capabilities")


class Capability(Enum):
    # Filesystem
    FILESYSTEM_READ = "filesystem.read"
    FILESYSTEM_WRITE = "filesystem.write"

    # Browser
    BROWSER_READ = "browser.read"
    BROWSER_INTERACT = "browser.interact"

    # Windows
    WINDOWS_APPS = "windows.apps"
    WINDOWS_KEYBOARD = "windows.keyboard"
    WINDOWS_MOUSE = "windows.mouse"

    # Vision
    VISION_SCREEN = "vision.screen"
    VISION_CAMERA = "vision.camera"

    # Memory
    MEMORY_READ = "memory.read"
    MEMORY_WRITE = "memory.write"

    # Home
    HOME_READ = "home.read"
    HOME_CONTROL = "home.control"

    # Development
    DEVELOPMENT_READ = "development.read"
    DEVELOPMENT_WRITE = "development.write"
    DEVELOPMENT_EXECUTE = "development.execute"

    # Network
    NETWORK_READ = "network.read"
    NETWORK_WRITE = "network.write"

    # System
    SYSTEM_READ = "system.read"
    SYSTEM_MODIFY = "system.modify"

    # Multimedia
    MULTIMEDIA_PLAY = "multimedia.play"
    MULTIMEDIA_CONTROL = "multimedia.control"

    # Communication
    COMMUNICATION_READ = "communication.read"
    COMMUNICATION_SEND = "communication.send"


# Set of all valid capability strings for fast lookup
VALID_CAPABILITIES = frozenset(c.value for c in Capability)


class CapabilityError(Exception):
    pass


def validate_capability(cap: str) -> Capability:
    """Validate and return a Capability enum from a string.

    Raises CapabilityError for unknown capabilities — fail-closed.
    """
    if cap not in VALID_CAPABILITIES:
        raise CapabilityError(f"unknown capability: {cap!r}")
    return Capability(cap)


def validate_capabilities(caps: list[str]) -> list[Capability]:
    """Validate a list of capability strings. Raises on first invalid one."""
    return [validate_capability(c) for c in caps]


class CapabilitySet:
    """A validated set of capabilities for a tool, agent, or skill."""

    def __init__(self, capabilities: list[str] | None = None) -> None:
        self._caps: set[Capability] = set()
        if capabilities:
            for c in capabilities:
                self.add(c)

    def add(self, cap: str) -> None:
        self._caps.add(validate_capability(cap))

    def remove(self, cap: str) -> None:
        self._caps.discard(Capability(cap))

    def has(self, cap: str) -> bool:
        try:
            return Capability(cap) in self._caps
        except ValueError:
            return False

    def has_all(self, caps: list[str]) -> bool:
        return all(self.has(c) for c in caps)

    def has_any(self, caps: list[str]) -> bool:
        return any(self.has(c) for c in caps)

    def satisfies(self, required: CapabilitySet) -> bool:
        """Check if this set satisfies all required capabilities."""
        return required._caps.issubset(self._caps)

    def to_list(self) -> list[str]:
        return sorted(c.value for c in self._caps)

    def __len__(self) -> int:
        return len(self._caps)

    def __contains__(self, cap: str) -> bool:
        return self.has(cap)

    def __repr__(self) -> str:
        return f"CapabilitySet({self.to_list()})"
