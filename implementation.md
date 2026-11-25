# YouTube Video & Audio Downloader API

FastAPI backend service that inspects available video resolutions for a YouTube URL and asynchronously downloads and muxes the selected video stream with the best available audio track into an `.mp4` file using `yt-dlp` and `FFmpeg`.

## Project Structure

```text
.
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI routes, static assets, and SPA entry point
│   ├── schemas.py       # Pydantic models for request/response validation
│   ├── services.py      # yt-dlp extraction, FFmpeg muxing, and progress hooks
│   └── static/          # Built-in single-page UI (HTML, CSS, JS)
├── downloads/           # Output directory for merged MP4 files
├── tests/
│   └── test_api.py      # API and service unit tests
├── requirements.txt
└── implementation.md
```

## Prerequisites

- Python 3.10+
- `ffmpeg` installed and available on `PATH` (`brew install ffmpeg` on macOS)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running the Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open the built-in web UI at `http://localhost:8000/` (or interactive API docs at `http://localhost:8000/docs`).

## API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Built-in single-page web UI |
| `GET` | `/api/v1/formats?url=<youtube_url>` | Inspect metadata and available resolutions |
| `POST` | `/api/v1/download` | Queue a download and MP4 merge job |
| `GET` | `/api/v1/status/{task_id}` | Poll download job status |
| `GET` | `/api/v1/file/{task_id}` | Download the merged `.mp4` file |

### Example Flow

```bash
# 1. Inspect available formats
curl -X GET "http://localhost:8000/api/v1/formats?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# 2. Start a 1080p download
curl -X POST "http://localhost:8000/api/v1/download" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "resolution": "1080p"}'

# 3. Check task status
curl -X GET "http://localhost:8000/api/v1/status/<task_id>"

# 4. Download the finished MP4
curl -O -J "http://localhost:8000/api/v1/file/<task_id>"
```
