# AUT-09 — HUD engineering (avatar excluded)

## Outcome

- Metrics polling now stops while the main HUD is hidden or minimized and resumes at the selected graphics-profile interval when restored.
- Metric callbacks also refuse to sample while hidden, preventing queued/manual callbacks from doing work.
- Gemini voice names now come from `core/voice_config.py`, shared by the runtime, HUD and TTS selector. This is a static catalog because the provider does not reliably expose a live voice-list API.
- Existing theme infrastructure was audited and regression-tested: every theme supplies every required token. No appearance-changing mass replacement or large `ui.py` rewrite was attempted.
- Avatar, visemes, lip-sync, Blender and GLB/GLTF assets were not touched.

## Validation

`QT_QPA_PLATFORM=offscreen python -m pytest tests/test_aut09_hud_engineering.py tests/test_block5_hud_states_avatar.py tests/test_ui_regressions.py -q`

Result: **45 passed, 83 skipped**. The skips are pre-existing environment/Qt-gated UI cases, not new failure conversions.

Visible minimize/restore behavior and voice sound remain **PHYSICAL TEST REQUIRED**.
