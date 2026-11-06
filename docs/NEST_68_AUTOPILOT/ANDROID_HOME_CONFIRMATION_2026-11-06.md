# Sesión NEST 68 — Android: confirmación doméstica (6 noviembre 2026)

## Resultado técnico
Se preparó e integró EN EL CÓDIGO de JARVIS Ubuntu una barrera para que las llamadas desde canal Android a `lilith_home_action` y `batch_home_action`, y las rutinas con `confirm=true`, NO ejecuten acciones físicas inmediatamente. En su lugar, guardan los argumentos exactos como acción pendiente con identificador aleatorio, propietario de sesión y caducidad de cinco minutos; la respuesta `/api/chat` devuelve `pending_action`. Los endpoints `/api/action/confirm` y `/api/action/cancel` utilizan el mecanismo de confirmación existente, con consumo de un solo uso. Las confirmaciones del canal equivocado son rechazadas. El endpoint directo `/api/tool/invoke` rechaza herramientas de control del hogar con 403 (`confirm_required=true`).

Se corrigió además `actions/home_routine.py`: `confirm="false"` ya NO es tratado como verdadero por la función. Se añadió parsing afirmativo estricto. La UI de la APK Android tiene ahora código para mostrar un diálogo de confirmación/cancelación, llamar a los endpoints correspondientes y reflejar el resultado.

## Archivos Ubuntu modificados, SIN REINICIAR EL SERVICIO
- `/home/flako1312/jarvis-headless/main.py`: gate de canal Android.
- `/home/flako1312/jarvis-headless/api_server.py`: bloqueo de invocaciones directas de domótica.
- `/home/flako1312/jarvis-headless/actions/home_routine.py`: parseo estricto de confirmación.
- `/home/flako1312/jarvis-headless/core/android_home_confirmation.py`: helper puro de política y vista previa.
- `/home/flako1312/jarvis-headless/tests/test_android_home_confirmation_policy.py`: pruebas de política, propietario, caducidad, replay y cancelación.
- `/home/flako1312/jarvis-headless/tests/test_android_home_confirmation_e2e.py`: servidor HTTP simulado con sesión Android y sin HA real.
- `/home/flako1312/jarvis-headless/tests/test_headless_block1.py`: inventario HEADLESS actualizado a las herramientas NEST 68.

## Fuentes APK modificadas (NO INSTALADAS EN DISPOSITIVOS)
- `.../data/api/Dto.kt`
- `.../data/api/JarvisApi.kt`
- `.../data/JarvisRepository.kt`
- `.../data/AppContainer.kt` (vincula SettingsStore a la sesión Android)
- `.../ui/ViewModels.kt`
- `.../ui/screens/ChatScreen.kt`
Ruta raíz: `/home/flako1312/apk_nueva_src/app/src/main/java/com/lilith/hub/`.

## Verificaciones realizadas
- Suite de regresión seleccionada: **197 passed, 7 warnings, 0 failures** (wakeword, gateway, permisos, control múltiple, HEADLESS profile, nuevas pruebas).
- HTTP E2E completamente simulado: pendiente, confirmación de sesión correcta, denegación a otra sesión, confirmación única, cancelación y autenticación.
- Compilación Kotlin: `./gradlew :app:compileDebugKotlin --offline --no-daemon --max-workers=2` → **BUILD SUCCESSFUL** en dos ejecuciones, incluida la revisión con sesión persistente por instalación.
- `py_compile`, `git diff --check` correctos.
- Health JARVIS Ubuntu: OK/STANDBY. LILITH: online, BD y MQTT correctos.
- No hubo POST a dispositivos reales, ninguna instalación Android y ningún reinicio de servicios.

## Precauciones y siguientes pasos
- **NO DECLARAR DESPLEGADO.** El proceso JARVIS en ejecución no se reinició. Todavía utiliza código previamente cargado.
- La APK instalada tampoco recibió una nueva versión. La compilación es solo de fuentes, no validación física.
- **RESUELTO EN CÓDIGO APK:** `JarvisRepository` utiliza `SettingsStore.deviceUuid` (UUID persistente que Android guarda en DataStore) como sesión `jarvis-...` tanto en `/api/chat` como en `/api/action/confirm` y `/api/action/cancel`. Separamos así el propietario entre instalaciones. Pendiente comprobarlo físicamente en la APK instalada.
- Ubuntu tiene numerosos cambios preexistentes en Git y archivos sin seguimiento de otros trabajos. NO hacer `git reset --hard`, `git clean`, commit masivo ni sobreescritura.
- Copias exactas de los archivos anteriores y parches individuales generados bajo `/home/flako1312/jarvis-headless-backups/android_home_confirm_20261106_0535/` con permisos restrictivos. Son la vía de reversión.
- No reiniciar hasta comprobar el SOAK, preparar despliegue de APK, autorización del usuario y probar físicamente el flujo.
- Siguiente bloque seguro: testear concurrencia entre `/api/chat` y confirmaciones, preparar despliegue en una ventana sin SOAK e instalar la APK actualizada solo tras aprobación. Después, pruebas físicas supervisadas.
