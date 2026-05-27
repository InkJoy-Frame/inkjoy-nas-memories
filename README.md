# InkJoy NAS Manager

Turn your NAS into an auto-play photo stream for InkJoy ePaper frames — pick folders, pick frames, set a schedule, and forget about it.

## Features

- Single-page UI — set up auto-play in a 4-step wizard (pick folders → pick frames → push settings → name it)
- Daily scheduled push from NAS photo folders with three fill modes (blur fill / center crop / ISFR smart crop)
- Quick push — browse photos and send one to any frame instantly
- Auto server detection login (global / China)
- English / Chinese UI

## Quick Start

### Docker Compose

```bash
docker-compose up --build
```

Open `http://localhost:8080`, log in with your InkJoy account.

### Local Development (no Docker)

```powershell
pip install -r requirements.txt
$env:IMAGES_DIR = "<your photo directory>"
$env:DATA_DIR = "./data"
$env:FLASK_DEBUG = "1"
python app.py
```

## Project Structure

- `app.py` — Flask routes + API
- `database.py` — SQLite schema and data access
- `scheduler_manager.py` — APScheduler job lifecycle and image processing (blur/crop/ISFR)
- `api_client.py` — InkJoy Open API client
- `templates/home.html` — single business page (auto-play list + wizard + quick push)
- `static/css/style.css` — all styles
- `static/js/i18n.js` — bilingual translations

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


