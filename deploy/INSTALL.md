# JARVIS Headless — Deployment

## Prerequisites

- Ubuntu 24.04+ with systemd --user support
- Python 3.14+ virtualenv at `.venv/`
- PulseAudio running as user
- ALSA capture device configured
- `loginctl enable-linger` for the service user

## systemd service install

```bash
# Enable linger (allows user services to start at boot without login)
loginctl enable-linger flako1312

# Deploy the unit file
mkdir -p ~/.config/systemd/user
cp deploy/systemd/jarvis-headless.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now jarvis-headless.service
```

## Verify

```bash
systemctl --user status jarvis-headless
curl http://127.0.0.1:7470/health
curl http://127.0.0.1:7470/status
```

## Logs

```bash
journalctl --user -u jarvis-headless -f
```

## Service behavior

- **Restart=on-failure**: auto-restarts on crash (exit != 0), NOT on clean stop
- **RestartSec=10**: waits 10s before restart
- **StartLimitBurst=4 / StartLimitIntervalSec=120**: max 4 restarts in 2 minutes
- **KillSignal=SIGTERM**: clean shutdown via `jarvis.request_shutdown()`
- **Health endpoint**: 127.0.0.1:7470 (local only, daemon thread dies with process)

## Telegram text gateway

See [`../docs/TELEGRAM_GATEWAY.md`](../docs/TELEGRAM_GATEWAY.md) for the owner-only long-polling
adapter, private configuration, systemd unit, operations and physical acceptance sequence.
