# BLOCK 01 — WINDOWS, FILES & BROWSER AUDIT

**Date**: 2026-10-15
**Auditor**: Claude Opus 4.6

---

## 1. Objetivo

Auditar completamente los subsistemas de control de Windows (programas, ventanas, teclado, raton), archivos (lectura, escritura, procesamiento de formatos) y navegador (Playwright). Verificar que el router diferencia correctamente entre "Abre Spotify" (Windows) y "Explicame que es Spotify" (conversacion).

## 2. Estado inicial

- **551 passed, 2 failed, 77 skipped** en la suite existente
- 2 fallos preexistentes en `test_screen_processor.py` (modelo vision default y mock de `raise_for_status`)
- Bug preexistente en `file_processor.py`: `pd.read_csv()` con parametro invalido `errors="replace"`
- Ningun test previo cubria computer_control, open_app, file_controller, browser_control ni el router classifier de forma unitaria

## 3. Archivos inspeccionados

| Archivo | Lineas |
|---------|--------|
| `actions/computer_control.py` | 491 |
| `actions/open_app.py` | 254 |
| `actions/file_controller.py` | 600 |
| `actions/file_processor.py` | 1045 |
| `actions/browser_control.py` | 893 |
| `actions/safe_text_entry.py` | ~40 (header) |
| `router/classifier.py` | 114 |
| `router/models.py` | 34 |
| `router/core.py` | 255 |
| `tests/conftest.py` | 22 |
| `tests/test_screen_processor.py` | ~330 |

## 4. Funciones existentes

### A — WINDOWS (`computer_control.py`, `open_app.py`)

| Funcion | Estado |
|---------|--------|
| type (teclado) | IMPLEMENTED |
| smart_type (limpiar + escribir) | IMPLEMENTED |
| click / double_click / right_click | IMPLEMENTED |
| move (raton) | IMPLEMENTED |
| drag | IMPLEMENTED |
| hotkey (combinaciones) | IMPLEMENTED |
| press (tecla individual) | IMPLEMENTED |
| scroll (up/down/left/right) | IMPLEMENTED |
| copy (clipboard read) | IMPLEMENTED |
| paste (clipboard write) | IMPLEMENTED |
| screenshot | IMPLEMENTED |
| wait | IMPLEMENTED |
| clear_field | IMPLEMENTED |
| focus_window (Win/Mac/Linux) | IMPLEMENTED |
| screen_find (IA visual) | IMPLEMENTED |
| screen_click (find + click) | IMPLEMENTED |
| random_data | IMPLEMENTED |
| user_data (memoria) | IMPLEMENTED |
| open_app (67 alias, 3 OS) | IMPLEMENTED |
| open_app fallback (Start Menu search) | IMPLEMENTED |

### B — ARCHIVOS (`file_controller.py`, `file_processor.py`)

| Funcion | Estado |
|---------|--------|
| list_files | IMPLEMENTED |
| create_file / create_folder | IMPLEMENTED |
| read_file (con truncado) | IMPLEMENTED |
| write_file (write/append) | IMPLEMENTED |
| rename_file | IMPLEMENTED |
| delete_file (papelera segura) | IMPLEMENTED |
| move_file / copy_file | IMPLEMENTED |
| find_files (nombre/extension) | IMPLEMENTED |
| get_largest_files | IMPLEMENTED |
| get_disk_usage | IMPLEMENTED |
| organize_desktop | IMPLEMENTED |
| get_file_info | IMPLEMENTED |
| open_file (OS default app) | IMPLEMENTED |
| file_processor: image (describe/ocr/resize/convert/compress) | IMPLEMENTED |
| file_processor: PDF (summarize/extract/to_word) | IMPLEMENTED |
| file_processor: DOCX/TXT (summarize/explain/reformat/word_count) | IMPLEMENTED |
| file_processor: CSV/XLSX (analyze/filter/sort/convert/stats) | IMPLEMENTED |
| file_processor: JSON (validate/format/analyze/to_csv) | IMPLEMENTED |
| file_processor: code (explain/review/fix/run/document) | IMPLEMENTED |
| file_processor: audio (transcribe/trim/convert/info) | IMPLEMENTED |
| file_processor: video (info/trim/extract_audio/frame/compress) | IMPLEMENTED |
| file_processor: archive (list/extract) | IMPLEMENTED |
| file_processor: PPTX (summarize/extract_text) | IMPLEMENTED |
| file_processor: unknown (text→API upload→binary fallback) | IMPLEMENTED |
| safe_path validation | IMPLEMENTED |
| path shortcuts (desktop/downloads/home etc.) | IMPLEMENTED |
| protected directory deletion guard | IMPLEMENTED |

### C — NAVEGADOR (`browser_control.py`)

| Funcion | Estado |
|---------|--------|
| go_to (URL) | IMPLEMENTED |
| search (Google/Bing/DuckDuckGo/Yandex) | IMPLEMENTED |
| click / smart_click | IMPLEMENTED |
| type_text / smart_type | IMPLEMENTED |
| fill_form | IMPLEMENTED |
| scroll | IMPLEMENTED |
| press key | IMPLEMENTED |
| get_text / get_url | IMPLEMENTED |
| new_tab / close_tab | IMPLEMENTED |
| screenshot | IMPLEMENTED |
| back / forward / reload | IMPLEMENTED |
| close browser | IMPLEMENTED |
| switch browser | IMPLEMENTED |
| list_browsers | IMPLEMENTED |
| close_all | IMPLEMENTED |
| Multi-browser support (Chrome/Edge/Firefox/Opera/Brave/Safari/Vivaldi) | IMPLEMENTED |
| Real user profile detection | IMPLEMENTED |
| JARVIS fallback profile | IMPLEMENTED |
| URL normalization (bare words → .com) | IMPLEMENTED |

## 5. Problemas encontrados

### Bugs corregidos

1. **`file_processor.py:455` — `pd.read_csv(errors=...)` invalido**
   - `errors` no es un parametro de `pd.read_csv()` en pandas moderno
   - Causaba crash para todo procesamiento CSV
   - **Corregido**: cambiado a `encoding_errors="replace"`

2. **`test_screen_processor.py:89` — modelo vision default desactualizado**
   - El test esperaba `qwen3-vl:4b` pero `vision_model.py` define `qwen3-vl:4b-instruct`
   - **Corregido**: actualizado el test

3. **`test_screen_processor.py:308` — `raise_for_status` ya no se usa**
   - El codigo de `screen_processor.py` cambio a usar `response.ok` en vez de `raise_for_status()`
   - **Corregido**: se establece `response.ok = True` en el mock

### Observaciones

4. **`file_processor.py:431` — bug logico en custom action fallback**
   - Cuando `action not in prompt_map`, se reasigna `action = "custom"` y luego `instruction = action`
   - Esto pierde el action original — `instruction` siempre sera `"custom"`
   - Impacto: acciones desconocidas en text docs pierden el nombre de la accion
   - Severidad: baja (el procesamiento aun funciona via fallback)

5. **Router classifier no tiene dominios para Gmail, multimedia, recordatorios, presentaciones**
   - `Domain` enum solo define: WINDOWS, FILES, VISION, MEMORY, HOME, DEVELOPMENT, KNOWLEDGE, LOCAL_AI, WEB, CONVERSATION
   - Falta: GMAIL, MULTIMEDIA, REMINDERS, PRESENTATIONS
   - Impacto: estas peticiones se redirigen a CONVERSATION (fallback) donde Gemini las procesa via tools

6. **`browser_control.py` — comentarios en turco** (lineas 348, 413, 737)
   - Inconsistencia con el resto del proyecto (espanol/ingles)
   - No es un bug funcional

## 6. Cambios realizados

| Archivo | Cambio |
|---------|--------|
| `actions/file_processor.py:455` | `errors="replace"` → `encoding_errors="replace"` |
| `tests/test_screen_processor.py:89` | Test actualizado: `qwen3-vl:4b` → `qwen3-vl:4b-instruct` |
| `tests/test_screen_processor.py:295-308` | Mock corregido: `response.ok = True` antes de la llamada |

## 7. Tests anadidos

| Archivo | Tests |
|---------|-------|
| `tests/test_block1_windows_files_browser.py` | **147 tests** |

Cobertura:
- `TestComputerControlDispatch` (18 tests): dispatch table, acciones, pyautogui, safe_type
- `TestSafeScreenshotPath` (4 tests): paths seguros, fallback
- `TestScreenshot` (1 test): captura con mock
- `TestOpenAppNormalize` (5 tests): alias, passthrough, case
- `TestOpenApp` (6 tests): launch, fallo, excepcion, logging
- `TestFileControllerHelpers` (5 tests): format_size, resolve_path, is_safe_path
- `TestFileControllerCRUD` (17 tests): create/read/write/rename/find/info/disk/access
- `TestFileControllerSpecialChars` (3 tests): espacios, unicode, caracteres especiales
- `TestFileControllerDispatch` (3 tests): unknown, list, create_file
- `TestFileProcessorDetectType` (30 parametrized): todas las extensiones
- `TestFileProcessorResolvePath` (4 tests): existente, vacio, relativo, inexistente
- `TestFileProcessorHelpers` (3 tests): file_size_str, output_path
- `TestFileProcessorDispatch` (10 tests): no path, not found, word_count, JSON, CSV, code, archive, image
- `TestBrowserNormalizeURL` (6 tests): URLs, bare words, about:blank
- `TestBrowserControlDispatch` (3 tests): unknown, list, close_all
- `TestRouterWindowsVsConversation` (11 tests): "Abre Spotify" vs "Explicame Spotify"
- `TestRouterOtherDomains` (9 tests): web, home, memory, vision, dev, local_ai, files, fallback, ambiguity
- `TestRouterConfidence` (3 tests): confianza, fallback, raw_input

## 8. Tests ejecutados

```
python -m pytest tests/test_block1_windows_files_browser.py --tb=short -q
```

## 9. Resultado

| Metrica | Valor |
|---------|-------|
| Passed | 147 |
| Failed | 0 |
| Skipped | 0 |
| Warnings | 1 (DeprecationWarning de google.genai) |

Suite global despues de cambios:

| Metrica | Valor |
|---------|-------|
| Passed | 700 |
| Failed | 0 |
| Skipped | 77 |
| Warnings | 1 |

## 10. Pruebas fisicas pendientes

| ID | Area | Prueba | Estado |
|----|------|--------|--------|
| PHY-B1-001 | Windows | Ejecutar "Abre Spotify" y verificar que Spotify se abre | PHYSICAL TEST REQUIRED |
| PHY-B1-002 | Windows | Ejecutar "Cierra Spotify" y verificar que se cierra | PHYSICAL TEST REQUIRED |
| PHY-B1-003 | Windows | Verificar focus_window con ventana real | PHYSICAL TEST REQUIRED |
| PHY-B1-004 | Windows | Verificar screenshot real se guarda correctamente | PHYSICAL TEST REQUIRED |
| PHY-B1-005 | Windows | Verificar hotkeys (Ctrl+C, Alt+Tab) en apps reales | PHYSICAL TEST REQUIRED |
| PHY-B1-006 | Windows | Verificar screen_find con Gemini Vision real | PHYSICAL TEST REQUIRED |
| PHY-B1-007 | Archivos | Procesar PDF real con Gemini (summarize) | PHYSICAL TEST REQUIRED |
| PHY-B1-008 | Archivos | Procesar imagen real (describe) | PHYSICAL TEST REQUIRED |
| PHY-B1-009 | Archivos | Procesar DOCX con python-docx | PHYSICAL TEST REQUIRED |
| PHY-B1-010 | Navegador | Abrir Chrome via Playwright con perfil real | PHYSICAL TEST REQUIRED |
| PHY-B1-011 | Navegador | Navegar a URL, verificar contenido | PHYSICAL TEST REQUIRED |
| PHY-B1-012 | Navegador | Busqueda en Google, verificar resultados | PHYSICAL TEST REQUIRED |
| PHY-B1-013 | Navegador | Multiples pestanas, back, forward, reload | PHYSICAL TEST REQUIRED |
| PHY-B1-014 | Navegador | Timeout de navegacion/pagina no disponible | PHYSICAL TEST REQUIRED |
| PHY-B1-015 | Navegador | Recuperacion despues de error | PHYSICAL TEST REQUIRED |

## 11. Riesgos o deuda tecnica

1. **CSV processing crasheaba en produccion** — bug de `errors` parametro fue corregido
2. **Router classifier carece de dominios especificos** para Gmail, multimedia, recordatorios — depende de Gemini fallthrough
3. **Comentarios en turco** en browser_control.py — inconsistencia menor
4. **Bug logico en custom action text docs** — severity baja, action name se pierde
5. **`open_app` Start Menu fallback** usa `pyautogui.write()` que no soporta caracteres no-ASCII — podria fallar con apps con nombre en espanol/unicode

## 12. Archivos modificados

- `actions/file_processor.py` (1 linea)
- `tests/test_screen_processor.py` (2 lineas)
- `tests/test_block1_windows_files_browser.py` (NUEVO — 147 tests)

## 13. Git

Pendiente de commit al finalizar todos los bloques.
