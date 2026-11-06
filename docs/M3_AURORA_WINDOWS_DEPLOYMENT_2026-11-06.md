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
