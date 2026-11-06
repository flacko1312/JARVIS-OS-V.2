# JARVIS — criterios de cierre, sin APK ni cambios en LILITH
Fecha: 6 noviembre 2026. Alcance: `C:\JARVIS` (Windows) y `/home/flako1312/jarvis-headless` (Ubuntu).

## Objetivo
Concluir capacidades, herramientas y calidad de los DOS asistentes fijos: Windows en despacho, Ubuntu 24/7 en comedor/cocina. LILITH Core sigue siendo propietario de memoria persistente, rutinas y autorizaciones de HA. Su desarrollo M-3 a M-9 queda separado. No desarrollar APK Android, ni modificar el repositorio LILITH, ni activar dispositivos físicos para simular progreso.

## Línea base verificada
Fuente: `STATUS_SNAPSHOT.json` v12, más antigua que los cambios de hoy. Su partición GLOBAL exclusiva es:
- **43/68 OPERATIVO registrado**; no equivale a 43 funciones físicamente validadas.
- **9 PARCIAL**: A2 (wake word), B13/B14/B15 (persianas, termostatos, climatización), E44/E45 (Google Calendar/citas), E49 (tráfico), G67 (audio local Ubuntu), G68 (puentes).
- **2 AUSENTE**: B22 (automatizaciones por eventos, autoridad LILITH/HA); C35 (multiroom real).
- **4 BLOQUEADO**: B18 (Google Home), D36 (llamadas sin SIP), G62/G63 (API y script propietarios).
- **10 REQUIERE HARDWARE**: B16/B17, C32/C33, F55–F60.
Las notas del `MASTER_PLAN.md` contienen cifras más antiguas y referencias a la APK: NO utilizarlas como prueba de cierre. No alterar etiquetas globales sin nueva prueba material.

## Implementado/probado en este ciclo
- Herramientas principales temporizador/calendario/tráfico/radio/podcast/alarma/transporte/control múltiple: **Ubuntu 259/259 PASS; Windows 260/260 PASS**. Estas son pruebas automatizadas, no pruebas de audio ni de dispositivos físicos.
- Fallo real Windows corregido: el temporizador pronunciaba la alerta después de la notificación OS, que podía bloquear la voz. Se cambió el orden y se protegieron las pruebas de sonidos de OS. Commit Windows `333625b`.
- Conversación/persistencia/protección de efectos: **Windows 102/102 PASS; Ubuntu 100/100 PASS** en suites seleccionadas.
- Nuevo test de contrato de enrutamiento: las 36 acciones HEADLESS de Ubuntu tienen una rama de despacho en código, y Windows verifica que cada nombre declarado en TOOL_DECLARATIONS tiene rama. **1/1 PASS por equipo**. Es verificación estática, no E2E de Gemini.
- Ambos equipos JARVIS/Ubuntu y LILITH health anteriormente OK; no reinicios ni pruebas físicas.

## Para considerar CERRADO el software de JARVIS
1. Los nombres anunciados a Gemini deben tener despachador, parámetros validados, tests unitarios y manejo de error, sin publicidad falsa de capacidades. Ya hay tests estáticos añadidos para rutas.
2. Las órdenes naturales deben invocar la herramienta adecuada en los dos JARVIS (no solo estar declaradas); validar con Gemini en sesiones reales cuando sea seguro, sin manipular HA.
3. Mantener la autoridad LILITH sobre memoria/rutinas/domótica: JARVIS no duplicará motores de automatización ni recuerdos persistentes.
4. No tocar SOAK/producción. Todo cambio que necesite reinicio queda **PREPARADO, NO DESPLEGADO** hasta permiso explícito.
5. Validaciones físicas de Ubuntu (micrófono, altavoces, wakeword, TTS, conversación continua con ruido, radio) requieren presencia del usuario; hasta entonces código y pruebas aisladas solamente.
6. E44/E45 necesitan OAuth Calendar para servicio Google; E49 requiere clave ORS para rutas reales. No marcar éxito solo por instalar código.
7. B22 y C35 dependen de un disparador de eventos HA/LILITH o de reproducción multiroom real; no pueden cerrarse creando un duplicado inseguro en JARVIS.
8. Hardware/capacidades propietarias: registrar como DEPENDENCIA EXTERNA y no prometer 68/68 sin esos prerrequisitos.

## Próximas tareas autónomas seguras, en orden
- Tests de voz y continuidad con sesiones simuladas en Windows y Ubuntu (sin grabar ni emitir audio).
- Cobertura de fallos y errores en las herramientas declaradas y confirmación de ejecución por plataforma.
- Auditoría de seguridad de ejecución: permisos, confirmaciones, idempotencia y logs en JARVIS solamente.
- Validación de arranque automático/recuperación por consultas read-only; no reiniciar servicios.
- Preparar checklist de pruebas físicas individuales y ventana de despliegue supervisada.
- Registrar cada corrección con test antes/después, commit propio y HANDOFF, sin tocar cambios ajenos.

## Prohibiciones y coordinación
No trabajar en APK ni sus fuentes, `/home/flako1312/lilith`, Home Assistant ni M-3/M-9; no activar los aparatos. No reiniciar JARVIS hasta orden del usuario. No usar `git reset --hard` ni `git clean` en Ubuntu: su worktree tiene cambios anteriores sin seguimiento. Seguir la automatización existente «JARVIS — cierre autónomo» (cada hora), que hace bloques verificables y no pretende permanecer ejecutándose sin interrupción.
