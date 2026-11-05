# PHYSICAL_TESTS — Comprobaciones que debe hacer el usuario

Este archivo contiene todas las pruebas que requieren presencia física o acceso a hardware real.
Cada prueba incluye instrucciones simples y qué verificar.

---

## GRUPO 1: Pruebas de voz y conversación (AURORA Windows)

### PH-A1: Spotify AEC — acceptance final
**Capacidad:** C26 (Spotify), A1 (Reconocimiento voz)
**Estado previo:** shadow_v4 activo; offline replay 0 falsas activaciones
**Instrucción:**
1. Poner Spotify con una canción con partes vocales (p.ej. anuncio hablado o canción cantada).
2. Esperar 30-60 segundos en silencio.
3. **Esperado:** JARVIS no dice nada ni responde (0 turnos de usuario falsos).
4. Hablar una pregunta normal ("¿Qué hora es?") mientras sigue la música.
5. **Esperado:** JARVIS responde correctamente una sola vez, sin pausar la música.
**Si falla:** desactivar con `JARVIS_SPOTIFY_FILTER_MODE=off`

### PH-A2: Recuperación de transporte Gemini Live
**Capacidad:** A10, A5
**Estado previo:** Lógica de reconexión implementada pero NO forzada físicamente
**Instrucción:**
1. Iniciar conversación con JARVIS, establecer contexto ("El número es 42").
2. Desconectar temporalmente la red WiFi/LAN 5 segundos, reconectar.
3. **Esperado:** JARVIS muestra estado RECONNECTING, luego vuelve a LISTENING.
4. Preguntar "¿Cuál era el número?" (sin mencionar contexto previo).
5. **Esperado:** JARVIS responde "42" (o lo recuerda de la conversación) sin saludo nuevo.
**Registrar:** duración reconexión, si hubo saludo nuevo, si el contexto se mantuvo.

### PH-A3: Cámara web
**Capacidad:** C33 (parcial), visión
**Estado previo:** screen_process physical pass; cámara pendiente
**Instrucción:**
1. Decir a JARVIS: "Mira lo que hay en la cámara."
2. **Esperado:** captura imagen de webcam, describe lo que ve.
**Si falla:** anotar error específico.

---

## GRUPO 2: Domótica y Home Assistant

### PH-B1: Verificar entidades HA disponibles
**Capacidad:** B11-15, 23-24
**Instrucción:**
1. En la interfaz de JARVIS (Windows o Ubuntu), pedir "Lista los dispositivos del hogar."
2. O acceder a HA directamente: http://[IP-HA]:8123 → Developer Tools → States.
3. **Registrar:**
   - ¿Qué entidades están en estado `unavailable`?
   - ¿Qué grupos de habitaciones existen?
   - ¿Hay entidades cover.* (persianas)?
   - ¿Hay entidades climate.* (termostatos)?
   - ¿Hay dispositivos Cast (`media_player.*`)?
4. Actualizar BLOCKERS.md con el inventario real.

### PH-B2: Control de luz por voz
**Capacidad:** B11, A9
**Prerequisito:** PH-B1 completado, entidad de luz disponible identificada
**Instrucción:**
1. Decir: "Enciende la luz del [habitación]."
2. **Esperado:** luz se enciende, JARVIS confirma.
3. Decir: "Apaga la luz del [habitación]."
4. **Esperado:** luz se apaga, JARVIS confirma.
**Precaución:** solo probar entidades previamente identificadas como disponibles en PH-B1.

---

## GRUPO 3: Audio y multimedia doméstica (Ubuntu)

### PH-C1: Radio por internet en Ubuntu
**Capacidad:** C28
**Instrucción:**
1. En el sistema Ubuntu (voz o terminal), pedir "Pon la radio [nombre emisora]."
2. **Esperado:** reproducción de audio en altavoz doméstico.
**Prerequisito:** capacidad radio implementada en Ubuntu.

### PH-C2: Multiroom audio
**Capacidad:** C35
**Prerequisito:** Music Assistant instalado en HA, altavoces compatibles
**Instrucción:**
1. Pedir "Pon música en el salón y en la cocina."
2. **Esperado:** música en ambos altavoces sincronizada.

---

## GRUPO 4: Comunicación y organización

### PH-D1: Anuncio por altavoces domésticos
**Capacidad:** D37, D38
**Prerequisito:** TTS broadcast configurado en Ubuntu/HA
**Instrucción:**
1. Desde AURORA Windows o APK Android: "Anuncia en casa: la cena está lista."
2. **Esperado:** voz en altavoces de la casa pronuncia el mensaje.

### PH-E1: Alarma/temporizador
**Capacidad:** E41, E42
**Prerequisito:** timer tool implementado en AURORA
**Instrucción:**
1. Decir: "Pon un temporizador de 2 minutos."
2. Esperar 2 minutos.
3. **Esperado:** JARVIS notifica cuando termina.

---

## GRUPO 5: Verificación de Ubuntu y LILITH

### PH-U1: Estado servicios Ubuntu
**Instrucción:**
1. SSH a `server-lilith`.
2. Ejecutar: `systemctl status jarvis-headless` y `systemctl status lilith`.
3. Verificar: `journalctl -u jarvis-headless -n 50`.
4. **Registrar:** versión, uptime, errores recientes.
5. Actualizar STATUS.json con estado real.

### PH-U2: Activación por palabra clave en Ubuntu
**Capacidad:** A2
**Instrucción:**
1. Acercarse al micrófono conectado a Ubuntu.
2. Decir claramente "Jarvis" (o la palabra clave configurada).
3. **Esperado:** respuesta de Ubuntu.
4. **Registrar:** falsos positivos en 5 minutos de prueba.

### PH-L1: LILITH health check
**Instrucción:**
1. Desde AURORA Windows (si LILITH está en la red), decir "Jarvis, comprueba el estado de LILITH."
2. O SSH a Ubuntu y ejecutar: `curl -H "Authorization: Bearer [token]" http://[LILITH_IP]/health`.
3. **Esperado:** respuesta `{"status": "ok"}`.

---

## Registro de resultados

| Prueba | Fecha | Resultado | Observaciones |
|---|---|---|---|
| PH-A1 Spotify AEC | — | PENDIENTE | |
| PH-A2 Recuperación transporte | — | PENDIENTE | |
| PH-A3 Cámara web | — | PENDIENTE | |
| PH-B1 Inventario HA | — | PENDIENTE | |
| PH-B2 Control luz voz | — | PENDIENTE | |
| PH-C1 Radio Ubuntu | — | PENDIENTE | |
| PH-C2 Multiroom | — | PENDIENTE | |
| PH-D1 Anuncio altavoces | — | PENDIENTE | |
| PH-E1 Temporizador | — | PENDIENTE | |
| PH-U1 Estado Ubuntu | — | PENDIENTE | |
| PH-U2 Palabra clave Ubuntu | — | PENDIENTE | |
| PH-L1 LILITH health | — | PENDIENTE | |
