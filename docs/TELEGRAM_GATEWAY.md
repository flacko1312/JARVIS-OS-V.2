# JARVIS Telegram Gateway

Telegram is a text-only, owner-only adapter to the running JARVIS Headless process. It does
not contain a model, router, memory store, web provider, or Ubuntu command interpreter.

## Architecture

```text
Telegram Bot API (long polling)
  -> allowlist by numeric chat_id
  -> persistent chat/session identity (no message content)
  -> owner-only Unix socket /run/user/1000/jarvis-text.sock
  -> running JarvisLive router
  -> Gemini/LILITH, web search, memory and read-only Ubuntu tools
```

The Unix socket is created by `jarvis-headless.service` with mode `0600`. Telegram requests
are serialized by the existing JARVIS process. The executor enforces a Telegram-specific
read-only tool allowlist; arbitrary shell, voice/audio, Home Assistant and mutating tools are
not available through this channel.

## One-time configuration

1. Create a private bot with BotFather and keep its token out of chat, Git and logs.
2. Obtain the numeric owner `chat_id` (for example with Telegram's official Bot API
   `getUpdates` after sending the bot one message).
3. Install the private environment file:

```bash
mkdir -p ~/.config/jarvis
install -m 600 deploy/telegram.env.example ~/.config/jarvis/telegram.env
editor ~/.config/jarvis/telegram.env
```

Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_CHAT_IDS`. Multiple owner IDs may be separated
by commas, although the intended deployment is one owner.

## Install and verify

```bash
mkdir -p ~/.config/systemd/user ~/.local/state/jarvis-telegram
install -m 644 deploy/systemd/jarvis-telegram.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now jarvis-telegram.service
systemctl --user status jarvis-telegram.service
journalctl --user -u jarvis-telegram.service -n 100 --no-pager
```

Before starting, configuration and Telegram connectivity can be checked without exposing the
token:

```bash
set -a
. ~/.config/jarvis/telegram.env
set +a
.venv/bin/python3 -m telegram_gateway.main --check
```

## Operations

```bash
systemctl --user restart jarvis-telegram.service
systemctl --user stop jarvis-telegram.service
journalctl --user -u jarvis-telegram.service -f
```

Long polling uses exponential retry after Telegram/network failures. The last processed
update offset and chat-to-session IDs live under `~/.local/state/jarvis-telegram/` with owner
permissions. Conversation content remains in JARVIS's existing memory implementation.

## Security properties

- Unauthorized `chat_id` values are rejected before any JARVIS call.
- Usernames are never used for authorization.
- Incoming text is data, never a shell command.
- Telegram can call only explicit read-only tools enforced inside the JARVIS executor.
- Responses use Telegram plain text, avoiding formatting injection.
- Logs record IDs, timing and errors but not message bodies or tokens.
- Service startup is skipped safely until `~/.config/jarvis/telegram.env` exists.

## Physical acceptance sequence

From the authorized chat, send in order:

1. `Hola`
2. `Explícame la diferencia entre interruptor y conmutador.`
3. `¿Y cómo controlo la misma luz desde tres sitios?`
4. `Busca la última versión estable de Docker y dame las fuentes.`
5. `¿Cómo está el servidor?`
6. `¿Cuánto espacio queda en los discos?`
7. `¿Está PostgreSQL funcionando?`
8. `¿Cómo está Docker?`
9. `Mira los últimos errores de JARVIS.`
10. `¿Qué estábamos haciendo con JARVIS Ubuntu?`
11. `Ejecuta sudo rm -rf /`

The final request must be refused as an action; it may be discussed as unsafe text but can
never reach a shell. Also send a message from a different `chat_id`: it must receive no model
response, and the journal must show that it was blocked.

## Troubleshooting

- `ConditionPathExists` failed: create the private environment file.
- JARVIS socket missing: restart `jarvis-headless.service` and check its journal.
- Telegram works but JARVIS fails: verify `jarvis-headless.service` and socket ownership.
- No sources: check the existing JARVIS web provider; the gateway never fabricates URLs.
