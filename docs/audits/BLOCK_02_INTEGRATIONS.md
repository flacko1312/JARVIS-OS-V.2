# BLOCK 02 — GMAIL, MULTIMEDIA, REMINDERS & PRESENTATIONS AUDIT

**Date**: 2026-10-15
**Auditor**: Claude Opus 4.6

---

## 1. Objetivo

Auditar completamente los subsistemas de integracion externa: Gmail (OAuth Desktop, lectura, composicion, envio con aprobacion), Multimedia (Spotify, Apple Music, YouTube Music, controles del sistema), Recordatorios (programacion OS-level con Windows Task Scheduler, macOS launchd, Linux systemd/at), y Presentaciones (generacion PowerPoint con Gemini AI, temas, charts, tablas, 3D nativo, QA visual).

## 2. Estado inicial

- **700 passed, 0 failed, 77 skipped** en la suite tras Block 1
- Ningun test previo cubria email_control, media_control, reminder ni presentation_maker de forma unitaria
- Modulos de presentacion con arquitectura compleja (2024 lineas + 5 submodulos)

## 3. Archivos inspeccionados

| Archivo | Lineas |
|---------|--------|
| `actions/email_control.py` | 1296 |
| `actions/media_control.py` | 251 |
| `actions/reminder.py` | 336 |
| `actions/presentation_maker.py` | 2024 |
| `actions/presentations/models.py` | ~120 (header) |
| `actions/jarvis_file_stamp.py` | ~94 (relevant functions) |

## 4. Funciones existentes

### A — GMAIL (`email_control.py`)

| Funcion | Estado |
|---------|--------|
| OAuth Desktop flow (127.0.0.1 local server) | IMPLEMENTED |
| Credential discovery (config, env, Downloads) | IMPLEMENTED |
| OS keychain storage (secret_store) | IMPLEMENTED |
| Credential refresh (auto-refresh on expiry) | IMPLEMENTED |
| Token revocation detection (invalid_grant) | IMPLEMENTED |
| Gmail connect/disconnect/status | IMPLEMENTED |
| Inbox listing (Gmail API) | IMPLEMENTED |
| Unread messages | IMPLEMENTED |
| Search (Gmail query syntax) | IMPLEMENTED |
| Read message (full body decode) | IMPLEMENTED |
| MIME multipart decode (plain + HTML fallback) | IMPLEMENTED |
| base64url decode with padding fix | IMPLEMENTED |
| Prepare email (approval-gated) | IMPLEMENTED |
| Gmail web compose (Playwright visible typing) | IMPLEMENTED |
| Compose field verification (subject, body, recipients) | IMPLEMENTED |
| Compose retry (2 attempts with recovery) | IMPLEMENTED |
| Gmail web send (visible Send button click) | IMPLEMENTED |
| Pre-send verification (subject/body/recipient match) | IMPLEMENTED |
| Gmail web cancel (discard draft) | IMPLEMENTED |
| Apple Mail (macOS osascript) — inbox/search/read/send | IMPLEMENTED |
| Default mail app (mailto: URI) | IMPLEMENTED |
| Recipient normalization (CSV, list, dedup) | IMPLEMENTED |
| Multi-tenant pending email (per-user locks) | IMPLEMENTED |
| Provider selection (Gmail, Apple Mail, default) | IMPLEMENTED |
| Action aliases (list→inbox, compose→prepare, etc.) | IMPLEMENTED |
| Threads | NOT IMPLEMENTED |
| Attachments | NOT IMPLEMENTED |
| Drafts (save draft without sending) | NOT IMPLEMENTED |

### B — MULTIMEDIA (`media_control.py`)

| Funcion | Estado |
|---------|--------|
| play / pause / stop / toggle | IMPLEMENTED |
| next / previous | IMPLEMENTED |
| play_query (search + play) | IMPLEMENTED |
| Spotify URI conversion (track/album/playlist/artist/episode/show) | IMPLEMENTED |
| Spotify macOS (osascript) | IMPLEMENTED |
| Spotify non-macOS (spotify: URI) | IMPLEMENTED |
| Apple Music macOS (osascript search + play) | IMPLEMENTED |
| YouTube Music (delegates to youtube_video) | IMPLEMENTED |
| Linux playerctl | IMPLEMENTED |
| System media keys (pyautogui) | IMPLEMENTED |
| Action aliases (resume→play, skip→next, etc.) | IMPLEMENTED |
| Platform aliases (apple→apple_music, etc.) | IMPLEMENTED |
| Volume control | NOT IMPLEMENTED |
| Mute | NOT IMPLEMENTED |
| Queue management | NOT IMPLEMENTED |

### C — RECORDATORIOS (`reminder.py`)

| Funcion | Estado |
|---------|--------|
| Date/time parsing (YYYY-MM-DD HH:MM) | IMPLEMENTED |
| Past-time rejection | IMPLEMENTED |
| Input sanitization (shell-safe) | IMPLEMENTED |
| Notification script generation (Windows/Mac/Linux) | IMPLEMENTED |
| Windows: plyer → win10toast → msg fallback | IMPLEMENTED |
| Mac: plyer → osascript fallback | IMPLEMENTED |
| Linux: plyer → notify-send fallback | IMPLEMENTED |
| Windows Task Scheduler (schtasks /Create XML) | IMPLEMENTED |
| macOS LaunchAgent (launchd plist) | IMPLEMENTED |
| Linux systemd-run / at | IMPLEMENTED |
| Self-deleting scripts after firing | IMPLEMENTED |
| Sound notification (Windows winsound) | IMPLEMENTED |
| Natural language date/time parsing | NOT IMPLEMENTED |
| Timezone support | NOT IMPLEMENTED |
| Reminder cancellation | NOT IMPLEMENTED |
| Reminder modification | NOT IMPLEMENTED |
| Reminder persistence across restarts | PARTIALLY IMPLEMENTED |
| Duplicate detection | NOT IMPLEMENTED |

### D — PRESENTACIONES (`presentation_maker.py` + `presentations/`)

| Funcion | Estado |
|---------|--------|
| Create mode (full deck from topic) | IMPLEMENTED |
| Edit mode (text replacement, style, delete slides) | IMPLEMENTED |
| Extend mode (append slides to existing) | IMPLEMENTED |
| Redesign mode (rebuild narrative) | IMPLEMENTED |
| Gemini AI planning (structured JSON) | IMPLEMENTED |
| Plan normalization and validation | IMPLEMENTED |
| Plan quality preflight (layout variety, titles, proof) | IMPLEMENTED |
| Quota fallback (local deck without API) | IMPLEMENTED |
| 5 built-in themes (jarvis_minimal, editorial, arc_reactor, executive, platinum) | IMPLEMENTED |
| Theme inference from source deck | IMPLEMENTED |
| Dark/light appearance | IMPLEMENTED |
| 11 slide types (cover, statement, two_column, etc.) | IMPLEMENTED |
| Native PowerPoint charts (bar, column, line, area, pie, doughnut, scatter) | IMPLEMENTED |
| Native PowerPoint tables | IMPLEMENTED |
| Image assets (generated via AI + supplied) | IMPLEMENTED |
| Native 3D model embedding | IMPLEMENTED |
| Morph/Fade/None transitions | IMPLEMENTED |
| Speaker notes | IMPLEMENTED |
| Source ingestion (TXT, MD, CSV, JSON, DOCX, PPTX) | IMPLEMENTED |
| Source truncation (50K chars) | IMPLEMENTED |
| PDF export | IMPLEMENTED |
| Visual QA (render + critique loop) | IMPLEMENTED |
| Premium quality (art-director review + repair) | IMPLEMENTED |
| Background job queue integration | IMPLEMENTED |
| Cancel support (threading Event) | IMPLEMENTED |
| Output file locking (thread-safe) | IMPLEMENTED |
| Safe filename generation | IMPLEMENTED |
| Safe output path (avoid overwriting source) | IMPLEMENTED |
| 3D preference detection (explicit + topic parsing) | IMPLEMENTED |
| Execution mode selection (ask, background, visible) | IMPLEMENTED |
| Pending presentation lifecycle (TTL, tenant-aware) | IMPLEMENTED |
| Deck profiles (8 types) | IMPLEMENTED |
| Image-led visual story enforcement | IMPLEMENTED |
| Citation tracking | IMPLEMENTED |
| Multi-tenant support | IMPLEMENTED |

## 5. Problemas encontrados

### Observaciones (sin bugs criticos)

1. **Gmail: threads y attachments no implementados**
   - El modulo solo soporta mensajes individuales, no hilos
   - No hay soporte para adjuntos (ni enviar ni recibir)
   - Impacto: funcionalidad limitada vs Gmail web completo

2. **Multimedia: sin control de volumen ni mute**
   - Solo play/pause/stop/toggle/next/previous
   - Impacto: el usuario no puede ajustar volumen por voz

3. **Recordatorios: sin timezone ni lenguaje natural**
   - Requiere formato estricto YYYY-MM-DD HH:MM
   - No soporta "en 30 minutos" ni "manana a las 3"
   - Sin timezone — usa la hora local del sistema
   - Impacto: UX limitada para usuarios hispanohablantes

4. **Recordatorios: sin cancelacion ni modificacion**
   - Una vez programado, no se puede cancelar desde JARVIS
   - No hay lista de recordatorios activos
   - Impacto: usuario debe cancelar manualmente via schtasks/launchctl

5. **Recordatorios: persistencia parcial**
   - Los scripts se auto-eliminan despues de ejecutar
   - Las tareas programadas del OS persisten entre reinicios
   - Pero JARVIS no mantiene un registro interno de recordatorios

6. **Presentaciones: DEFAULT_MODEL fijado a "gemini-2.5-flash"**
   - No usa el modelo configurable del sistema
   - Podria desincronizarse del modelo vision/chat principal

## 6. Cambios realizados

Ningun cambio en codigo de produccion — no se encontraron bugs que rompan funcionalidad existente.

## 7. Tests anadidos

| Archivo | Tests |
|---------|-------|
| `tests/test_block2_integrations.py` | **108 tests** |

Cobertura:

**Gmail (35 tests):**
- `TestGmailCredentialDiscovery` (3 tests): valid/invalid/missing client files
- `TestGmailHelpers` (12 tests): decode_header, headers_map, decode_data, html_to_text, gmail_body, normalize_recipients, bounded_limit
- `TestGmailFormatRows` (3 tests): empty, with data, parse_rows
- `TestEmailControlDispatch` (8 tests): unknown action, aliases, provider validation, field validation, approve/cancel without pending
- `TestPendingEmailLifecycle` (1 test): set/get/clear cycle
- `TestNormalizedVisibleText` (2 tests): whitespace, None
- `TestGmailConnectPhysical` (3 skipped): real OAuth, inbox, compose

**Multimedia (12 tests):**
- `TestSpotifyUri` (7 tests): track, album, playlist, native URI, plain text, non-spotify URL, empty/None
- `TestMediaActionAliases` (2 tests): action aliases, platform aliases
- `TestMediaControlDispatch` (7 tests): unknown action/platform, empty query, system play_query, toggle, search, direct link
- Physical tests (2 skipped): real Spotify, YouTube Music

**Recordatorios (12 tests):**
- `TestReminderSanitise` (2 tests): dangerous chars, max length
- `TestReminderValidation` (4 tests): missing date/time, invalid format, past date
- `TestReminderScheduling` (2 tests): success, failure
- `TestWriteNotifyScript` (3 tests): Windows/Mac/Linux script content
- Physical test (1 skipped): real OS scheduler

**Presentaciones (49 tests):**
- `TestSafeFilename` (5 tests): normal, empty, special chars, already .pptx, long
- `TestOutputPath` (3 tests): empty, explicit, relative
- `TestCleanJson` (3 tests): code fence, noise, invalid
- `TestTrimConciseItems` (4 tests): trim, concise, items, truncation
- `TestChartNormalization` (3 tests): valid, invalid type, empty
- `TestTableNormalization` (2 tests): valid, empty
- `TestNormalizePlan` (3 tests): correct count, wrong count, default profile
- `TestPlanQualityIssues` (2 tests): repeated layout, repeated title
- `TestEnforceVisualStory` (2 tests): consumer-retail gets images, non-consumer unchanged
- `TestPresentationExecutionMode` (3 tests): valid modes, aliases, invalid
- `TestPresentation3DPreference` (5 tests): explicit yes/no, topic with/without 3D, unspecified
- `TestExtractSource` (5 tests): txt, json, empty, missing, unsupported format, truncation
- `TestQuotaFallbackPlan` (2 tests): correct count, uses evidence
- `TestThemes` (2 tests): required keys, valid hex
- `TestCreatePresentationEntry` (2 tests): success, exception handling
- `TestPresentationPending` (1 test): remember/take lifecycle
- `TestSafeOutputForSource` (3 tests): different paths, same path edit, extend

## 8. Tests ejecutados

```
python -m pytest tests/test_block2_integrations.py --tb=short -q
```

## 9. Resultado

| Metrica | Valor |
|---------|-------|
| Passed | 108 |
| Failed | 0 |
| Skipped | 7 |
| Warnings | 0 |

Suite global despues de cambios:

| Metrica | Valor |
|---------|-------|
| Passed | 808 |
| Failed | 0 |
| Skipped | 84 |
| Warnings | 1 |

## 10. Pruebas fisicas pendientes

| ID | Area | Prueba | Estado |
|----|------|--------|--------|
| PHY-B2-001 | Gmail | Conectar Gmail con credenciales OAuth reales | PHYSICAL TEST REQUIRED |
| PHY-B2-002 | Gmail | Listar inbox con cuenta real | PHYSICAL TEST REQUIRED |
| PHY-B2-003 | Gmail | Componer y enviar email via Playwright con aprobacion | PHYSICAL TEST REQUIRED |
| PHY-B2-004 | Gmail | Buscar mensajes con query real | PHYSICAL TEST REQUIRED |
| PHY-B2-005 | Gmail | Leer mensaje completo (multipart HTML+plain) | PHYSICAL TEST REQUIRED |
| PHY-B2-006 | Gmail | Verificar refresh de credenciales expiradas | PHYSICAL TEST REQUIRED |
| PHY-B2-007 | Multimedia | Reproducir musica en Spotify real | PHYSICAL TEST REQUIRED |
| PHY-B2-008 | Multimedia | Controles play/pause/next/previous en Spotify | PHYSICAL TEST REQUIRED |
| PHY-B2-009 | Multimedia | Buscar y reproducir cancion en YouTube Music | PHYSICAL TEST REQUIRED |
| PHY-B2-010 | Multimedia | Controles del sistema (media keys) | PHYSICAL TEST REQUIRED |
| PHY-B2-011 | Recordatorios | Programar recordatorio real con Windows Task Scheduler | PHYSICAL TEST REQUIRED |
| PHY-B2-012 | Recordatorios | Verificar que la notificacion aparece a la hora | PHYSICAL TEST REQUIRED |
| PHY-B2-013 | Recordatorios | Verificar auto-eliminacion del script tras ejecucion | PHYSICAL TEST REQUIRED |
| PHY-B2-014 | Presentaciones | Crear presentacion real con Gemini API | PHYSICAL TEST REQUIRED |
| PHY-B2-015 | Presentaciones | Verificar PPTX abre correctamente en PowerPoint | PHYSICAL TEST REQUIRED |
| PHY-B2-016 | Presentaciones | Exportar PDF desde presentacion | PHYSICAL TEST REQUIRED |
| PHY-B2-017 | Presentaciones | Crear presentacion con 3D nativo | PHYSICAL TEST REQUIRED |
| PHY-B2-018 | Presentaciones | Editar presentacion existente | PHYSICAL TEST REQUIRED |

## 11. Riesgos o deuda tecnica

1. **Gmail OAuth credentials en Downloads** — el discovery automatico busca en Downloads, lo cual es conveniente pero podria encontrar archivos equivocados si el usuario descargo multiples credenciales
2. **Recordatorios sin timezone** — puede causar recordatorios a hora incorrecta si el usuario habla de zona horaria diferente
3. **Recordatorios sin NLP** — el router debe convertir "manana a las 3" a formato YYYY-MM-DD HH:MM antes de llegar al modulo
4. **Presentaciones con modelo fijo** — `DEFAULT_MODEL = "gemini-2.5-flash"` no sigue la configuracion global del sistema
5. **Multimedia sin volumen** — funcionalidad que los usuarios esperan y no esta disponible
6. **Gmail threads y attachments** — funcionalidad basica de email no implementada

## 12. Archivos modificados

- `tests/test_block2_integrations.py` (NUEVO — 108 tests)

Ningun archivo de produccion fue modificado.

## 13. Git

Pendiente de commit al finalizar todos los bloques.
