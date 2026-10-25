"""AURORA runtime-state policy for the particle canvas.

Kept outside the renderer so product state mapping can change without touching
OpenGL, shaders or the morph engine.
"""
from __future__ import annotations


STATE_SHAPE_MAP = {
    "STANDBY": "core",
    "IDLE": "core",
    "INITIALISING": "core",
    "CONNECTING": "core",
    "RECONNECTING": "core",
    "LISTENING": "core",
    "ESCUCHANDO": "core",
    "THINKING": "brain",
    "PROCESSING": "brain",
    "PENSANDO": "brain",
    "SPEAKING": "vortex",
    "HABLANDO": "vortex",
}


def shape_for_state(state: str) -> str | None:
    return STATE_SHAPE_MAP.get(str(state or "").strip().upper())
