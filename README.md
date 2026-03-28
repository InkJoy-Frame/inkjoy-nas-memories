# InkJoy Manager

InkJoy Manager is a web app for managing InkJoy ePaper frames with upload and scheduled image publishing.

## Documentation Split

- **Developer docs (this file):** architecture, development workflow, project conventions.
- **User manual (bilingual):** local Docker usage and NAS deployment.
  - [`MANUAL.md`](./MANUAL.md)

## Features

- Account login (Global / China server)
- Device list retrieval
- Image upload and basic crop flow
- Scheduled daily image publishing from folder
- English / Chinese UI

## Quick Start (Development)

### Prerequisites

- Docker + Docker Compose
- Python 3.10+ (optional, for local lint/syntax checks)

### Run with Docker Compose

```powershell
docker-compose up --build
```

Open: `http://localhost:8080`

### Stop

```powershell
docker-compose down
```

## Project Structure

- `app.py`: Flask routes and API endpoints
- `database.py`: SQLite schema and data access
- `scheduler_manager.py`: APScheduler job lifecycle and execution
- `api_client.py`: InkJoy Open API client
- `templates/`: UI pages
- `static/`: CSS/JS assets

## Runtime Storage

- Database: `/data/inkjoy.db`
- Image library mount: `/images`

> Passwords are stored in plaintext for auto-login scheduling. This project is intended for personal/private deployment.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `inkjoy-manager-secret-change-this` | Flask session secret; change in production |
| `TZ` | `Asia/Shanghai` | Scheduler timezone |
| `IMAGES_DIR` | `/images` | Image library directory |
| `DATA_DIR` | `/data` | SQLite data directory |

## Build Scripts

- `build-export-x86.ps1`: Build/export **x86_64 / linux/amd64** image tar (Intel/AMD NAS)；默认输出 `inkjoy-manager-x86.tar`
- `build-export-arm.ps1`: Build/export **ARM64** image tar；默认输出 `inkjoy-manager-arm64.tar`

## API Dependency

Based on [InkJoy Open API](https://openapi.inkjoyframe.com/):

- `POST /api/v1/auth/login`
- `GET /api/v1/devices`
- `POST /api/v1/devices/{id}/publish`

## Notes for Contributors

- Keep account isolation logic in API layer (`session.account_id` checks).
- Do not bind scheduler execution to current web session.
- Prefer small, safe changes with backward-compatible DB updates.

