# InkJoy NAS Manager

Turn your NAS into an auto-play photo stream for InkJoy ePaper frames — pick folders, pick frames, set a schedule, and forget about it.

## Features

- Single-page UI — set up auto-play in a 4-step wizard (pick folders → pick frames → push settings → name it)
- Daily scheduled push from NAS photo folders with three fill modes (blur fill / center crop / ISFR smart crop)
- Quick push — browse photos and send one to any frame instantly
- Auto server detection login (global / China)
- English / Chinese UI

## Quick Start

### Docker (recommended)

Pre-built multi-arch images are available on GitHub Container Registry, supporting both x86_64 and ARM64 NAS devices.

```bash
docker run -d \
  --name inkjoy-manager \
  -p 8080:8080 \
  -v /path/to/your/photos:/images \
  -v /path/to/data:/data \
  -e SECRET_KEY=your-secret-key \
  -e TZ=Asia/Shanghai \
  ghcr.io/inkjoy-frame/inkjoy-nas-memories:latest
```

Or use Docker Compose:

```yaml
services:
  inkjoy-manager:
    image: ghcr.io/inkjoy-frame/inkjoy-nas-memories:latest
    ports:
      - "8080:8080"
    volumes:
      - /path/to/your/photos:/images
      - /path/to/data:/data
    environment:
      - SECRET_KEY=your-secret-key
      - TZ=Asia/Shanghai
    restart: unless-stopped
```

Open `http://<nas-ip>:8080`, log in with your InkJoy account.

### Supported Architectures

| Architecture | Devices |
|---|---|
| `linux/amd64` (x86_64) | Synology, QNAP, UGREEN DXP series, PC, server |
| `linux/arm64` (aarch64) | UGREEN DH series, Raspberry Pi, ARM NAS |

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

## Releases

Docker images are automatically built and published on every version tag via GitHub Actions. See [Releases](https://github.com/InkJoy-Frame/inkjoy-nas-memories/releases) for all versions.

To update to the latest version:

```bash
docker pull ghcr.io/inkjoy-frame/inkjoy-nas-memories:latest
docker stop inkjoy-manager && docker rm inkjoy-manager
# Re-run the docker run command above
```

## API Dependency

Based on [InkJoy Open API](https://openapi.inkjoyframe.com/):

- `POST /api/v1/auth/login`
- `GET /api/v1/devices`
- `POST /api/v1/devices/{id}/publish`


