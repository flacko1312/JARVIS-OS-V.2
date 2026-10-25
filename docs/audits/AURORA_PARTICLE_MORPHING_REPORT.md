# AURORA Particle Morphing — Implementation Report

Date: 2026-10-25  
Baseline HEAD: `b759b3fccc31ee2339279ec817748abe6eb84d75`  
Status: implemented and automatically validated; physical HUD/voice validation pending.

## Final timing and visual-definition refinement — 2026-10-25

Owner video evidence confirmed that audio reactivity, the large `HABLANDO`
state and the morph mechanism were working, but a short logical THINKING period
was visually skipped. The cause was deterministic: the canvas changed its
display state immediately while a 2.4-second morph was still active. A rapid
`LISTENING → THINKING → SPEAKING` sequence therefore labelled and energized the
still-transitioning cloud as SPEAKING before BRAIN had a stable visible period.

The correction separates immediate **logical state** (still used for audio and
runtime behaviour) from a bounded, de-duplicated **visual state queue**. Morphs
now run at 1.05 seconds and BRAIN receives a minimum 0.45-second stable hold.
The deterministic timeline `t=0 LISTENING, t=.20 THINKING, t=.35 SPEAKING,
t=2.00 LISTENING` now starts visual targets in the required order
`brain → vortex → core`, while `logical_state` reaches LISTENING immediately.
No Gemini, PCM, Qt audio-signal, F4/F8, AUDIO-selector or tool path was delayed.

Visual definition was also refined without changing the renderer architecture:

- CORE now uses 25% compact nucleus, 30% principal ring, two 7.5% secondary
  orbits, 20% internal streams and only 10% sparse ambient particles.
- VORTEX now uses a 14% compact nucleus, thinner depth-offset rings
  (24%/20%/16%/14%) and 12% internal streams, reducing centre overexposure.
- Shader point growth is capped at 1.65×; accent mixing/brightness and additive
  alpha were reduced to retain the theme/accent dual colour without clipping.
- Logs now distinguish `PARTICLE_STATE logical`, `PARTICLE_VISUAL enqueue`,
  `PARTICLE_MORPH source → target`, and `PARTICLE_MORPH complete`.

Native OpenGL framebuffer evidence for stable CORE/BRAIN/VORTEX, audio-reactive
frames and all three transitions is stored in
`C:\JARVIS_CHECKPOINTS\particle-morphing-prework-2026-10-25-b759b3f\timing-definition-validation`.
The capture reports GPU rendering at MEDIUM/10,000 particles and records the
1.05-second morph plus 0.45-second BRAIN hold. This is automated rendering
evidence; owner acceptance in the complete HUD remains pending.

## Final visual/input adjustments — 2026-10-25

Three narrowly scoped changes were made after owner validation:

1. **Dual colour in CORE/VORTEX.** Two float accent attributes were added to the
   existing interleaved VBO. During morphing the shader interpolates the source
   and target accent masks. VORTEX marks its nucleus plus horizontal/vertical
   principal rings (58%) as neon lilac; inclined rings and internal streams keep
   the live theme colour. CORE accents its energy ring and a small inner subset.
   Rendering remains one `GL_POINTS` draw call.
2. **Compact listening CORE.** Only CORE's procedural positions are scaled to
   78%; brain and vortex retain their size. The same source/target morph path is
   used, so no special transition or scale animation was introduced.
3. **Microphone sensitivity.** The real callback path was verified as
   `sounddevice.InputStream callback → _report_audio_level → Qt RMS/FFT signals →
   ParticleMorphingCanvas`. It was not disconnected. The code-level mismatch was
   that microphone PCM and much louder Gemini playback shared the same visual
   gain. A visual-only input gain is now applied in the canvas: RMS 1.85× and
   bass/mid/treble 1.85×/1.65×/1.85×. PCM, FFT normalization, STT, AEC, Qt
   routing and output response were not changed. Rate-limited `PARTICLE_AUDIO`
   logs continue reporting pre-gain measured values for physical diagnosis.

With a red/pink theme provider, real framebuffer captures show lilac principal
rings against the red/pink secondary cloud. Comparing compact CORE before and
after low synthetic microphone energy produced mean absolute RGB change
approximately `(17.24, 12.80, 15.57)`. This proves visual sensitivity but does
not replace owner verification with the selected physical microphone.
The corresponding CORE/BRAIN/transition/VORTEX/return framebuffers are stored in
the restore checkpoint's `final-visual-adjustments` directory.

## Runtime integration correction — 2026-10-25

Owner physical validation found that the first implementation rendered but was
not connected completely to AURORA. Code inspection confirmed two defects:

1. `_apply_state()` assigned `hud.state` but never requested a shape morph.
2. Audio/tool/error facade methods called the widget directly and therefore did
   not establish a Qt-thread boundary for worker/audio callbacks.

The correction adds a separately editable `STATE_SHAPE_MAP`, routes state through
`ParticleMorphingCanvas.set_state()`, and sends RMS, FFT, tool activity and error
updates through Qt signals owned by `MainWindow`. Current automatic mapping is:

- STANDBY/IDLE/LISTENING → core
- THINKING/PROCESSING → brain
- SPEAKING → vortex
- TOOL/EXECUTING → brain with increased energy
- ERROR/MUTED → retain the current shape with temporary distortion or dimming

Repeated states do not restart a morph. Morph start/completion and rate-limited
real PCM values are logged as `PARTICLE_MORPH` and `PARTICLE_AUDIO` records.
Optional development shortcuts are enabled only with
`JARVIS_PARTICLE_DEV_SHORTCUTS=1`: Ctrl+Alt+1/2/3 select core/brain/vortex.

## SPEAKING shape correction — Energy Vortex

Physical validation accepted audio reactivity, morphing and state integration,
but found the additive skull point cloud insufficiently recognisable. The normal
SPEAKING target is therefore now `vortex`; `skull` remains registered only for
internal compatibility/testing.

Vortex is deterministic procedural geometry with this current particle split:

- 14% compact technological nucleus;
- 24% horizontal toroidal orbit;
- 20% vertical toroidal orbit;
- 16% +45° inclined orbit;
- 14% -45° inclined orbit;
- remaining 12% in three internal helical energy streams.

All sets use the active LOW/MEDIUM/HIGH particle count and are concatenated into
the same single source/target VBO. The shader continues to provide slow ambient
rotation and existing bass/mid/treble response; no audio code, extra mesh or
per-ring draw call was added.

Audio normalization now uses FFT amplitude normalization and compression suitable
for speech. Synthetic measurements at amplitude 4000/32768 produced dominant
energies of approximately 0.759 at 100 Hz, 0.730 at 700 Hz and 0.769 at 4 kHz;
quiet 700 Hz input at amplitude 800 still produced mid≈0.326. These are measured
synthetic diagnostics, not claims about the owner's microphone gain.

State labels are now large, bold, theme-coloured, technologically spaced and
positioned in a reserved lower-center band. The particle body is scaled upward
slightly so the label does not cover the stable form.

## Scope and architecture

Only the central `HolographicCoreCanvas` instance was replaced. Panels, command
bar, audio selectors, F4/F8 handling, Gemini Live, logs and tools were not
rewritten. `ui.py` now instantiates `ParticleMorphingCanvas`; the former canvas
remains in place as untouched legacy code during this incremental change.

The renderer is native PyQt6 `QOpenGLWidget` + GLSL 1.20. It uses one interleaved
VBO (`source.xyz`, `target.xyz`, `seed`) and one `GL_POINTS` draw for the primary
body. The vertex shader performs interpolation, breathing, waves and controlled
mid-transition dispersion. The fragment shader renders circular additive points.
A raster point-cloud fallback is used if context/shader/VBO creation fails;
renderer errors do not enter the voice or tool paths.

Modules:

- `quality.py`: LOW/MEDIUM/HIGH policies.
- `sampler.py`: reusable area-weighted triangle `ModelPointSampler`.
- `shapes.py`: deterministic procedural core, brain, vortex and legacy skull point sets.
- `controller.py`: explicit safe morph state machine and request queue.
- `audio.py`: transient PCM16 RMS plus bass/mid/treble FFT energy.
- `widget.py`: GPU buffers, shader, lifecycle, overlays and fallback.

No asset was downloaded and no external licence was introduced.

## Point sampling and shape registration

`ModelPointSampler.sample(name, vertices, triangles, count)` selects triangles by
surface area, samples barycentric coordinates, centers/scales the result and
caches an exact-size contiguous `float32` array. Initial shapes are procedural
because the repository had no appropriate 3D model.

The engine API is:

```python
canvas.registerShape("new_shape", positions)  # exact active particle count
canvas.morphTo("new_shape")
```

Changing quality regenerates equal-count sets and replaces the VBO allocation;
the old storage is not retained.

## Morph and dissolve

The same particle index moves between source and target. `MorphController` uses:

`STABLE → DISSOLVING → DISPERSED → REASSEMBLING → STABILIZING → STABLE`

Smoothstep interpolation is augmented by deterministic seed displacement whose
strength peaks at transition midpoint. Requests during a transition are queued
and de-duplicated. There are no solid meshes, opacity swaps or model crossfades.

Development hooks: `morphTo("core"|"brain"|"vortex")` and
`force_dissolve()`. They are internal and add no normal-UI controls.

## Audio reactivity

The existing microphone and output PCM callbacks remain the only streams.
`main._report_audio_level()` now derives transient low/mid/high energy and sends
it beside the existing RMS. Raw PCM is not retained. Bass affects radial pulse,
mids affect an internal wave and treble affects point size/brightness. All visual
telemetry calls are exception-isolated from capture/playback.

## Quality presets

| Preset | Particles | Timer | Shader turbulence |
|---|---:|---:|---:|
| LOW | 4,000 | 33 ms | reduced |
| MEDIUM | 10,000 | 16 ms | normal |
| HIGH | 20,000 | 16 ms | full |

MEDIUM remains the default. On this Windows compositor, 33 ms was quantized below
30 FPS, so MEDIUM uses a vsynced 16 ms update while retaining half HIGH's points.

## Measured performance

Command:

`C:\JARVIS\.venv\Scripts\python.exe scripts\benchmark_aurora_particles.py`

Native Windows Qt platform, 720×560 viewport, real OpenGL context, particle body
visible. Process CPU is one-core-equivalent and includes the small benchmark
window. GPU utilization/VRAM were not available through a reliable project API
and are therefore **NOT MEASURED**.

| Preset/scenario | Average FPS | 1% low FPS | Mean frame | Process CPU |
|---|---:|---:|---:|---:|
| LOW idle | 19.99 | 16.21 | 47.14 ms | 1.04% |
| LOW vortex morph+audio | 20.69 | 18.44 | 47.45 ms | 5.39% |
| MEDIUM idle | 60.26 | 57.31 | 16.42 ms | 10.35% |
| MEDIUM vortex morph+audio | 59.62 | 57.69 | 16.67 ms | 6.57% |
| HIGH idle | 59.63 | 57.73 | 16.64 ms | 9.32% |
| HIGH vortex morph+audio | 59.62 | 57.84 | 16.67 ms | 10.75% |

After 10 warm-up cycles, 100 accelerated `core → brain → vortex` cycles at HIGH
changed process RSS from 171.422 MiB to 170.809 MiB (`-0.613 MiB`). This supports
buffer/memory stability for the automated stress window; it is not a long-soak
or GPU-driver VRAM certification.

## Automated validation

- Particle/integration-focused: `41 passed`.
- Relevant particle/UI/audio/F4/F8/device/HUD/conversation regression:
  `172 passed, 77 skipped`.
- Full safe suite: `1344 passed, 1 failed, 93 skipped, 49 subtests passed`.

The remaining full-suite failure is outside this visual change and reproduces
pre-existing dirty work: the modified computer-control target contract breaks
`test_select_repeat_regressions.py`. It was not changed here.

Automated native-context captures confirmed visible point-cloud core, brain and
vortex outputs plus a real `brain → vortex` transition frame. Current captures
are in the restore checkpoint's `vortex-validation` directory. This is rendering
evidence, not owner visual acceptance of the new vortex.

The earlier post-integration sequence confirmed the labels and state wiring with
the legacy skull. It is retained only as historical evidence; the current
SPEAKING validation is the vortex sequence referenced above.
Comparing listening idle versus injected measured audio produced mean absolute
RGB differences of approximately `(29.22, 21.67, 28.87)`, confirming that audio
changes rendered pixels. Owner microphone/output validation remains pending.

## Physical validation still required

- Recognisability and desired aesthetics in the complete AURORA HUD.
- Real-time core→brain→vortex→core dissolve/reassembly appearance.
- Microphone and AURORA-output responsiveness with real audio devices.
- Resize, minimise/restore, pause/resume and theme changes in the full app.
- F4 mute, F8 conversation, Gemini Live and AUDIO selector regression.
- Driver context-loss/recreation and a prolonged real-time soak.
- Independent GPU utilization and VRAM measurement if desired.

## Known limitations

- Core/brain/vortex are procedural approximations; legacy skull remains internal.
- LOW intentionally targets about 20 FPS on the audited compositor.
- The fallback is a reduced raster preview, not feature parity with GLSL.
- State-to-shape mappings are deliberately not hard-coded; JARVIS can adopt them
  later through the public morph hook without coupling its logic to the engine.

## Restore / rollback

Restore point:

`C:\JARVIS_CHECKPOINTS\particle-morphing-prework-2026-10-25-b759b3f`

1. Use the commit in `base-head.txt` as the baseline.
2. Apply `tracked-worktree.patch` (`git apply --3way <path>` on that baseline).
3. Copy `untracked\...` back to matching repository paths.

That checkpoint reconstructs the pre-task tracked and untracked worktree. Do not
run a broad reset/clean because it would destroy unrelated user work.
