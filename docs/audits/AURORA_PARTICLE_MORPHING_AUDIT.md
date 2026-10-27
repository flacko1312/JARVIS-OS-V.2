# AURORA Particle Morphing — Pre-implementation Audit

Date: 2026-10-25  
Baseline: `b759b3fccc31ee2339279ec817748abe6eb84d75`

## CURRENT RENDERER

The central AURORA visual is `HolographicCoreCanvas`, a native PyQt6 `QWidget`
painted with `QPainter`. It manually projects and rotates three nested wireframe
cubes, translucent faces and 70 decorative CPU particles. It does not use Qt
OpenGL, WebGL, Three.js, QWebEngine, shaders or a 3D asset.

## CURRENT CENTRAL VISUAL FILE(S)

- `ui.py`: `HolographicCoreCanvas` and its integration in `MainWindow`.
- `main.py`: computes PCM16 RMS and forwards input/output levels to the UI.

The surrounding telemetry, command bar, selectors, shortcuts, logs and voice
runtime are separate and must remain unchanged.

## CURRENT ANIMATION LOOP

A `QTimer` owned by `HolographicCoreCanvas` calls `_step()`. The widget stops the
timer while hidden and restarts it when shown. Rotation and projection are CPU
math in `_rot()`/`_proj()`. Resize is implicit because each paint uses the live
widget dimensions. Graphics quality currently changes cadence only for this
canvas. Theme colours are read from the active UI theme constants.

## CURRENT AUDIO DATA AVAILABLE

The existing microphone and playback pipelines both call `_report_audio_level()`
in `main.py`. It calculates normalized RMS and forwards it without retaining raw
audio. There are no FFT bands. The replacement can derive transient bass/mid/
treble energy in that same forwarding step without opening another audio stream.

## RECOMMENDED INTEGRATION

Use a native `QOpenGLWidget` and GLSL point rendering. Keep source and target
positions plus deterministic seeds in GPU buffers, interpolate and disperse in
the vertex shader, and draw the primary body in one `GL_POINTS` call. Isolate
sampling, procedural shapes, morph state, audio smoothing, quality policy and
rendering in a package outside `ui.py`. Preserve the existing public HUD API.

Initial shapes are deterministic procedural point sets, so no external asset or
licence is introduced. A reusable area-weighted triangle sampler supports later
mesh registration.

## RISKS

- OpenGL context/driver creation can fail; the widget must degrade to a safe
  raster particle preview and never affect voice or tool execution.
- `main.py` and `ui.py` contain pre-existing user changes, so integration edits
  must be narrow and must not be committed with unrelated work.
- Automated tests cannot certify visual recognisability, physical audio response,
  GPU/VRAM usage or real F4/F8/Gemini interaction. Those remain physical checks.
- Qt's offscreen platform may not expose a hardware context; benchmark output
  must distinguish real-context measurements from simulation/controller costs.

## RESTORE POINT

The untouched baseline and pre-existing worktree state are stored at:

`C:\JARVIS_CHECKPOINTS\particle-morphing-prework-2026-10-25-b759b3f`

Recovery: return to the commit recorded in `base-head.txt`, apply
`tracked-worktree.patch`, then copy the files under `untracked\` back to their
corresponding repository paths. No restore operation has been performed.
