# Auditoría de autorización de control múltiple — 2026-11-06 05:10

## Alcance comprobado
- Ubuntu `core/headless_permissions.py`: `batch_home_action/*` figura como `SAFE_WRITE`.
- Ubuntu `api_server.py`: POST `/api/tool/invoke` comprueba autenticación y permisos; `_dispatch_tool` **no tiene rama** `batch_home_action`. Una llamada directa autenticada devuelve 400, no actúa sobre HA.
- Ubuntu `api_server.py`: POST `/api/chat` autenticado entra por `jarvis.ask_text(..., channel="android")`.
- Ubuntu `main.py`: `_execute_tool` tiene una ruta de confirmación para canal Telegram; no se identificó control equivalente para `android` previo a `batch_home_action`; este despacho sí llama a `batch_home_action_async`.
- Ubuntu `actions/batch_home_action.py`: valida la acción como `turn_on` o `turn_off`; resuelve cada destino con LILITH y, si `resolved`, llama a `client.home_action`, sin exigir bandera explícita de confirmación.
- LILITH mantiene una barrera independiente de permisos/allowlist para las operaciones sobre dispositivos. No se ha probado evasión de esa barrera ni se ha ordenado nada físicamente.

## Pruebas herméticas, sin dispositivos ni producción
1. Servidor HTTP efímero `127.0.0.1` con token ficticio: POST `/api/tool/invoke` sin autorización -> 401.
2. El mismo servidor, token ficticio, `batch_home_action` -> 400 `not available via API`.
3. El mismo servidor sin instancia de JARVIS, POST `/api/chat` -> 503 `JARVIS not initialized`. Esta prueba NO verifica confirmación de Gemini ni acciones Android reales.
4. `tests/test_batch_home_action.py`: 17/17 PASS con cliente simulado.
Primer intento del script hermético falló por un error de comillas de impresión; se corrigió y las tres comprobaciones pasaron.

## Riesgo y próxima tarea
Una orden natural enviada con un token válido a `/api/chat` **puede llegar** al despacho de control múltiple sin que se identifique una confirmación obligatoria específica del canal Android. No se afirma que esto eluda las autorizaciones de LILITH. Evitar clasificar como demostrada la ejecución real mientras no haya pruebas del flujo completo y la política del cliente.

Preparar tests sin efectos para verificar si el canal Android exige confirmación previa al `home_action`, y diseñar una mitigación que conserve la compatibilidad con la APK. No modificar aún permisos, servicios, doble Alexa, SOAK ni dispositivos físicos.
