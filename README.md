# Holded ↔ Cegid Integration

Integration tool that migrates invoices, estimates, and purchase documents from **Holded** (ERP) to **Cegid** (accounting system).

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [Project Structure](#project-structure)
- [Key Concepts](#key-concepts)
- [Auto-Migration](#auto-migration)
- [Makefile Commands](#makefile-commands)
- [Troubleshooting](#troubleshooting)

---

## Overview

This application:

1. **Connects to Holded** – Fetches invoices, estimates, purchases, and other documents via the Holded API
2. **Transforms data** – Adapts the format for Cegid's API
3. **Pushes to Cegid** – Creates/updates documents in Cegid's accounting system
4. **Tracks progress** – Stores offsets per account and document type to avoid re-processing
5. **Runs automatically** – Optional scheduled migration every N days (default: 30)

---

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Web UI        │     │   Quart      │     │   Celery        │
│   (Browser)     │────▶│   App        │────▶│   Worker        │
│   Port 5000/8080│     │   (Python)   │     │   (Python)      │
└─────────────────┘     └──────┬───────┘     └────────┬────────┘
                               │                      │
                               │    ┌──────────────┐  │
                               └───▶│   Redis      │◀─┘
                                    │   (Broker +   │
                                    │   Cache)      │
                                    └──────────────┘
                                         │
                                    ┌────▼────┐
                                    │ Celery  │
                                    │ Beat    │
                                    │(Scheduler)│
                                    └─────────┘
```

- **Quart** – Web server (HTTP API, login, configuration UI)
- **Celery Worker** – Runs migration tasks asynchronously
- **Celery Beat** – Schedules automatic migrations
- **Redis** – Message broker for Celery and task log storage

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Web framework | Quart (async Flask) |
| Task queue | Celery |
| Broker | Redis |
| Python | 3.10+ |
| HTTP server | Hypercorn |

---

## Prerequisites

- **Docker** and **Docker Compose** (for full stack)
- **Python 3.10+** and **venv** (for local development)
- **Holded API key** (per account)
- **Cegid credentials** (API Contabilidad, API ERP)

---

## Quick Start

### 1. Clone and setup

```bash
cd holded_to_celig
python3 -m venv venv
source venv/bin/activate   # Linux/Mac
# or: venv\Scripts\activate  # Windows

pip install -r requirements.txt
```

### 2. Create credentials file

Create `src/config/credentials.json` (not in git). Use the structure in [Configuration](#configuration). You can also configure accounts via the web UI after first run.

### 3. Environment variables

```bash
cp .env.example .env
```

Edit `.env` with at least: `SECRET_KEY`, `BASIC_AUTH_USER`, `BASIC_AUTH_PASS`, `REDIS_URL`.

### 4. Run with Docker (recommended)

```bash
make up
```

Access: **http://localhost:8080** (or via Caddy on port 80/443 if configured).

### 5. Run locally (for development)

```bash
# Terminal 1: Redis
docker compose up -d redis

# Terminal 2: Celery Worker
export PYTHONPATH=. REDIS_URL=redis://localhost:6379/0
celery -A src.workers.celery_config worker --loglevel=info

# Terminal 3: Celery Beat (optional, for auto-migration)
export PYTHONPATH=. REDIS_URL=redis://localhost:6379/0
celery -A src.workers.celery_config beat --loglevel=info

# Terminal 4: Web app
make run-local
```

Access: **http://localhost:5000**

---

## Configuration

### `src/config/credentials.json`

Contains sensitive data (not committed to git). Structure:

```json
{
  "holded_accounts": [
    {
      "id": "uuid",
      "nombre_empresa": "Company Name",
      "api_key": "holded-api-key",
      "codigo_empresa": "CEGID_CODE",
      "tipo_cuenta": "normal|custom",
      "cuentas_a_migrar": [
        { "tipo": "invoice", "offset": 0 },
        { "tipo": "estimate", "offset": 0 },
        { "tipo": "purchase", "offset": 0 }
      ]
    }
  ],
  "cegid": {
    "username": "...",
    "password": "...",
    "api_contavilidad": { "clientId": "...", "clientSecret": "..." },
    "api_erp": { "clientId": "...", "clientSecret": "..." }
  }
}
```

### `.env` variables

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `SECRET_KEY` | Session secret (must be fixed) | Required |
| `BASIC_AUTH_USER` | Login username | - |
| `BASIC_AUTH_PASS` | Login password | - |
| `SESSION_LIFETIME_SECONDS` | Session duration | 2592000 (30 days) |
| `AUTO_MIGRATION_ENABLED` | Enable scheduled migration | `true` |
| `AUTO_MIGRATION_INTERVAL_DAYS` | Days between migrations | `30` |

---

## Running the Application

### Docker (full stack)

| Command | Description |
|---------|-------------|
| `make up` | Start all services |
| `make down` | Stop all services |
| `make logs` | Follow logs |

### Local development

| Scenario | Port | Notes |
|----------|------|-------|
| **App only** | 5000 | `make run-local` – needs Redis + Celery running for migrations |
| **App in Docker** | 8080 | `docker compose up -d app` – Celery + Redis in Docker |

**Important:** If you run the app locally (`make run-local`), ensure:
- Redis is running (`docker compose up -d redis`)
- Celery Worker is running (for migrations)
- `REDIS_URL=redis://localhost:6379/0` so the app can read task logs from Redis

---

## Project Structure

```
holded_to_celig/
├── src/
│   ├── config/
│   │   ├── credentials.json      # Not in git – create from example
│   │   └── settings.py           # App settings
│   ├── quart_app/
│   │   ├── app.py                # Web app, routes, auth
│   │   ├── config_manager.py     # Config load/save
│   │   └── templates/            # HTML templates
│   ├── services/
│   │   ├── holded_service.py     # HoldedAPI – Holded API client
│   │   ├── cegid_service.py      # CegidAPI – Cegid API client
│   │   ├── sync_service.py       # AsyncService – migration logic
│   │   └── logging_utils.py      # Task logs, Redis storage
│   └── workers/
│       ├── celery_config.py      # Celery app, beat schedule
│       └── tasks.py             # Celery tasks (auto_migrate_invoices, etc.)
├── docker-compose.yaml
├── Makefile
├── requirements.txt
├── .env.example
└── Caddyfile                    # Reverse proxy (optional)
```

---

## Key Concepts

### Holded accounts

Each Holded account has:
- **API key** – From Holded API settings
- **Código empresa** – Cegid company code
- **Cuentas a migrar** – Document types to migrate: `invoice`, `estimate`, `purchase`, etc.

### Offsets

- **Offset** – Number of documents already processed for that account/type
- Stored in `credentials.json` and updated after each successful migration
- Prevents re-processing the same documents

### Document types

| Type | Description |
|------|-------------|
| `invoice` | Invoice (sales) |
| `estimate` | Estimate |
| `purchase` | Purchase invoice |
| `salesorder` | Sales order |
| `purchaseorder` | Purchase order |

### Account types

- **normal** – Legacy Cegid API
- **nuevo_sistema** – New Cegid API

---

## Auto-Migration

- **Enabled by default** – Runs every N days (configurable)
- **Schedule** – Midnight (00:00) every `AUTO_MIGRATION_INTERVAL_DAYS` days
- **Date filter** – Only migrates documents from the last N days
- **Manual trigger** – Use "Ejecutar Ahora" in the web UI

### Configuration

```bash
# .env
AUTO_MIGRATION_ENABLED=true
AUTO_MIGRATION_INTERVAL_DAYS=30
```

After changing these, restart Celery Beat:

```bash
make restart-beat
```

---

## Makefile Commands

| Command | Description |
|---------|-------------|
| `make up` | Start all Docker services |
| `make down` | Stop all services |
| `make run-local` | Run app locally (stops Docker app first) |
| `make down-app` | Stop and remove app container |
| `make logs` | Follow all logs |
| `make logs-worker` | Follow Celery worker logs |
| `make logs-beat` | Follow Celery beat logs |
| `make logs-redis` | Follow Redis logs |
| `make restart-worker` | Restart Celery worker |
| `make restart-beat` | Restart Celery beat |
| `make build` | Rebuild Docker images |
| `make shell` | Shell into app container |

---

## Troubleshooting

### "Connection refused" when triggering migration

- **Cause:** App cannot reach Redis or Celery
- **Fix:** Ensure Redis and Celery Worker are running. If using Docker: `docker compose up -d redis celery_worker celery_beat`

### Logs modal is empty

- **Cause:** App and Celery use different Redis instances or task context is lost
- **Fix:** Ensure Redis is shared. Use `REDIS_URL=redis://localhost:6379/0` for local app. Rebuild Celery after code changes: `docker compose build celery_worker celery_beat && docker compose up -d celery_worker celery_beat`

### Session lost on page reload

- **Cause:** `SECRET_KEY` changes on restart (e.g. random default)
- **Fix:** Set a fixed `SECRET_KEY` in `.env` and restart the app

### Celery not picking up code changes

- **Fix:** Rebuild and restart Celery containers:
  ```bash
  docker compose stop celery_worker celery_beat
  docker compose build celery_worker celery_beat
  docker compose up -d celery_worker celery_beat
  ```

### No documents in date range

- **Cause:** All documents are older than the configured interval (e.g. 30 days)
- **Fix:** Check document dates in Holded. Adjust `AUTO_MIGRATION_INTERVAL_DAYS` if needed.

---

## Documentation

The web UI includes a **Documentación** section at `/documentation` with:
- Concept explanations
- How to create new integrations
- Document type mappings
- Troubleshooting

---

## License

Internal use. See project maintainers for details.
