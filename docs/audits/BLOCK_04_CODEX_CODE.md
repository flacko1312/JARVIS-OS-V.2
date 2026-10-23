# BLOCK 04 — CODEX (DEV AGENT) & CODE HELPER AUDIT

**Date**: 2026-10-15
**Auditor**: Claude Opus 4.6

---

## 1. Objetivo

Auditar completamente los subsistemas de desarrollo asistido por IA: Dev Agent (scaffolding de proyectos multi-archivo con planificacion Gemini, escritura en orden de dependencias, ejecucion automatica, loop de auto-fix, apertura en VSCode, instalacion de dependencias) y Code Helper (escritura/edicion/explicacion/ejecucion/build/optimizacion/debug visual de codigo, con deteccion automatica de intencion).

## 2. Estado inicial

- **867 passed, 0 failed, 84 skipped** en la suite tras Block 3
- Ningun test previo cubria dev_agent ni code_helper

## 3. Archivos inspeccionados

| Archivo | Lineas |
|---------|--------|
| `actions/dev_agent.py` | 608 |
| `actions/code_helper.py` | 580 |

## 4. Funciones existentes

### A — DEV AGENT (`dev_agent.py`)

| Funcion | Estado |
|---------|--------|
| `_plan_project()` Gemini AI project planning (JSON) | IMPLEMENTED |
| `_write_file()` per-file code generation with dependency context | IMPLEMENTED |
| `_run_project()` subprocess execution with timeout | IMPLEMENTED |
| `_fix_files()` Gemini-driven auto-fix per traceback | IMPLEMENTED |
| `_try_auto_install()` missing module auto-install | IMPLEMENTED |
| `_install_dependencies()` pip install with check | IMPLEMENTED |
| `_open_vscode()` VSCode launch (3 candidates) | IMPLEMENTED |
| `_classify_error()` error type categorization | IMPLEMENTED |
| `_has_error()` error detection (excluding timeouts) | IMPLEMENTED |
| `_parse_traceback()` file+line extraction from traceback | IMPLEMENTED |
| `_strip_fences()` markdown fence removal | IMPLEMENTED |
| `_is_rate_limit()` rate limit detection | IMPLEMENTED |
| `_build_project()` full orchestration pipeline | IMPLEMENTED |
| `dev_agent()` entry point with parameter dispatch | IMPLEMENTED |
| Dependency-order file writing | IMPLEMENTED |
| Rate limit retry (20s wait + skip) | IMPLEMENTED |
| MAX_FIX_ATTEMPTS = 5 | IMPLEMENTED |
| Multi-language support | PARTIALLY IMPLEMENTED |
| Test generation | NOT IMPLEMENTED |
| Git integration | NOT IMPLEMENTED |

### B — CODE HELPER (`code_helper.py`)

| Funcion | Estado |
|---------|--------|
| `code_helper()` entry point with action dispatch | IMPLEMENTED |
| Auto-detect intent (screen_debug/optimize/edit/run/build/explain/write) | IMPLEMENTED |
| `_write()` Gemini code generation + save | IMPLEMENTED |
| `_write_action()` with preview | IMPLEMENTED |
| `_edit_action()` Gemini code editing + save | IMPLEMENTED |
| `_explain_action()` Gemini code explanation | IMPLEMENTED |
| `_run_action()` script execution | IMPLEMENTED |
| `_run_file()` subprocess with interpreter map | IMPLEMENTED |
| `_build()` write→run→fix loop (3 attempts) | IMPLEMENTED |
| `_fix_code()` Gemini error fixing | IMPLEMENTED |
| `_optimize_action()` Gemini code optimization | IMPLEMENTED |
| `_screen_debug_action()` screenshot + Gemini vision analysis | IMPLEMENTED |
| `_resolve_save_path()` language→extension mapping | IMPLEMENTED |
| `_read_file()` with error handling | IMPLEMENTED |
| `_save_file()` with jarvis_file_stamp | IMPLEMENTED |
| `_preview()` truncated code preview | IMPLEMENTED |
| `_has_error()` error signal detection | IMPLEMENTED |
| `_detect_intent()` keyword-based intent classification | IMPLEMENTED |
| `_take_screenshot()` pyautogui capture | IMPLEMENTED |
| `_image_to_base64()` encoding | IMPLEMENTED |
| `_clean_code()` fence removal | IMPLEMENTED |
| Multi-interpreter support (py, js, ts, sh, ps1, rb, php) | IMPLEMENTED |
| Line count diff in optimize | IMPLEMENTED |

## 5. Problemas encontrados

### Observaciones (sin bugs criticos)

1. **dev_agent usa google.generativeai (legacy) mientras code_helper usa google.genai (nuevo)**
   - `_get_model()` en dev_agent: `genai.GenerativeModel(model_name)`
   - `_get_gemini()` en code_helper: `genai.GenerativeModel(model)`
   - `_screen_debug_action()`: `genai.Client(api_key=...)`
   - Mezcla de SDK legacy y nuevo en el mismo proyecto
   - Impacto: inconsistencia, posibles problemas de compatibilidad futura

2. **dev_agent._get_api_key() lee directamente del config JSON**
   - code_helper._get_api_key() usa `get_gemini_key()` del config_manager
   - Inconsistencia en la obtencion de credenciales
   - Impacto: si se cambia la ubicacion del API key, dev_agent se rompe

3. **_classify_error() orden de prioridad no intuitivo**
   - "ImportError" contiene "importerror" que matchea dependency_error antes que import_error
   - `ImportError: cannot import name 'foo'` se clasifica como dependency_error
   - Impacto: mensajes de fix potencialmente incorrectos pero no bloquea el fix loop

4. **code_helper._screen_debug_action() auto-aplica fix**
   - Si detecta un code block en la respuesta de Gemini, sobrescribe el archivo original
   - Sin confirmacion del usuario
   - Impacto: podria sobrescribir codigo correcto basandose en un analisis visual incorrecto

5. **Modelo fijo "gemini-2.5-flash" en ambos modulos**
   - No usa la configuracion global del sistema
   - Impacto: no se beneficia de upgrades automaticos del modelo

6. **Comentarios en turco en dev_agent.py (linea 328)**
   - `"""ModuleNotFoundError varsa eksik paketi otomatik kurmaya çalışır."""`
   - Inconsistencia con el resto del proyecto

## 6. Cambios realizados

Ningun cambio en codigo de produccion — no se encontraron bugs que rompan funcionalidad existente.

## 7. Tests anadidos

| Archivo | Tests |
|---------|-------|
| `tests/test_block4_codex_code.py` | **61 tests** |

Cobertura:

**Dev Agent (25 tests):**
- `TestStripFences` (4 tests): python fence, no fence, generic fence, empty
- `TestIsRateLimit` (3 tests): 429, quota, normal error
- `TestClassifyError` (5 tests): dependency, syntax, import, cannot-import-only, runtime, none
- `TestHasError` (3 tests): timeout not error, empty not error, traceback is error
- `TestParseTraceback` (2 tests): match project file, no match
- `TestDevAgentEntry` (3 tests): missing description, rate limit, plan failure
- `TestTryAutoInstall` (2 tests): detects missing module, no match
- `TestRunProject` (2 tests): timeout, command not found
- `TestInstallDependencies` (2 tests): no deps, already installed
- `TestOpenVSCode` (1 test): all candidates fail

**Code Helper (36 tests):**
- `TestCleanCode` (3 tests): python fence, no fence, empty
- `TestResolveSavePath` (4 tests): default python, explicit, absolute, language extensions
- `TestReadFile` (3 tests): no path, missing file, valid file
- `TestPreview` (2 tests): short code, long code
- `TestHasErrorCodeHelper` (2 tests): error detected, clean output
- `TestDetectIntent` (7 tests): screen_debug, optimize, explain, write, build, edit, run
- `TestCodeHelperDispatch` (9 tests): unknown action, write/edit/explain/run/build/optimize missing args
- `TestRunFile` (3 tests): unsupported extension, python run, timeout

**Physical (3 skipped):**
- TestScreenDebugPhysical: needs real screen + Gemini API
- TestDevAgentPhysical: full build, fix loop

## 8. Tests ejecutados

```
python -m pytest tests/test_block4_codex_code.py --tb=short -q
```

## 9. Resultado

| Metrica | Valor |
|---------|-------|
| Passed | 61 |
| Failed | 0 |
| Skipped | 3 |
| Warnings | 0 |

Suite global despues de cambios:

| Metrica | Valor |
|---------|-------|
| Passed | 928 |
| Failed | 0 |
| Skipped | 87 |
| Warnings | 1 |

## 10. Pruebas fisicas pendientes

| ID | Area | Prueba | Estado |
|----|------|--------|--------|
| PHY-B4-001 | Dev Agent | Crear proyecto multi-archivo real con Gemini | PHYSICAL TEST REQUIRED |
| PHY-B4-002 | Dev Agent | Verificar auto-fix loop con error real | PHYSICAL TEST REQUIRED |
| PHY-B4-003 | Dev Agent | Verificar apertura de VSCode | PHYSICAL TEST REQUIRED |
| PHY-B4-004 | Dev Agent | Verificar instalacion automatica de dependencias | PHYSICAL TEST REQUIRED |
| PHY-B4-005 | Code Helper | Generar codigo Python con Gemini y ejecutar | PHYSICAL TEST REQUIRED |
| PHY-B4-006 | Code Helper | Editar archivo existente con Gemini | PHYSICAL TEST REQUIRED |
| PHY-B4-007 | Code Helper | Screen debug con captura real + Gemini vision | PHYSICAL TEST REQUIRED |
| PHY-B4-008 | Code Helper | Optimizar codigo real con Gemini | PHYSICAL TEST REQUIRED |
| PHY-B4-009 | Code Helper | Build con fix loop completo | PHYSICAL TEST REQUIRED |

## 11. Riesgos o deuda tecnica

1. **Mezcla de SDKs de Gemini** — legacy `google.generativeai` en dev_agent vs nuevo `google.genai` en code_helper screen_debug
2. **Inconsistencia en obtencion de API key** — dev_agent lee JSON directo, code_helper usa config_manager
3. **Modelo fijo** — "gemini-2.5-flash" hardcoded, no configurable
4. **Screen debug auto-aplica fix sin confirmacion** — riesgo de sobrescribir codigo correcto
5. **Comentarios en turco** — inconsistencia idiomatica (linea 328 de dev_agent, linea 413 de code_helper)
6. **_classify_error() prioridad** — ImportError se clasifica como dependency en vez de import, afecta mensajes del fix loop

## 12. Archivos modificados

- `tests/test_block4_codex_code.py` (NUEVO — 61 tests)

Ningun archivo de produccion fue modificado.

## 13. Git

Pendiente de commit al finalizar todos los bloques.
