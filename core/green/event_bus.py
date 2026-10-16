"""Event Bus — lightweight in-process event decoupling for JARVIS.

Reports events for observability; does NOT authorize execution.
Subscriber exceptions are isolated: a failing handler never crashes core
JARVIS operations.

JARVIS remains fully functional when the event bus is disabled.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger("jarvis.green.events")

EVENT_BUS_ENABLED = os.environ.get("JARVIS_EVENT_BUS_ENABLED", "0") == "1"


class EventType(Enum):
    TURN_STARTED = "turn_started"
    TURN_COMPLETED = "turn_completed"

    ROUTING_DECIDED = "routing_decided"

    TOOL_REQUESTED = "tool_requested"
    TOOL_AUTHORIZED = "tool_authorized"
    TOOL_REJECTED = "tool_rejected"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"

    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"

    LILITH_REQUESTED = "lilith_requested"
    LILITH_COMPLETED = "lilith_completed"
    LILITH_FAILED = "lilith_failed"

    TRACE_COMPLETED = "trace_completed"


@dataclass
class Event:
    """A structured event with typed payload."""

    event_type: EventType
    timestamp: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)
    source: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, EventType):
            raise TypeError(f"event_type must be EventType, got {type(self.event_type)}")


EventHandler = Callable[[Event], None]


class EventBus:
    """In-process publish/subscribe event bus.

    Handlers are called synchronously in subscription order.
    A handler exception is logged and suppressed — it never disrupts
    the emitting code path.
    """

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = {}

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        handlers = self._handlers[event_type]
        if handler in handlers:
            return  # duplicate subscription ignored
        handlers.append(handler)
        logger.debug("subscribed to %s: %s", event_type.value, handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        handlers = self._handlers.get(event_type, [])
        try:
            handlers.remove(handler)
        except ValueError:
            pass

    def emit(self, event: Event) -> None:
        if not EVENT_BUS_ENABLED:
            return
        handlers = self._handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                logger.exception(
                    "event handler %s failed for %s — isolated, core unaffected",
                    handler,
                    event.event_type.value,
                )

    def handler_count(self, event_type: EventType) -> int:
        return len(self._handlers.get(event_type, []))

    def clear(self) -> None:
        self._handlers.clear()
