from __future__ import annotations

import math
import logging
from collections import deque
import time
from typing import Callable

import numpy as np
from PyQt6 import sip
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen, QVector3D
from PyQt6.QtOpenGL import (
    QOpenGLBuffer, QOpenGLShader, QOpenGLShaderProgram,
    QOpenGLVersionFunctionsFactory, QOpenGLVersionProfile,
)
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import QSizePolicy

from .audio import AudioAnalyzer
from .controller import MorphController
from .quality import QualityManager
from .shapes import SHAPE_FACTORIES, accent_mask
from .state_mapping import shape_for_state

logger = logging.getLogger("jarvis.aurora_particles")

GL_COLOR_BUFFER_BIT = 0x00004000
GL_DEPTH_BUFFER_BIT = 0x00000100
GL_FLOAT = 0x1406
GL_POINTS = 0x0000
GL_BLEND = 0x0BE2
GL_SRC_ALPHA = 0x0302
GL_ONE = 1
GL_PROGRAM_POINT_SIZE = 0x8642
GL_POINT_SPRITE = 0x8861

VERTEX_SHADER = """
#version 120
attribute vec3 aSource;
attribute vec3 aTarget;
attribute float aSeed;
attribute float aAccentSource;
attribute float aAccentTarget;
uniform float uTime, uProgress, uDissolve, uBass, uMid, uTreble, uError;
uniform float uPointSize, uTurbulence, uAspect, uIntensity;
varying float vEnergy;
varying float vAccent;
mat3 rotY(float a){float c=cos(a),s=sin(a);return mat3(c,0.,-s, 0.,1.,0., s,0.,c);}
void main(){
  float e=uProgress*uProgress*(3.0-2.0*uProgress);
  vec3 p=mix(aSource,aTarget,e);
  vec3 dir=normalize(p+vec3(sin(aSeed*91.7),cos(aSeed*47.3),sin(aSeed*23.1))*.18);
  float wave=sin(uTime*1.7+aSeed*38.0+p.y*8.0);
  p += dir*uDissolve*(.18+.24*sin(aSeed*71.0))*uTurbulence;
  p += dir*(.012+.060*uBass)*sin(uTime*1.3+aSeed*12.0);
  p += vec3(0., wave*(.008+.035*uMid), 0.);
  p += uError*vec3(sin(aSeed*83.0+uTime*13.0), cos(aSeed*61.0+uTime*11.0), 0.)*.022;
  p = rotY(uTime*.09)*p;
  p = p*.84 + vec3(0., .07, 0.); // reserve a clear lower HUD status band
  p.x/=max(.55,uAspect);
  gl_Position=vec4(p.xy, p.z*.25, 1.0);
  vAccent=mix(aAccentSource,aAccentTarget,e);
  gl_PointSize=uPointSize*min(1.65,1.0+uBass*.18+uTreble*.55+uDissolve*.18+vAccent*.10);
  vEnergy=clamp(.48+uIntensity*.42+uTreble*.50+wave*.10+uError*.18,0.,1.);
}
"""

FRAGMENT_SHADER = """
#version 120
uniform vec3 uColorA, uColorB;
uniform vec3 uAccentColor;
varying float vEnergy;
varying float vAccent;
void main(){
  vec2 q=gl_PointCoord-vec2(.5);
  float d=dot(q,q);
  if(d>.25) discard;
  float alpha=smoothstep(.25,.01,d)*(.25+vEnergy*.35);
  vec3 base=mix(uColorA,uColorB,vEnergy);
  vec3 c=mix(base,uAccentColor,clamp(vAccent*.72,0.,1.));
  c*=1.0+vAccent*.10;
  gl_FragColor=vec4(c,alpha);
}
"""


class ParticleMorphingCanvas(QOpenGLWidget):
    """AURORA's isolated GPU point-cloud core with a safe raster fallback."""

    _STATE_LABELS = {"INITIALISING": "INITIALISING", "LISTENING": "ESCUCHANDO",
                     "THINKING": "PENSANDO", "PROCESSING": "PENSANDO",
                     "SPEAKING": "HABLANDO", "MUTED": "MIC OFF"}

    def __init__(self, face_path: str = "", parent=None, config=None,
                 palette_provider: Callable[[], tuple[str, str]] | None = None):
        super().__init__(parent)
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.state = "INITIALISING"
        self.logical_state = "INITIALISING"
        self.speaking = False
        self.muted = False
        self.executing = False
        self._error_until = 0.0
        self._palette_provider = palette_provider
        self._quality = QualityManager((config or {}).get("graphics_quality", "medium") if isinstance(config, dict) else "medium")
        self._morph = MorphController()
        self._visual_queue: deque[tuple[str, str]] = deque()
        self._visual_hold_until = 0.0
        self._brain_min_hold = .45
        self._audio = AudioAnalyzer()
        self._in_level = self._out_level = 0.0
        self._shapes: dict[str, np.ndarray] = {}
        self._source = self._target = np.empty((0, 3), dtype=np.float32)
        self._source_accent = self._target_accent = np.empty(0, dtype=np.float32)
        self._seeds = np.empty(0, dtype=np.float32)
        self._program: QOpenGLShaderProgram | None = None
        self._vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self._gl = None
        self._gpu_ready = False
        self._gl_error = ""
        self._pending_upload = True
        self._last = time.perf_counter()
        self._time = 0.0
        self._load_shapes()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(self._quality.current.frame_ms)

    # Public engine API -------------------------------------------------
    def register_shape(self, name: str, positions) -> None:
        points = np.asarray(positions, dtype=np.float32).reshape(-1, 3)
        if len(points) != self._quality.current.particle_count:
            raise ValueError("shape particle count must match active quality")
        self._shapes[str(name)] = np.ascontiguousarray(points)

    registerShape = register_shape

    def morph_to(self, name: str) -> bool:
        if name not in self._shapes:
            raise KeyError(name)
        started = self._morph.request(name)
        if started:
            logger.info("PARTICLE_MORPH %s -> %s", self._morph.current_shape, name)
            self._source = self._shapes[self._morph.current_shape]
            self._target = self._shapes[name]
            self._source_accent = self._shape_accents[self._morph.current_shape]
            self._target_accent = self._shape_accents[name]
            self._pending_upload = True
        return started

    morphTo = morph_to

    def set_state(self, state: str) -> bool:
        normalized = str(state or "IDLE").strip().upper()
        self.logical_state = normalized
        self.speaking = normalized in ("SPEAKING", "HABLANDO")
        logger.info("PARTICLE_STATE logical %s", normalized)
        target = shape_for_state(normalized)
        if not target:
            self.state = normalized
            return False
        return self._enqueue_visual_state(normalized, target)

    def _enqueue_visual_state(self, state: str, shape: str) -> bool:
        if self._morph.state.value == "STABLE" and not self._visual_queue and time.perf_counter() >= self._visual_hold_until:
            if shape == self._morph.current_shape:
                self.state = state
                return False
            self.state = state
            return self.morph_to(shape)
        pending_shape = self._visual_queue[-1][1] if self._visual_queue else self._morph.target_shape
        if pending_shape == shape:
            if self._visual_queue:
                self._visual_queue[-1] = (state, shape)
            return False
        if len(self._visual_queue) >= 4:
            if len(self._visual_queue) > 1 and self._visual_queue[-2][1] == shape:
                self._visual_queue.pop()
            self._visual_queue[-1] = (state, shape)
        else:
            self._visual_queue.append((state, shape))
        logger.info("PARTICLE_VISUAL enqueue %s", shape)
        return False

    def _advance_visual_queue(self, now: float) -> None:
        if self._morph.state.value != "STABLE" or now < self._visual_hold_until or not self._visual_queue:
            return
        state, shape = self._visual_queue.popleft()
        self.state = state
        if shape != self._morph.current_shape:
            self.morph_to(shape)

    def force_dissolve(self) -> None:
        order = ("core", "brain", "vortex")
        self.morph_to(order[(order.index(self._morph.current_shape) + 1) % len(order)])

    def set_input_audio_level(self, level: float):
        # Microphone PCM is materially quieter than Gemini playback on the
        # validated hardware. Apply visual-only gain; logged/analyzed values and
        # the audio pipeline remain untouched.
        self._in_level = max(0., min(1., float(level) * 1.85))
    def set_output_audio_level(self, level: float): self._out_level = max(0., min(1., float(level)))
    def set_input_audio_spectrum(self, bass: float, mid: float, treble: float):
        self._audio.set_bands("input", (bass * 1.85, mid * 1.65, treble * 1.85))
    def set_output_audio_spectrum(self, bass: float, mid: float, treble: float): self._audio.set_bands("output", (bass, mid, treble))
    def set_executing(self, active: bool):
        self.executing = bool(active)
        if self.executing:
            self.morph_to("brain")
        else:
            target = shape_for_state(self.state)
            if target:
                self.morph_to(target)
    def flag_error(self, seconds: float = 6.0): self._error_until = time.time() + seconds

    def set_graphics_quality(self, quality: str):
        old = self._quality.current.name
        preset = self._quality.set(quality)
        self._timer.setInterval(preset.frame_ms)
        if preset.name != old:
            current, target = self._morph.current_shape, self._morph.target_shape
            self._load_shapes()
            self._morph = MorphController(current)
            if target != current:
                self.morph_to(target)
            self._pending_upload = True

    @property
    def renderer_status(self) -> dict:
        return {"gpu": self._gpu_ready, "error": self._gl_error,
                "quality": self._quality.current.name,
                "particles": self._quality.current.particle_count,
                "shape": self._morph.current_shape, "morph_state": self._morph.state.value}

    # Lifecycle ---------------------------------------------------------
    def _load_shapes(self):
        n = self._quality.current.particle_count
        self._shapes = {name: factory(n) for name, factory in SHAPE_FACTORIES.items()}
        self._shape_accents = {name: accent_mask(name, n) for name in self._shapes}
        current = self._morph.current_shape if hasattr(self, "_morph") else "core"
        self._source = self._target = self._shapes.get(current, self._shapes["core"])
        self._source_accent = self._target_accent = self._shape_accents.get(current, self._shape_accents["core"])
        self._seeds = np.random.default_rng(4409).random(n).astype(np.float32)

    def initializeGL(self):
        try:
            profile = QOpenGLVersionProfile()
            profile.setVersion(2, 0)
            self._gl = QOpenGLVersionFunctionsFactory.get(profile, self.context())
            if self._gl is None:
                raise RuntimeError("compatible OpenGL functions unavailable")
            self._gl.initializeOpenGLFunctions()
            program = QOpenGLShaderProgram(self)
            if not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, VERTEX_SHADER):
                raise RuntimeError(program.log())
            if not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, FRAGMENT_SHADER):
                raise RuntimeError(program.log())
            if not program.link():
                raise RuntimeError(program.log())
            self._program = program
            if not self._vbo.create():
                raise RuntimeError("VBO creation failed")
            self._gpu_ready = True
            self._upload()
        except Exception as exc:
            self._gpu_ready = False
            self._gl_error = f"{type(exc).__name__}: {exc}"[:240]

    def _upload(self):
        if not self._gpu_ready or not self._vbo.isCreated():
            return
        packed = np.column_stack((self._source, self._target, self._seeds,
                                  self._source_accent, self._target_accent)).astype(np.float32)
        self._vbo.bind()
        self._vbo.allocate(int(packed.nbytes))
        self._vbo.write(0, sip.voidptr(packed.ctypes.data), int(packed.nbytes))
        self._vbo.release()
        self._pending_upload = False

    def _step(self):
        now = time.perf_counter()
        dt = min(.1, max(.001, now - self._last))
        self._last = now
        self._time += dt
        completed = self._morph.update(dt)
        if completed:
            logger.info("PARTICLE_MORPH complete shape=%s", self._morph.current_shape)
            if self._morph.current_shape == "brain":
                self._visual_hold_until = now + self._brain_min_hold
        if completed and self._morph.state.value != "STABLE":
            self._source = self._shapes[self._morph.current_shape]
            self._target = self._shapes[self._morph.target_shape]
            self._source_accent = self._shape_accents[self._morph.current_shape]
            self._target_accent = self._shape_accents[self._morph.target_shape]
            self._pending_upload = True
        self._audio.decay(math.exp(-dt * 1.15))
        self._in_level *= math.exp(-dt * 2.0)
        self._out_level *= math.exp(-dt * 1.65)
        self._advance_visual_queue(now)
        self.update()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def showEvent(self, event):
        self._last = time.perf_counter()
        if not self._timer.isActive(): self._timer.start(self._quality.current.frame_ms)
        super().showEvent(event)

    def closeEvent(self, event):
        self._timer.stop()
        if self.context() and self._vbo.isCreated():
            self.makeCurrent(); self._vbo.destroy(); self.doneCurrent()
        super().closeEvent(event)

    # Rendering ---------------------------------------------------------
    def paintGL(self):
        if self._gpu_ready and self._program and self._gl:
            if self._pending_upload: self._upload()
            g = self._gl
            g.glClearColor(0., 0., 0., 0.)
            g.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            g.glEnable(GL_BLEND); g.glBlendFunc(GL_SRC_ALPHA, GL_ONE)
            g.glEnable(GL_PROGRAM_POINT_SIZE); g.glEnable(GL_POINT_SPRITE)
            p = self._program; p.bind(); self._vbo.bind()
            stride = 9 * 4
            for name, offset, size in (("aSource", 0, 3), ("aTarget", 12, 3), ("aSeed", 24, 1),
                                       ("aAccentSource", 28, 1), ("aAccentTarget", 32, 1)):
                loc = p.attributeLocation(name); p.enableAttributeArray(loc); p.setAttributeBuffer(loc, GL_FLOAT, offset, size, stride)
            bands = self._audio.output if self.logical_state == "SPEAKING" else self._audio.input
            p.setUniformValue("uTime", float(self._time)); p.setUniformValue("uProgress", float(self._morph.progress))
            p.setUniformValue("uDissolve", float(self._morph.dissolve)); p.setUniformValue("uBass", float(bands[0]))
            p.setUniformValue("uMid", float(bands[1])); p.setUniformValue("uTreble", float(bands[2]))
            error_active = time.time() < self._error_until
            p.setUniformValue("uError", 1.0 if error_active else 0.0)
            p.setUniformValue("uPointSize", self._quality.current.point_size); p.setUniformValue("uTurbulence", self._quality.current.turbulence)
            p.setUniformValue("uAspect", float(max(1, self.width()) / max(1, self.height())))
            state_energy = {
                "STANDBY": .12, "IDLE": .12, "LISTENING": .32,
                "THINKING": .58, "PROCESSING": .58, "SPEAKING": .48,
                "MUTED": .04,
            }.get(self.state, .24)
            active_level = self._out_level if self.speaking else self._in_level
            intensity = state_energy + (.30 if self.executing else 0.) + active_level * .85
            p.setUniformValue("uIntensity", float(intensity))
            color_a, color_b = self._theme_colors()
            if error_active:
                color_b = QVector3D(1.0, .08, .20)
            p.setUniformValue("uColorA", color_a); p.setUniformValue("uColorB", color_b)
            p.setUniformValue("uAccentColor", QVector3D(.78, .42, 1.0))
            g.glDrawArrays(GL_POINTS, 0, self._quality.current.particle_count)
            self._vbo.release(); p.release()
        else:
            self._paint_fallback()
        self._paint_overlay()

    def _theme_colors(self):
        try:
            raw_a, raw_b = self._palette_provider() if self._palette_provider else ("#8b5cf6", "#ff5fd0")
            a, b = QColor(raw_a), QColor(raw_b)
            if not a.isValid() or not b.isValid():
                raise ValueError("invalid theme colour")
            return (QVector3D(a.redF(), a.greenF(), a.blueF()),
                    QVector3D(b.redF(), b.greenF(), b.blueF()))
        except Exception:
            return QVector3D(.55, .30, 1.), QVector3D(1., .36, .82)

    def _paint_fallback(self):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(7, 5, 18, 0))
        points = (1-self._morph.progress)*self._source[::max(1,len(self._source)//700)] + self._morph.progress*self._target[::max(1,len(self._target)//700)]
        s = min(self.width(), self.height()) * .36; cx, cy = self.width()/2, self.height()*.47
        painter.setPen(QPen(QColor(183, 148, 255, 175), 1.6))
        for x, y, z in points:
            painter.drawPoint(int(cx+x*s), int(cy-y*s))
        painter.end()

    def _paint_overlay(self):
        painter = QPainter(self); painter.setPen(QColor(183, 148, 255, 185))
        font = painter.font(); font.setPixelSize(10); font.setLetterSpacing(font.SpacingType.AbsoluteSpacing, 1.2); painter.setFont(font)
        painter.drawText(12, 22, "YAW   AUTO")
        painter.drawText(12, 38, "PIT   AUTO")
        painter.drawText(12, 54, f"CAPAS 03  NODOS {self._quality.current.particle_count}")
        painter.drawText(12, self.height()-34, f"MODO  {self._morph.current_shape.upper()}")
        painter.drawText(12, self.height()-18, f"ENTR {self._in_level:.2f}  SAL {self._out_level:.2f}")
        label = self._STATE_LABELS.get(self.state, self.state)
        display_label = " ".join(label)
        status_font = painter.font()
        status_font.setBold(True)
        status_font.setPixelSize(max(16, min(24, self.height() // 24)))
        status_font.setLetterSpacing(status_font.SpacingType.AbsoluteSpacing, 2.0)
        painter.setFont(status_font)
        status_rect = self.rect().adjusted(24, 0, -24, -38)
        status_rect.setTop(max(0, self.height() - 96))
        painter.setPen(QColor(8, 4, 20, 220))
        painter.drawText(status_rect.translated(1, 2), int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), display_label)
        color_a, _ = self._theme_colors()
        painter.setPen(QColor.fromRgbF(color_a.x(), color_a.y(), color_a.z(), .95))
        painter.drawText(status_rect, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), display_label)
        painter.end()
