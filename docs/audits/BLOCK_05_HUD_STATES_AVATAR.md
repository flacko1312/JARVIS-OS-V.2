# BLOCK 05 — HUD, UI & STATES AUDIT

> **AVATAR STATUS: DEFERRED BY USER / OUT OF CURRENT SCOPE.** Existing avatar-related
> code, assets and historical test evidence are preserved but are not completion
> requirements, failures or blockers for the current JARVIS audit.

**Date**: 2026-10-15
**Auditor**: Claude Opus 4.6

---

## 1. Objetivo

Auditar los subsistemas de interfaz dentro del alcance actual: HUD (AURORA PyQt6 GUI, 8688 lineas), UI y Estados (maquina de estados visible, transiciones, locale). La evidencia historica relacionada con avatar/graficos se conserva, pero el avatar queda diferido por decision del usuario y fuera del alcance actual.

## 2. Estado inicial

- **928 passed, 0 failed, 87 skipped** en la suite tras Block 4
- Tests existentes en `test_ui_branding.py`, `test_ui_submit.py`, `test_ui_regressions.py`, `test_ui_current_contract.py` cubren: temas, branding, submit, intro, voice, graficos (40+ tests)
- Sin tests para: ui_locale.py, core/graphics_capability.py scoring, ui.py helpers puros

## 3. Archivos inspeccionados

| Archivo | Lineas |
|---------|--------|
| `ui.py` | 8688 |
| `ui_locale.py` | 436 |
| `core/graphics_capability.py` | 223 |

## 4. Funciones existentes

### A — HUD (`ui.py`)

| Funcion | Estado |
|---------|--------|
| MainWindow (QMainWindow) | IMPLEMENTED |
| HudCanvas (holographic animation) | IMPLEMENTED |
| HolographicCoreCanvas (arc reactor) | IMPLEMENTED |
| AgentGridWidget (8 agent cards) | IMPLEMENTED |
| AIActivityCanvas (neural network vis) | IMPLEMENTED |
| ChatBubbleWidget (conversation UI) | IMPLEMENTED |
| FocusDialogueWidget | IMPLEMENTED |
| MissionControlPanel (right panel tabs) | IMPLEMENTED |
| LogWidget (event log) | IMPLEMENTED |
| TaskQueueWidget | IMPLEMENTED |
| ToolLogWidget | IMPLEMENTED |
| FileDropZone (drag-and-drop) | IMPLEMENTED |
| VisionPreviewWindow (screen/camera feed) | IMPLEMENTED |
| CompactModeWidget | IMPLEMENTED |
| SetupOverlay (first-run config) | IMPLEMENTED |
| SettingsOverlay | IMPLEMENTED |
| ShortcutsOverlay | IMPLEMENTED |
| NameSignInOverlay | IMPLEMENTED |
| VoiceSelectOverlay | IMPLEMENTED |
| KeyTutorialOverlay | IMPLEMENTED |
| PopupManager (toast notifications) | IMPLEMENTED |
| PresenceSystem | IMPLEMENTED |
| ThemeManager (dynamic color themes) | IMPLEMENTED |
| SystemTrayIcon | IMPLEMENTED |
| Graphics profiles (low/medium/high) | IMPLEMENTED |
| Keyboard shortcuts (F4/F8/F11/Ctrl+M/Ctrl+/) | IMPLEMENTED |
| 9 Gemini voices | IMPLEMENTED |
| Research/presentation progress UI | IMPLEMENTED |
| Tool progress indicators | IMPLEMENTED |
| MetricBar + SparklineBar (telemetry) | IMPLEMENTED |
| _SysMetrics (CPU/RAM/GPU monitoring) | IMPLEMENTED |

### B — STATES (`ui_locale.py`)

| Funcion | Estado |
|---------|--------|
| t() translation with fallback | IMPLEMENTED |
| state_display() internal→visual state | IMPLEMENTED |
| status_abbrev() abbreviated status | IMPLEMENTED |
| UI_TEXT dict (200+ translations) | IMPLEMENTED |
| STATE_DISPLAY dict (14 states) | IMPLEMENTED |
| STATUS_ABBREV dict (6 abbreviations) | IMPLEMENTED |
| All UI text in Castilian Spanish | IMPLEMENTED |

### C — GRAPHICS CAPABILITY (`core/graphics_capability.py`)

Esta seccion conserva evidencia tecnica del HUD ya obtenida. No valida ni reabre trabajo de avatar.

| Funcion | Estado |
|---------|--------|
| _classify_gpu() (6 classes) | IMPLEMENTED |
| score_graphics_capability() | IMPLEMENTED |
| detect_graphics_capability() (auto) | IMPLEMENTED |
| _windows_gpu() PowerShell CIM | IMPLEMENTED |
| _mac_gpu() system_profiler | IMPLEMENTED |
| _linux_gpu() nvidia-smi/lspci | IMPLEMENTED |
| GraphicsCapability dataclass | IMPLEMENTED |
| Fingerprint (SHA-256, deterministic) | IMPLEMENTED |
| Auto mode (detect + score) | IMPLEMENTED |

## 5. Problemas encontrados

### Observaciones (sin bugs criticos)

1. **ui.py es monolitico (8688 lineas)**
   - Todo el HUD esta en un solo archivo
   - Dificil de mantener y testear
   - Impacto: no funcional, solo mantenibilidad

2. **C (color constants) no se adapta a temas**
   - Los colores base estan hardcodeados como constantes de clase
   - ThemeManager existe pero C sigue siendo estatico
   - Impacto: los colores base no cambian con el tema

3. **_SysMetrics usa polling con timer**
   - CPU/RAM/GPU se leen en un thread separado
   - No hay mecanismo de pausa cuando el HUD esta minimizado
   - Impacto: consumo innecesario de recursos en background

4. **Voice options hardcodeadas**
   - VOICE_OPTIONS lista fija de 9 voces
   - No se sincroniza con voces disponibles en la API de Gemini
   - Impacto: si Gemini anade/retira voces, la lista queda desactualizada

5. **ui_locale.py tiene entradas duplicadas**
   - Algunas claves aparecen dos veces: "JARVIS: Command Center is open.", "RIGHT PANEL INFORMATION", etc.
   - No causa error (dict sobreescribe), pero indica falta de limpieza
   - Impacto: ninguno funcional

## 6. Cambios realizados

Ningun cambio en codigo de produccion — no se encontraron bugs que rompan funcionalidad existente.

## 7. Tests anadidos

| Archivo | Tests |
|---------|-------|
| `tests/test_block5_hud_states_avatar.py` | **39 tests** |

Cobertura:

**UI Locale (15 tests):**
- `TestTranslation` (4 tests): known key, unknown fallback, all strings, no empty
- `TestStateDisplay` (3 tests): known states, unknown fallback, all states covered
- `TestStatusAbbrev` (3 tests): known abbreviations, unknown truncation, short input

**Graphics Capability (14 tests):**
- `TestClassifyGpu` (7 tests): nvidia, intel, apple silicon, software, empty, AMD, Intel Arc
- `TestScoreGraphicsCapability` (7 tests): low/medium/high end, fingerprint, to_dict, none values, VRAM

**UI Helpers (14 tests):**
- `TestNormalizeGraphicsQuality` (5 tests): valid, aliases, case, None, invalid
- `TestGraphicsProfiles` (3 tests): existence, FPS ordering, required keys
- `TestVoiceOptions` (3 tests): existence, bidirectional maps, all voices in maps
- `TestColorConstants` (1 test): hex format validation
- `TestReadUISettings` (3 tests): missing file, valid file, corrupt file

**Physical (6 skipped, evidencia historica):**
- MainWindow launch, theme cycling, compact mode, state transitions y system tray.
- Cualquier caso especifico de avatar queda **DEFERRED BY USER — OUT OF CURRENT SCOPE**.

## 8. Tests ejecutados

```
python -m pytest tests/test_block5_hud_states_avatar.py --tb=short -q
```

## 9. Resultado

| Metrica | Valor |
|---------|-------|
| Passed | 39 |
| Failed | 0 |
| Skipped | 6 |
| Warnings | 0 |

Suite global despues de cambios:

| Metrica | Valor |
|---------|-------|
| Passed | 967 |
| Failed | 0 |
| Skipped | 93 |
| Warnings | 1 |

## 10. Pruebas fisicas pendientes

| ID | Area | Prueba | Estado |
|----|------|--------|--------|
| PHY-B5-001 | HUD | Arrancar MainWindow y verificar que el HUD se renderiza | PHYSICAL TEST REQUIRED |
| PHY-B5-002 | HUD | Ciclar temas (Ctrl+T) y verificar que los colores cambian | PHYSICAL TEST REQUIRED |
| PHY-B5-003 | HUD | Activar modo compacto (Ctrl+M) y verificar layout | PHYSICAL TEST REQUIRED |
| PHY-B5-004 | HUD | Verificar fullscreen (F11) y restauracion | PHYSICAL TEST REQUIRED |
| PHY-B5-005 | Estados | Verificar transicion IDLE→LISTENING→THINKING→SPEAKING | PHYSICAL TEST REQUIRED |
| PHY-B5-006 | Estados | Verificar estado MUTED y recovery | PHYSICAL TEST REQUIRED |
| PHY-B5-007 | Estados | Verificar estado ERROR y recovery | PHYSICAL TEST REQUIRED |
| PHY-B5-008 | Avatar | Verificar animacion holografica a diferentes calidades | DEFERRED BY USER — OUT OF CURRENT SCOPE |
| PHY-B5-009 | HUD | Verificar metricas de sistema (CPU/RAM/GPU) en HUD | PHYSICAL TEST REQUIRED |
| PHY-B5-010 | HUD | Verificar system tray icon y menu | PHYSICAL TEST REQUIRED |
| PHY-B5-011 | UI | Verificar FileDropZone con archivo real | PHYSICAL TEST REQUIRED |
| PHY-B5-012 | UI/Vision | Verificar VisionPreviewWindow con webcam | PHYSICAL TEST REQUIRED |

## 11. Riesgos o deuda tecnica

1. **ui.py monolitico** — 8688 lineas en un solo archivo, dificil de mantener
2. **Polling de metricas sin pausa** — consume recursos incluso cuando el HUD no esta visible
3. **Voces hardcodeadas** — lista fija que puede desincronizarse de la API
4. **Entradas duplicadas en ui_locale.py** — limpieza pendiente
5. **C colores estaticos** — no se adaptan a temas dinamicos

## 12. Archivos modificados

- `tests/test_block5_hud_states_avatar.py` (NUEVO — 39 tests)

Ningun archivo de produccion fue modificado.

## 13. Git

Pendiente de commit al finalizar todos los bloques.
