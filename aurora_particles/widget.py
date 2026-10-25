from __future__ import annotations

import logging
import math
import time
from typing import Callable

import numpy as np
from PyQt6 import sip
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen, QVector3D, QVector4D
from PyQt6.QtOpenGL import (
    QOpenGLBuffer, QOpenGLShader, QOpenGLShaderProgram,
    QOpenGLVersionFunctionsFactory, QOpenGLVersionProfile,
)
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import QSizePolicy

from .audio import AudioAnalyzer
from .neural_graph import NeuralGraph, build_neural_graph
from .neural_morph import MORPH_GLSL
from .neural_state import NeuralStateController
from .quality import QualityManager

logger = logging.getLogger("jarvis.aurora_particles")

GL_COLOR_BUFFER_BIT = 0x00004000
GL_DEPTH_BUFFER_BIT = 0x00000100
GL_FLOAT = 0x1406
GL_POINTS = 0x0000
GL_LINES = 0x0001
GL_BLEND = 0x0BE2
GL_SRC_ALPHA = 0x0302
GL_ONE = 1
GL_ONE_MINUS_SRC_ALPHA = 0x0303
GL_PROGRAM_POINT_SIZE = 0x8642
GL_POINT_SPRITE = 0x8861

DEFORM_GLSL = MORPH_GLSL

NODE_VERTEX_SHADER = """
#version 120
attribute vec3 aPosition;
attribute float aSeed,aRole,aDepth;
uniform float uTime,uAspect,uPointSize,uError,uNodeGlow;
uniform vec4 uState,uAudio;
varying float vSeed,vRole,vDepth,vEnergy;
""" + DEFORM_GLSL + """
void main(){
  vec3 p=neuralDeform(aPosition,aSeed,aRole,aRole,1.0);
  gl_Position=vec4(p.xy,p.z*.28,1.0);
  float listening=uState.y,processing=uState.z,speaking=uState.w;
  float high=uAudio.w,rms=uAudio.x;
  float spark=step(.86,fract(aSeed*19.0+uTime*(.10+high*.85)))*high;
  float depthScale=.68+.54*aDepth;
  float accent=step(.78,fract(aSeed*17.0));
  float coreWeight=(1.0-aRole)*(1.0-aRole);
  gl_PointSize=uPointSize*depthScale*(.30+.40*accent+1.25*coreWeight)
      *min(1.50,1.0+high*.34+rms*.14+spark*.24)*mix(1.0,2.7,uNodeGlow);
  vSeed=aSeed;vRole=aRole;vDepth=aDepth;
  vEnergy=clamp(.20+processing*.24+speaking*.24+listening*.14+rms*.42+spark*.28+uError*.20,0.,1.);
}
"""

NODE_FRAGMENT_SHADER = """
#version 120
uniform vec3 uViolet,uMagenta,uCyan;
uniform vec4 uState,uAudio;
uniform float uNodeGlow,uTime;
varying float vSeed,vRole,vDepth,vEnergy;
void main(){
  vec2 q=gl_PointCoord-vec2(.5);float d=dot(q,q);if(d>.25)discard;
  if(vRole>.18 && fract(vSeed*37.0)<.48)discard;
  float halo=smoothstep(.25,.01,d);
  vec3 branch=mix(vec3(.96,.12,.58),vec3(.06,.78,1.0),clamp(vRole*.72+fract(vSeed*7.0)*.28,0.,1.));
  vec3 color=mix(vec3(.45,.12,.96),branch,.38+.48*vRole);
  float core=(1.0-vRole)*(.18+uState.z*.22+uState.w*(.38+.62*uAudio.x));
  color=mix(color,vec3(1.0,.94,1.0),clamp(core,0.,.82));
  float amber=uState.z*step(.91,fract(vSeed*29.0+uTime*.08));
  color=mix(color,vec3(1.0,.32,.035),amber*.52);
  float coreWeight=(1.0-vRole)*(1.0-vRole);
  float alpha=halo*(.30+.18*vEnergy+.58*coreWeight)*(.68+.32*vDepth)*mix(1.0,.16,uNodeGlow);
  gl_FragColor=vec4(color*(.44+.20*vEnergy+coreWeight*.34+uNodeGlow*.22),alpha);
}
"""

EDGE_VERTEX_SHADER = """
#version 120
attribute vec3 aPosition;
attribute float aSeed,aPath,aDepth,aLayer;
uniform float uTime,uAspect,uError;
uniform vec4 uState,uAudio;
varying float vSeed,vPath,vDepth,vEnergy,vLayer;
""" + DEFORM_GLSL + """
void main(){
  vec3 p=neuralDeform(aPosition,aSeed,clamp(length(aPosition.xy)/.88,0.,1.),aPath,aLayer);
  gl_Position=vec4(p.xy,p.z*.28,1.0);
  vSeed=aSeed;vPath=aPath;vDepth=aDepth;vLayer=aLayer;
  vEnergy=clamp(.18+uAudio.x*.36+uAudio.z*.28+uState.z*.18+uState.w*.20+uError*.12,0.,1.);
}
"""

EDGE_FRAGMENT_SHADER = """
#version 120
uniform float uTime,uGlowPass;
uniform vec3 uViolet,uMagenta,uCyan;
uniform vec4 uState,uAudio;
varying float vSeed,vPath,vDepth,vEnergy,vLayer;
void main(){
  float listening=uState.y,processing=uState.z,speaking=uState.w;
  float rate=.045+uAudio.x*.34+processing*.27+speaking*.20;
  float reverse=listening/(listening+speaking+.001);
  float phaseA=fract(vSeed+uTime*rate*(.72+.18*vLayer));
  float phaseB=fract(vSeed*3.17+.37+uTime*rate*(1.18+.11*vLayer));
  float phaseC=fract(vSeed*7.31+.71+uTime*rate*(1.72+.09*vLayer));
  phaseA=mix(phaseA,1.0-phaseA,reverse);phaseB=mix(phaseB,1.0-phaseB,reverse);phaseC=mix(phaseC,1.0-phaseC,reverse);
  float deltaA=abs(vPath-phaseA);float deltaB=abs(vPath-phaseB);float deltaC=abs(vPath-phaseC);
  float pulseA=exp(-deltaA*deltaA/(.00018+uAudio.w*.00062));
  float pulseB=exp(-deltaB*deltaB/(.00010+uAudio.w*.00045));
  float pulseC=exp(-deltaC*deltaC/(.00007+uAudio.w*.00034));
  float pulse=max(pulseA,max(pulseB*.78,pulseC*.56));
  float occasional=step(.76,fract(vSeed*13.7+uTime*.035));
  pulse*=clamp(.10+listening*.80+processing*.92+speaking*.88+uState.x*.12*occasional,0.,1.);
  float secondary=step(.5,vLayer)-step(1.5,vLayer);float wisp=step(1.5,vLayer);
  vec3 mainColor=mix(vec3(.48,.035,.94),vec3(1.0,.025,.42),fract(vSeed*5.2));
  vec3 secondaryColor=mix(vec3(.10,.055,.92),vec3(.0,.60,1.0),fract(vSeed*7.7));
  vec3 microColor=mix(vec3(.008,.018,.30),vec3(.0,.62,.70),step(.82,fract(vSeed*23.0)));
  vec3 base=mix(mainColor,secondaryColor,secondary);
  base=mix(base,microColor,wisp);
  base=mix(base,vec3(.0,.78,1.0),listening*(.18+.40*secondary+.52*wisp));
  base=mix(base,vec3(.01,.86,.78),wisp*step(.86,fract(vSeed*23.0))*.44);
  float amber=processing*step(.78,fract(vSeed*31.0+floor(uTime*.45)*.13));
  base=mix(base,vec3(1.0,.27,.025),amber*.64);
  vec3 impulse=mix(vec3(.10,.72,1.0),vec3(1.0,.24,.72),speaking);
  impulse=mix(impulse,vec3(1.0,.72,.24),processing*amber*.72);
  vec3 color=mix(base,impulse,pulse*(.26+.18*speaking));
  float layerAlpha=1.0-secondary*.20-wisp*.70;
  float routeFade=.48+.52*(1.0-smoothstep(.08,1.0,vPath));
  float alpha=(.28+.15*vEnergy+pulse*.32)*(.32+.68*vDepth)*layerAlpha*routeFade;
  alpha*=mix(1.0,.24,uGlowPass);
  gl_FragColor=vec4(color*(.58+pulse*.34+uGlowPass*.16),alpha);
}
"""


def _mode_for_state(state: str) -> str:
    state = str(state or "STANDBY").strip().upper()
    if state in {"LISTENING", "ESCUCHANDO"}:
        return "listening"
    if state in {"THINKING", "PROCESSING", "PENSANDO", "TOOL", "EXECUTING"}:
        return "processing"
    if state in {"SPEAKING", "HABLANDO"}:
        return "speaking"
    return "standby"


class ParticleMorphingCanvas(QOpenGLWidget):
    """One living neural entity with state and real-audio driven deformation."""

    _STATE_LABELS = {
        "STANDBY": "STANDBY", "IDLE": "STANDBY", "INITIALISING": "STANDBY",
        "LISTENING": "ESCUCHANDO", "THINKING": "PROCESANDO",
        "PROCESSING": "PROCESANDO", "SPEAKING": "HABLANDO", "MUTED": "MIC OFF",
    }
    _STATE_SUBTITLES = {
        "STANDBY": "ESPERANDO", "IDLE": "ESPERANDO", "INITIALISING": "INICIANDO",
        "LISTENING": "TU VOZ ENTRA", "THINKING": "ANALIZANDO",
        "PROCESSING": "ANALIZANDO", "SPEAKING": "JARVIS RESPONDE",
        "MUTED": "MICRÓFONO SILENCIADO",
    }

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
        quality = (config or {}).get("graphics_quality", "medium") if isinstance(config, dict) else "medium"
        self._quality = QualityManager(quality)
        self._state_controller = NeuralStateController()
        self._audio = AudioAnalyzer()
        self._in_level = self._out_level = self._visual_rms = 0.0
        self._graph: NeuralGraph | None = None
        self._node_program: QOpenGLShaderProgram | None = None
        self._edge_program: QOpenGLShaderProgram | None = None
        self._node_vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self._edge_vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self._gl = None
        self._gpu_ready = False
        self._gl_error = ""
        self._pending_upload = True
        self._last = time.perf_counter()
        self._time = 0.0
        self._load_graph()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(self._quality.current.frame_ms)

    def set_state(self, state: str) -> bool:
        normalized = str(state or "STANDBY").strip().upper()
        self.logical_state = normalized
        self.state = normalized
        self.speaking = normalized in {"SPEAKING", "HABLANDO"}
        mode = _mode_for_state(normalized)
        logger.info("NEURAL_STATE logical=%s visual_target=%s", normalized, mode)
        started = self._state_controller.request(mode)
        if started:
            logger.info("NEURAL_TRANSITION start %s -> %s duration=%.2f",
                        self._state_controller.current, mode, self._state_controller.duration)
        elif self._state_controller._queue:
            logger.info("NEURAL_TRANSITION enqueue=%s depth=%d", mode, len(self._state_controller._queue))
        return started

    def morph_to(self, name: str) -> bool:
        aliases = {"core": "standby", "brain": "processing", "vortex": "speaking"}
        mode = aliases.get(str(name).lower(), str(name).lower())
        if mode not in {"standby", "listening", "processing", "speaking"}:
            raise KeyError(name)
        return self._state_controller.request(mode)

    morphTo = morph_to

    def register_shape(self, name: str, positions) -> None:
        raise RuntimeError("The neural renderer uses one continuous graph; external shape registration is unsupported")

    registerShape = register_shape

    def force_dissolve(self) -> None:
        order = ("standby", "listening", "processing", "speaking")
        current = self._state_controller.target
        self._state_controller.request(order[(order.index(current) + 1) % len(order)])

    def set_input_audio_level(self, level: float):
        self._in_level = max(0.0, min(1.0, float(level) * 1.85))

    def set_output_audio_level(self, level: float):
        self._out_level = max(0.0, min(1.0, float(level)))

    def set_input_audio_spectrum(self, bass: float, mid: float, treble: float):
        self._audio.set_bands("input", (bass * 1.85, mid * 1.65, treble * 1.85))

    def set_output_audio_spectrum(self, bass: float, mid: float, treble: float):
        self._audio.set_bands("output", (bass, mid, treble))

    def set_executing(self, active: bool):
        self.executing = bool(active)
        self._state_controller.request("processing" if self.executing else _mode_for_state(self.logical_state))

    def flag_error(self, seconds: float = 6.0):
        self._error_until = time.time() + seconds

    def set_graphics_quality(self, quality: str):
        old = self._quality.current.name
        preset = self._quality.set(quality)
        self._timer.setInterval(preset.frame_ms)
        if preset.name != old:
            self._load_graph(); self._pending_upload = True

    @property
    def renderer_status(self) -> dict:
        preset = self._quality.current
        return {
            "gpu": self._gpu_ready, "error": self._gl_error, "quality": preset.name,
            "particles": preset.particle_count, "nodes": preset.particle_count,
            "connections": preset.edge_count, "mode": self._state_controller.current,
            "filaments": self._graph.filament_count if self._graph is not None else 0,
            "filaments_by_layer": self._graph.layer_filament_counts if self._graph is not None else (0,0,0),
            "segments_by_layer": self._graph.layer_segment_counts if self._graph is not None else (0,0,0),
            "target_mode": self._state_controller.target,
            "transition_progress": round(float(self._state_controller.progress), 3),
        }

    def _load_graph(self) -> None:
        preset = self._quality.current
        self._graph = build_neural_graph(preset.particle_count, preset.edge_count)

    @staticmethod
    def _build_program(parent, vertex: str, fragment: str) -> QOpenGLShaderProgram:
        program = QOpenGLShaderProgram(parent)
        if not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, vertex): raise RuntimeError(program.log())
        if not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, fragment): raise RuntimeError(program.log())
        if not program.link(): raise RuntimeError(program.log())
        return program

    def initializeGL(self):
        try:
            profile = QOpenGLVersionProfile(); profile.setVersion(2, 0)
            self._gl = QOpenGLVersionFunctionsFactory.get(profile, self.context())
            if self._gl is None: raise RuntimeError("compatible OpenGL functions unavailable")
            self._gl.initializeOpenGLFunctions()
            self._node_program = self._build_program(self, NODE_VERTEX_SHADER, NODE_FRAGMENT_SHADER)
            self._edge_program = self._build_program(self, EDGE_VERTEX_SHADER, EDGE_FRAGMENT_SHADER)
            if not self._node_vbo.create() or not self._edge_vbo.create(): raise RuntimeError("neural VBO creation failed")
            self._gpu_ready = True; self._upload()
        except Exception as exc:
            self._gpu_ready = False
            self._gl_error = f"{type(exc).__name__}: {exc}"[:300]
            logger.warning("NEURAL_RENDER fallback reason=%s", self._gl_error)

    def _upload(self):
        if not self._gpu_ready or self._graph is None: return
        graph = self._graph
        node_data = np.column_stack((graph.nodes, graph.node_seed, graph.node_role, graph.node_depth)).astype(np.float32)
        edge_data = np.column_stack((graph.edge_vertices, graph.edge_seed, graph.edge_path, graph.edge_depth, graph.edge_layer)).astype(np.float32)
        for vbo, packed in ((self._node_vbo, node_data), (self._edge_vbo, edge_data)):
            vbo.bind(); vbo.allocate(int(packed.nbytes)); vbo.write(0, sip.voidptr(packed.ctypes.data), int(packed.nbytes)); vbo.release()
        self._pending_upload = False

    def _step(self):
        now = time.perf_counter(); dt = min(.1, max(.001, now-self._last)); self._last = now; self._time += dt
        downgrade = self._quality.observe_frame(dt) if self.isVisible() else None
        if downgrade:
            logger.warning("NEURAL_QUALITY auto_downgrade %s -> %s", self._quality.current.name, downgrade)
            self.set_graphics_quality(downgrade)
        completed = self._state_controller.update(dt)
        if completed: logger.info("NEURAL_TRANSITION complete mode=%s", completed)
        raw_rms = self._out_level if self.speaking else self._in_level
        factor = 1.0-math.exp(-dt*(10.0 if raw_rms > self._visual_rms else 4.2))
        self._visual_rms += (raw_rms-self._visual_rms)*factor
        self._audio.decay(math.exp(-dt*1.15)); self._in_level *= math.exp(-dt*2.0); self._out_level *= math.exp(-dt*1.65)
        self.update()

    def hideEvent(self, event):
        self._timer.stop(); super().hideEvent(event)

    def showEvent(self, event):
        self._last = time.perf_counter()
        if not self._timer.isActive(): self._timer.start(self._quality.current.frame_ms)
        super().showEvent(event)

    def closeEvent(self, event):
        self._timer.stop()
        if self.context():
            self.makeCurrent()
            for vbo in (self._node_vbo, self._edge_vbo):
                if vbo.isCreated(): vbo.destroy()
            self.doneCurrent()
        super().closeEvent(event)

    def _uniforms(self, program: QOpenGLShaderProgram) -> None:
        bands = self._audio.output if self.speaking else self._audio.input
        program.setUniformValue("uTime", float(self._time))
        program.setUniformValue("uAspect", float(max(1,self.width())/max(1,self.height())))
        program.setUniformValue("uState", QVector4D(*(float(x) for x in self._state_controller.weights)))
        program.setUniformValue("uAudio", QVector4D(float(self._visual_rms), *(float(x) for x in bands)))
        program.setUniformValue("uError", 1.0 if time.time() < self._error_until else 0.0)
        violet, magenta = self._theme_colors()
        program.setUniformValue("uViolet", violet); program.setUniformValue("uMagenta", magenta)
        program.setUniformValue("uCyan", QVector3D(.16,.88,1.0))

    @staticmethod
    def _attributes(program, specs, stride):
        for name, offset, size in specs:
            location = program.attributeLocation(name); program.enableAttributeArray(location)
            program.setAttributeBuffer(location, GL_FLOAT, offset, size, stride)

    def paintGL(self):
        if self._gpu_ready and self._node_program and self._edge_program and self._gl and self._graph:
            if self._pending_upload: self._upload()
            g=self._gl; g.glClearColor(.003,.004,.014,0.0); g.glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT)
            g.glEnable(GL_BLEND); g.glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA); g.glEnable(GL_PROGRAM_POINT_SIZE); g.glEnable(GL_POINT_SPRITE)
            edge=self._edge_program; edge.bind(); self._edge_vbo.bind()
            self._attributes(edge,(("aPosition",0,3),("aSeed",12,1),("aPath",16,1),("aDepth",20,1),("aLayer",24,1)),28)
            self._uniforms(edge)
            g.glBlendFunc(GL_SRC_ALPHA,GL_ONE)
            edge.setUniformValue("uGlowPass",1.0); g.glLineWidth(3.0); g.glDrawArrays(GL_LINES,0,len(self._graph.edge_vertices))
            g.glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA)
            edge.setUniformValue("uGlowPass",0.0)
            first=0
            for width,segments in zip((1.8,1.15,1.0),self._graph.layer_segment_counts):
                count=segments*2; g.glLineWidth(width); g.glDrawArrays(GL_LINES,first,count); first+=count
            self._edge_vbo.release(); edge.release()
            node=self._node_program; node.bind(); self._node_vbo.bind()
            self._attributes(node,(("aPosition",0,3),("aSeed",12,1),("aRole",16,1),("aDepth",20,1)),24)
            self._uniforms(node); node.setUniformValue("uPointSize",float(self._quality.current.point_size))
            g.glBlendFunc(GL_SRC_ALPHA,GL_ONE)
            node.setUniformValue("uNodeGlow",1.0); g.glDrawArrays(GL_POINTS,0,self._quality.current.particle_count)
            g.glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA)
            node.setUniformValue("uNodeGlow",0.0); g.glDrawArrays(GL_POINTS,0,self._quality.current.particle_count)
            self._node_vbo.release(); node.release()
        else: self._paint_fallback()
        self._paint_overlay()

    def _theme_colors(self):
        try:
            raw_a,raw_b=self._palette_provider() if self._palette_provider else ("#8b5cf6","#ff4fa3")
            a,b=QColor(raw_a),QColor(raw_b)
            if not a.isValid() or not b.isValid(): raise ValueError("invalid theme colour")
            return QVector3D(a.redF(),a.greenF(),a.blueF()),QVector3D(b.redF(),b.greenF(),b.blueF())
        except Exception: return QVector3D(.52,.24,1.0),QVector3D(1.0,.22,.64)

    def _paint_fallback(self):
        painter=QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing,True); painter.fillRect(self.rect(),QColor(1,2,10,245))
        if self._graph is None: painter.end(); return
        scale=min(self.width(),self.height())*.38; cx,cy=self.width()/2,self.height()*.46
        painter.setPen(QPen(QColor(114,72,210,70),1.0)); vertices=self._graph.edge_vertices
        for index in range(0,len(vertices),2):
            a,b=vertices[index],vertices[index+1]
            painter.drawLine(int(cx+a[0]*scale),int(cy-a[1]*scale),int(cx+b[0]*scale),int(cy-b[1]*scale))
        painter.setPen(QPen(QColor(221,121,255,185),1.8))
        for (x,y,_z),seed in zip(self._graph.nodes,self._graph.node_seed):
            if seed>.55: painter.drawPoint(int(cx+x*scale),int(cy-y*scale))
        painter.end()

    def _paint_overlay(self):
        painter=QPainter(self); label=self._STATE_LABELS.get(self.state,self.state)
        subtitle=self._STATE_SUBTITLES.get(self.state,"")
        font=painter.font(); font.setBold(True); font.setPixelSize(max(14,min(20,self.height()//28))); font.setLetterSpacing(font.SpacingType.AbsoluteSpacing,4.0); painter.setFont(font)
        rect=self.rect().adjusted(24,0,-24,-42); rect.setTop(max(0,self.height()-104)); painter.setPen(QColor(255,71,190,225))
        painter.drawText(rect,int(Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignVCenter),label)
        subfont=painter.font(); subfont.setBold(False); subfont.setPixelSize(max(8,min(11,self.height()//48))); subfont.setLetterSpacing(subfont.SpacingType.AbsoluteSpacing,2.4); painter.setFont(subfont)
        subrect=rect.translated(0,24); painter.setPen(QColor(190,153,255,180))
        painter.drawText(subrect,int(Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignVCenter),subtitle); painter.end()
