# NEST 68 — Cierre de pruebas de concurrencia Android (06/11/2026, 06:05)

## Resultado
**Código preparado y verificado, NO desplegado ni activado.** No se reinició ningún servicio ni se instaló ninguna APK. No se ejecutó ninguna orden real sobre Home Assistant.

### Hallazgos y correcciones en archivos de Ubuntu
1. Dos confirmaciones Android simultáneas dejaban `_request_channel="telegram_confirmed"` después de terminar: fallo reproducido con un test aislado que falló. **Corregido** con `asyncio.Lock` compartido con `ask_text` y un `ContextVar` temporal que no modifica el canal compartido para Android.
2. Los grupos Telegram pueden tener chat IDs negativos. El canal pendiente ahora se registra explícitamente como `android` o `telegram`; no se infiere por el signo del número. Probado.
3. El gateway obtenía un único `_last_pending_telegram_action` global: una segunda sesión podía sobrescribir la vista previa. Se añadió `_pending_android_by_owner` y `pending_android_action_for_owner()`, que comprueban canal, propietario y caducidad; `api_server.py` usa ese método si existe.
4. Los argumentos pendientes ahora se guardan con `deepcopy`; cambios posteriores en listas de destinos o parámetros HA no alteran lo pendiente de aprobación.
5. La protección implementada anteriormente sigue: acciones domésticas Android pasan a confirmación pendiente, `/api/tool/invoke` las rechaza, confirmación de un solo uso y rutina `confirm="false"` no activa dispositivos. La app Android incorpora diálogo de Confirmar/Cancelar y UUID de instalación como sesión.

### Pruebas
- **249 PASS; 7 warnings; 0 FAIL** en la batería de regresión aislada de Ubuntu: wakeword, gateway Android, bloque de permisos, Telegram, batch, confirmaciones, concurrencia e inventario de herramientas.
- `py_compile` y `git diff --check` sin errores.
- Prueba de fallo concurrente reproducido ANTES de la corrección y validado correctamente DESPUÉS.
- El endpoint HTTP E2E simulado verifica token, propietario, aprobación, cancelación y uso único, sin conexión a Gemini/HA real.

### APK de prueba generada
- Ruta: `/home/flako1312/apk_nueva_src/app/build/outputs/apk/debug/app-debug.apk`
- Tamaño: aprox. 18 MiB.
- `./gradlew :app:assembleDebug --offline --no-daemon --max-workers=2`: **BUILD SUCCESSFUL**.
- `apksigner verify`: firma APK v2 válida, 1 firmante.
- SHA-256: `76519a12b2cb1e55e184f2f2fd64a6c3ae781402395a62f0aeda84d3cbb9ae56`.
- No se ha instalado en ningún móvil/tablet. Es una APK DEBUG; verificar compatibilidad de firma con la instalada antes de actualizar.

### Copias y reversión
- `/home/flako1312/jarvis-headless-backups/android_home_confirm_20261106_0535/` contiene originales y parches de `main.py`, `api_server.py`, `actions/home_routine.py`, varios archivos de APK y diferencias de tests.
- Los repositorios Ubuntu headless y APK ya contenían modificaciones anteriores sin confirmar. **NO** hacer `git clean`, `git reset --hard`, ni commits indiscriminados. No se han alterado ni eliminado esos archivos.
- Los documentos de cierre se guardan en Git en Windows `C:\JARVIS`.

### Qué queda hasta el despliegue
1. Mantener servicios vivos y SOAK sin interrupciones; esperar autorización expresa del usuario para cualquier reinicio.
2. En ventana autorizada, validar backups y estabilidad; reiniciar **solo JARVIS Ubuntu** para cargar las correcciones, si no compromete SOAK.
3. Verificar el gateway con consultas inocuas y después pruebas supervisadas de confirmación; las acciones de luces requieren autorización expresa.
4. Verificar la firma de la APK existente, instalar una actualización compatible **solo con consentimiento**, probar Confirmar/Cancelar en dispositivo.
5. Riesgo residual: dos solicitudes solapadas **de la misma sesión** podrían compartir una vista previa reciente; la UI normalmente serializa, pero falta una prueba real multi-dispositivo tras el despliegue.
