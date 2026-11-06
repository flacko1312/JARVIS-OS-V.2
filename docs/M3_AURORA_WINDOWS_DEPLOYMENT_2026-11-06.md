# M3 — AURORA Windows: implementación y estado de despliegue (2026-11-06)

## Alcance
La Fase 4 Core ↔ AURORA incorpora cuatro capacidades de consulta Windows:
- windows.system.metrics.read
- windows.application.list
- windows.window.list
- windows.audio.device.list

Conserva las seis capacidades legacy de presencia Fase 2. Cuando
ADAPTER_INVOKE_READONLY_ENABLED no es true, el catálogo permanece exactamente
igual al anterior (seis entradas) y el conector rechaza invoke.

Un único receptor WebSocket procesa heartbeat_ack e invoke, sin competir con
otras llamadas a recv(). Los resultados tienen límites de tamaño y tiempo.
Métricas son agregadas; las aplicaciones muestran nombres de ejecutables,
sin argumentos. Las ventanas devuelven nombres de procesos, nunca títulos
privados de documentos o pestañas, y no incluyen AURORA/JARVIS.

La disponibilidad de sesión y hardware se verifica al publicar el catálogo y
antes de ejecutar cada llamada. Si no se puede comprobar, se rechaza.

## Pruebas realizadas
- Windows: 63 PASS con el Python virtual existente del proyecto:
  tests/test_adapter_connector.py,
  lilith_client/test_aurora_m3.py,
  tests/test_m3_aurora_transport.py.
- Core Ubuntu: 26 PASS de contratos M2/M3/P4.
- Compilación Python y comprobación de diff: PASS.

## Estado de la puesta en marcha
- Código instalado en C:\JARVIS\lilith_client\adapter_connector.py
- Copia anterior recuperable:
  C:\JARVIS\lilith_client\adapter_connector.py.bak.m3_20261106
- **No se modificaron variables de entorno ni se reinició AURORA/Core.**
- La integración REAL Core → AURORA → Windows → Core NO está validada aún.
- No declarar M3 CERTIFIED_FINAL hasta obtener respuestas reales, comprobar
  desconexión/retorno y verificar ausencia de regresiones en la voz.

## Activación posterior (ventana controlada)
1. Verificar procesos, trabajo concurrente y que el propietario acepta el reinicio.
2. Configurar ADAPTER_INVOKE_READONLY_ENABLED=true en AURORA Windows, conservando
   ADAPTER_CONNECTION_ENABLED=true y las credenciales existentes.
3. Configurar ADAPTER_WINDOWS_READONLY_ENABLED=true en el contenedor Core a través
   del mecanismo de despliegue existente (no basta escribir .env si Compose no la pasa).
4. Reiniciar solo los servicios imprescindibles, uno cada vez, con rollback comprobado.
5. Confirmar catálogo de 10 entradas, resolver 4 capacidades disponibles según
   sesión/hardware y enviar las cuatro consultas con token AUTHORIZED e idempotency_key.
6. Probar flags off, Windows desconectado, reconexión y no regresión.
7. Si hay algún fallo, desactivar flags y restaurar solamente el archivo desde
   la copia indicada, siguiendo el procedimiento habitual de despliegue.

No tocar voz, GUI, Home Assistant, MQTT, PostgreSQL, disco ni red durante
la activación. No instalar LLM en Ubuntu.


## Activación real M3 — 2026-11-06 (supersede el estado predespliegue anterior)

La integración está instalada y habilitada en los dos hosts, sin modificar voz,
interfaz, memoria ni motores conversacionales:
- Windows: conector activo en `C:\JARVIS\lilith_client\adapter_connector.py`;
  tarea `JARVIS-Adapter-Presence` reiniciada de forma controlada. Configuración
  `ADAPTER_INVOKE_READONLY_ENABLED=true` y `ADAPTER_CONNECTION_ENABLED=true`.
- Core: `ADAPTER_WINDOWS_READONLY_ENABLED=true` en la configuración del
  contenedor `lilith_core`. Se recreó únicamente Core mediante Docker Compose.
  PostgreSQL, MQTT y Home Assistant no se reiniciaron.
- Catálogo recibido por Core: 10 capacidades (6 legacy + 4 canónicas).
  El resolver devuelve `connected=true`, `invoke_enabled=true` y
  `available=true` para las cuatro capacidades Windows.

**Pruebas reales Core → AURORA → Windows → Core:** cuatro llamadas a
`POST /api/v1/adapters/invoke` con credencial AUTHORIZED e idempotency_key
única, **HTTP 200 (4/4)**. Evidencia resumida: CPU 1,8 %, RAM disponible
6120 MB, disco C: libre 393 GB; 50 nombres de aplicaciones/procesos,
7 ventanas con `titles_redacted=true` y 34 dispositivos de audio.
Los nombres privados de ventanas y los tokens no se registraron en este informe.

**Seguridad (6/6):** credencial inválida rechazada HTTP 401; capacidad
Linux sobre adapter Windows rechazada HTTP 404; adapter desconocido HTTP 400;
primera solicitud idempotente HTTP 200; repetición exacta HTTP 200 con
`idempotent_replay=true` y mismo ID; reutilización conflictiva HTTP 409.

**Reconexión real:** al parar la tarea Windows, Core registró
`adapter_disconnected ... reason=clean_shutdown` a las 18:02:16 CET;
al reiniciar la tarea, Core registró nueva sesión
`adapter_registered ... adapter.aurora.windows` a las 18:02:40 CET.
Tarea `Running`, dos procesos pythonw vinculados (lanzador e intérprete),
TCP hacia Core `ESTABLISHED` después de la recuperación.

**Regresiones:** AURORA Windows 63 pruebas PASS (29 legacy + 34 M3/transport);
Core 26 pruebas M2/M3/Phase4 PASS en la revisión posterior a la activación.
Python compila. Existe una advertencia no bloqueante de `asyncio_mode` al
ejecutar pytest de Core sin autoload de plugins.

**Rollback limitado a M3:**
- Windows: restaurar `C:\JARVIS\.env.adapter` desde
  `C:\JARVIS\.env.adapter.bak.m3_activation_20261106` y reiniciar
  únicamente la tarea `JARVIS-Adapter-Presence`.
- Código anterior del conector, si fuera necesario:
  `C:\JARVIS\lilith_client\adapter_connector.py.bak.m3_20261106`.
- Ubuntu: restaurar `.env` desde
  `.env.bak.m3_activation_20261106` y recrear únicamente `core` sin
  dependencias. Nunca exponer tokens en la bitácora.

**Estado:** READY_FOR_PHYSICAL. El software M3 ya está desplegado y las
consultas reales están validadas. Quedan para campaña física de aceptación:
bloqueo/desbloqueo del escritorio, suspensión/reanudación, conexión/
desconexión de audio y observación prolongada de la voz. No declarar
CERTIFIED_FINAL por estas pruebas no realizadas.
