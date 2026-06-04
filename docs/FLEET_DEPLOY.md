# Brain Fleet Hub — deploy (admin VPS)

## Prerequisites

- Python 3.10+, TLS reverse proxy (nginx/caddy)
- Tokens generated offline (never commit)

## Server env

```bash
export BRAIN_FLEET_INSTALL_TOKEN="..."   # ingest only (user machines)
export BRAIN_FLEET_ADMIN_TOKEN="..."     # dashboard + GET API only
export BRAIN_FLEET_PORT=8600
export BRAIN_FLEET_DB=/var/lib/brain/fleet_metrics.db
python brain_fleet_server.py
```

## User config (`config.toml`)

```toml
[fleet]
enabled = true
url = "https://fleet.example.com"
token = "INSTALL_TOKEN"
push = true
```

```powershell
python brain.py fleet push
```

## Security checklist

- [ ] Install token cannot GET `/api/fleet/snapshots` or `/fleet.html`
- [ ] Payload rejects paths, code snippets, emails (see `tests/test_fleet_sanitize.py`)
- [ ] Admin token never in user `config.toml`
- [ ] Local viewer (`ops.html`) does not proxy fleet

## Schema

Allowlist: [config/fleet_telemetry_schema.json](../config/fleet_telemetry_schema.json)
