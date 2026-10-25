# AURORA Neural Voice Visual — Implementation Report

Date: 2026-10-25  
Branch: `codex/neural-voice-visual`  
Baseline: `b759b3f`  
Visual checkpoint: `b93a0f5`  
Status: implemented and automatically validated; final owner-operated HUD/audio validation pending.

## Reference-directed refinement — 2026-10-25

The visual was refined against the owner-provided holographic neural triptych.
The same graph now uses a radial flower/constellation silhouette, a brighter
white-magenta nucleus, cyan route accents, symmetric-but-organic tendrils and
separate soft/sharp glow passes. STANDBY remains compact; listening increases
cyan inward activity; speaking expands the full neural corona. Only real state
and audio inputs are displayed—none of the fictional CPU, temperature, memory
or subsystem metrics shown in the aesthetic reference were copied.

Current framebuffer evidence:

`C:\JARVIS_CHECKPOINTS\neural-reference-style-v5-2026-10-25`

## Outcome

The central voice visual is now one continuous holographic neural entity rather
than three separate procedural shapes. It is an irregular deterministic 3D
graph composed of nodes, branching filaments and curved cross-connections.
Standby, listening, processing and speaking deform and energize the same graph;
no state swaps the geometry, recreates buffers or changes the audio pipeline.

The implementation retains the real project architecture: native PyQt6
`QOpenGLWidget`, GLSL 1.20, existing Qt state signals, existing microphone/TTS
RMS and FFT forwarding, and LOW/MEDIUM/HIGH quality selection. There is no
Three.js, WebView or Kotlin/JavaScript bridge in this desktop runtime.

## Files

- `aurora_particles/neural_graph.py`: deterministic branched graph and curved edge buffers.
- `aurora_particles/neural_state.py`: inertial four-state blend and bounded transition queue.
- `aurora_particles/widget.py`: two-pass GPU renderer, audio/state deformation, fallback and lifecycle.
- `aurora_particles/quality.py`: neural budgets and sustained-low-FPS downgrade.
- `aurora_particles/__init__.py`: public neural exports.
- `tests/test_aurora_particle_morphing.py`: graph, state, audio, shader, lifecycle and integration tests.
- `scripts/benchmark_aurora_particles.py`: native-context FPS/CPU/RSS benchmark.
- `scripts/capture_aurora_particle_states.py`: reproducible native framebuffer sequence.

No microphone capture, Gemini Live, F4/F8, AUDIO selector, tool, LILITH or
surrounding HUD implementation was changed by this redesign.

## GPU architecture

One graph is allocated when the widget starts or its quality preset changes.
Normal animation performs no geometry creation and no per-frame NumPy packing.

1. **Node VBO:** position, deterministic seed, radial role and depth.
2. **Filament VBO:** quadratic-Bezier connections stored as three line segments,
   with route position and depth per vertex.
3. **Filament draws:** a faint wide halo pass and one sharp `GL_LINES` pass. A
   fragment pulse moves along each route; direction reverses for listening and
   runs outward for speaking.
4. **Node draws:** one soft point-glow pass and one sharp `GL_POINTS` pass with
   depth-dependent size and circular point sprites.

The renderer therefore uses two reusable programs, two reusable VBOs and four
bounded draw calls. Curves are sampled once. Pulses are shader calculations, not pooled
Python objects. A QPainter graph fallback remains available when OpenGL setup
fails.

## State behaviour

### STANDBY

- 2.5% slow breathing;
- gentle Z drift and parallax rotation;
- reduced energy;
- sparse route pulses;
- the complete graph remains alive while silent.

### ESCUCHANDO

- the same outer branches contract toward the nucleus;
- contraction uses smoothed input RMS plus bass energy;
- mids curl the filaments without destroying their base routes;
- highs add bounded node sparks;
- impulses travel from route exterior toward the center.

### PROCESANDO

- activity converges and circulates internally;
- mid-frequency/latent energy increases curl speed;
- a 420 ms minimum hold preserves a visible processing phase when logical
  states arrive quickly.

### HABLANDO

- smoothed output RMS and bass expand branches from the same base graph;
- the nucleus moves toward white/lilac at high output energy;
- impulses travel from center toward branch endpoints;
- magenta/rose/cyan remain visible outside the nucleus.

Transitions are smoothstep blends of four state weights. The normal durations
are 650 ms standby→listening, 720 ms listening→processing, 900 ms
processing→speaking and 1.05 s speaking→standby. Other transitions use 820 ms.
The queue is bounded at four entries and removes consecutive duplicates.

## Audio analysis

The existing `_report_audio_level()` path remains authoritative:

`existing PCM callback → transient RMS/FFT → Qt signals → neural shader uniforms`

No new stream is opened and raw PCM is not retained. `AudioAnalyzer` applies
separate attack/release smoothing to bass, mid and high bands. The widget adds
frame-rate-independent smoothing to RMS. The shader uses:

- RMS: overall reaction strength;
- bass: global absorption/emission deformation;
- mids: filament curl and internal circulation;
- highs: small bounded sparks and narrower/brighter impulses.

All normalized values are capped before reaching the shader.

## Quality and automatic degradation

| Preset | Nodes | Connections | Curved line vertices | Timer |
|---|---:|---:|---:|---:|
| LOW | 450 | 800 | 4,800 | 33 ms |
| MEDIUM | 800 | 1,600 | 9,600 | 16 ms |
| HIGH | 1,200 | 2,400 | 14,400 | 16 ms |

MEDIUM remains the default. If a visible MEDIUM/HIGH widget remains below
24 FPS for three accumulated seconds, runtime quality drops one level. Brief
stalls decay from the counter and cannot trigger a downgrade. This affects only
the live renderer preset; it does not rewrite the user's saved preference.

## Measured performance

Command:

`C:\JARVIS\.venv\Scripts\python.exe scripts\benchmark_aurora_particles.py`

Native Windows OpenGL, 720×560 viewport. CPU is one-core-equivalent process CPU.
GPU utilization and VRAM were not exposed through a reliable project API and
are **not measured**.

| Preset/scenario | Average FPS | 1% low FPS | Mean frame | Process CPU |
|---|---:|---:|---:|---:|
| LOW idle | 20.67 | 19.87 | 46.77 ms | 0.00%* |
| LOW state+audio | 20.74 | 17.46 | 46.95 ms | 1.80% |
| MEDIUM idle | 60.39 | 59.14 | 16.54 ms | 11.41% |
| MEDIUM state+audio | 59.64 | 58.89 | 16.66 ms | 7.17% |
| HIGH idle | 59.85 | 59.05 | 16.67 ms | 11.43% |
| HIGH state+audio | 59.63 | 58.99 | 16.66 ms | 8.42% |

\*The short LOW idle CPU sampling interval rounded measured process time to
zero; this is not a claim of zero real CPU usage.

After 10 warm-up cycles, 100 accelerated
`STANDBY→ESCUCHANDO→PROCESANDO→HABLANDO→STANDBY` cycles at HIGH changed RSS
from 159.648 MiB to 156.883 MiB (`-2.766 MiB`). This is evidence against an
obvious short-window leak, not a long-soak or driver VRAM certification.

## Automated validation

- Neural visual focused tests: `20 passed`.
- Visual/HUD/audio/F4/F8/device/conversation regressions:
  `151 passed, 77 skipped`.
- Full safe suite: `1323 passed, 1 failed, 93 skipped, 49 subtests passed`.
  The sole failure is the pre-existing dirty-worktree mismatch in
  `test_select_repeat_regressions.py`: its mock lacks the newer
  `target_id` field expected by the independently modified
  `actions/computer_control.py`. No visual file participates in that failure.
- Native framebuffer sequence: nine PNG captures, GPU renderer active,
  MEDIUM/800 nodes/1,600 connections, final state stable STANDBY.

Final captures:

`C:\JARVIS_CHECKPOINTS\neural-voice-visual-final-2026-10-25`

Low-input and high-input listening frames differ in approximately 4.89% of
pixels; mean absolute RGB difference is `(5.19, 7.78, 7.41)`. Rotation and time
also contribute to that framebuffer difference, so the deterministic unit tests
remain the evidence that each audio band reaches its distinct shader behaviour.

## Decisions and limitations

- A graph was chosen instead of increasing the old point count: behaviour and
  connectivity are the visual identity, not particle quantity.
- Connections are quadratic curves sampled into three static segments. Native
  wide anti-aliased GPU curves are not consistently available in GLSL 1.20.
- Impulses are bright regions moving inside the line shader, avoiding a third
  draw call and per-frame object pooling.
- The graph is deterministic but intentionally asymmetric; it is not a brain
  mesh, sphere, atom or music visualizer.
- LOW measures about 20 FPS on the audited Windows compositor. MEDIUM is both
  the default and the best measured operating point.

## Physical validation still required

The following cannot be certified by automated framebuffer capture:

1. perceived state readability in the complete AURORA HUD;
2. real microphone low/high-volume response;
3. real Gemini/TTS emission behaviour;
4. F4 mute and F8 conversation handling while watching the animation;
5. AUDIO selector changes during a live conversation;
6. resize, minimize/restore, context recreation and a prolonged real-time soak.

## Recovery

- Git checkpoint before this redesign: `b93a0f5`.
- Full external snapshot of the pre-redesign visual integration:
  `C:\JARVIS_CHECKPOINTS\neural-voice-visual-prework-2026-10-25-b759b3f`.

Unrelated dirty work remains outside the visual commits and must not be reset or
cleaned when testing rollback.
