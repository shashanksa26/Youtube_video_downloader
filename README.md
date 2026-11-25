# YouTube Video & Audio Downloader

A **FastAPI** backend service with a built-in single-page web UI for inspecting available YouTube video qualities, downloading a selected video resolution alongside the best available audio track via **`yt-dlp`**, and muxing them into an `.mp4` file using **`FFmpeg`**.

## Features

- **Built-in Web UI (`/`)**: Paste a YouTube link, preview thumbnail/title/duration, pick a resolution, track live download & FFmpeg merge progress, and download the `.mp4` with one click.
- **Format Inspection (`GET /api/v1/formats`)**: Extracts available resolutions, FPS, approximate file sizes, and audio availability without downloading media.
- **Asynchronous Download & Muxing (`POST /api/v1/download`)**: Queues background tasks to download video + best audio and merge them into MP4.
- **Progress Polling & File Streaming (`GET /api/v1/status/{task_id}`, `GET /api/v1/file/{task_id}`)**: Tracks stream progress percentages, FFmpeg post-processing stages, and serves the finished `.mp4`.
- **Interactive API Docs**: Swagger UI at `/docs` and ReDoc at `/redoc`.

## Project Structure

```text
.
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI routes, static assets, and UI entry point
│   ├── schemas.py       # Pydantic request/response models
│   ├── services.py      # yt-dlp format extraction, progress hooks, and FFmpeg muxing
│   └── static/
│       ├── index.html   # Single-page web UI
│       ├── styles.css   # Light/dark responsive styles
│       └── app.js       # Client-side API calls, polling, and accessible error handling
├── downloads/           # Temporary output directory for merged MP4 files
├── tests/
│   └── test_api.py      # Unit & API tests (mocked yt-dlp)
├── requirements.txt
├── pytest.ini
├── implementation.md
└── youtube_downloader_fastapi_implementation_plan.md
```

## Prerequisites

- **Python 3.10+**
- **FFmpeg** installed and available on your `PATH`:

```bash
# macOS (Homebrew)
brew install ffmpeg

# Ubuntu / Debian
sudo apt update && sudo apt install -y ffmpeg

# Windows (Winget)
winget install Gyan.FFmpeg
```

## Setup & Run

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the FastAPI server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then open:
- **Web UI**: `http://localhost:8000/`
- **Swagger Docs**: `http://localhost:8000/docs`

## API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Built-in single-page web UI |
| `GET` | `/api/v1/formats?url=<url>` | Inspect metadata and available video qualities |
| `POST` | `/api/v1/download` | Queue a video + audio download & MP4 merge job |
| `GET` | `/api/v1/status/{task_id}` | Poll task status, progress percentage, speed, and stage |
| `POST` | `/api/v1/cancel/{task_id}` | Cancel a queued or active download task |
| `GET` | `/api/v1/file/{task_id}` | Download the completed `.mp4` file |

### Example cURL Usage

```bash
# 1. List available qualities
curl -X GET "http://localhost:8000/api/v1/formats?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# 2. Queue a 1080p download
curl -X POST "http://localhost:8000/api/v1/download" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "resolution": "1080p"}'

# 3. Poll task status
curl -X GET "http://localhost:8000/api/v1/status/<task_id>"

# 4. Download the merged MP4
curl -O -J "http://localhost:8000/api/v1/file/<task_id>"
```

## Running Tests

Install `pytest` and `httpx` (if not already in your environment) and run:

```bash
.venv/bin/pytest -v
```

## Production Notes

- **File Cleanup**: Add a TTL cleanup job or post-response deletion for files in `downloads/` to prevent disk exhaustion.
- **Task Queue**: Replace the in-memory `tasks` dictionary and FastAPI `BackgroundTasks` with Celery + Redis or ARQ when running multiple workers.
- **Rate Limits & Security**: Configure `yt-dlp` cookies/proxies if deploying from datacenter IPs, restrict accepted domains (`youtube.com`, `youtu.be`), and add authentication if exposed publicly.
