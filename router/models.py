"""Modelos del Router de JARVIS."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Domain(Enum):
    WINDOWS = "windows"
    FILES = "files"
    VISION = "vision"
    MEMORY = "memory"
    HOME = "home"
    DEVELOPMENT = "development"
    KNOWLEDGE = "knowledge"
    LOCAL_AI = "local_ai"
    WEB = "web"
    CONVERSATION = "conversation"


_REQUIRES_LILITH = frozenset({Domain.MEMORY, Domain.HOME, Domain.LOCAL_AI})


@dataclass
class RouteResult:
    domain: Domain
    handler: str
    confidence: float
    params: dict = field(default_factory=dict)

    @property
    def requires_lilith(self) -> bool:
        return self.domain in _REQUIRES_LILITH
