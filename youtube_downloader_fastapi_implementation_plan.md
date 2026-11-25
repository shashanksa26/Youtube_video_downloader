# YouTube Video & Audio Downloader API — Implementation Plan

## 1. Overview
This project provides a **FastAPI** backend service capable of inspecting available video qualities for any given YouTube URL and downloading the requested quality merged with the best available audio track.

Because YouTube serves high-resolution video streams (1080p, 1440p, 4K) separately from audio streams via DASH, this architecture combines **`yt-dlp`** (for stream extraction and downloading) with **`FFmpeg`** (for muxing separate video and audio tracks into a single `.mp4` container).

---

## 2. System Architecture & Workflow
To prevent HTTP timeouts during large downloads or FFmpeg muxing, the API operates asynchronously across two main stages:

1. **Metadata & Format Inspection (`GET /api/v1/formats`)**
   - Accepts a YouTube URL.
   - Extracts available video resolutions, codecs, and approximate file sizes without downloading the media.
   - Returns a structured JSON list of selectable qualities.
2. **Asynchronous Download & Merge (`POST /api/v1/download` -> `GET /api/v1/status/{task_id}` -> `GET /api/v1/file/{task_id}`)**
   - Queues a background task to download the requested video resolution + best audio stream.
   - Uses FFmpeg to merge both streams into an `.mp4` file.
   - Tracks progress via a `task_id` and serves the finished file once ready.

---

## 3. Prerequisites & Environment Setup

### Tech Stack
* **Python 3.10+**
* **FastAPI & Uvicorn:** Web framework and ASGI server
* **yt-dlp:** Media stream extraction and downloading
* **FFmpeg:** System-level binary for merging video and audio streams
* **Pydantic:** Request/response validation

### Installation
1. **Install FFmpeg:**
   ```bash
   # Ubuntu / Debian
   sudo apt update && sudo apt install -y ffmpeg

   # macOS (Homebrew)
   brew install ffmpeg

   # Windows (Winget)
   winget install Gyan.FFmpeg
   ```

2. **Set up Python Environment & Dependencies:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install fastapi uvicorn yt-dlp pydantic
   ```

---

## 4. Project Directory Structure

```text
youtube_downloader/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI routes and application entry point
│   ├── schemas.py       # Pydantic models for request/response validation
│   └── services.py      # yt-dlp extraction, merging, and file management logic
├── downloads/           # Temporary storage directory for merged media files
├── requirements.txt     # Python package dependencies
└── implementation.md    # Project implementation documentation
```

---

## 5. Step-by-Step Implementation

### Phase 1: Dependencies (`requirements.txt`)
```text
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
yt-dlp>=2024.4.9
pydantic>=2.7.0
```

### Phase 2: Data Schemas (`app/schemas.py`)
Define strict input and output contracts for URL validation, available formats, and task status polling.

```python
from pydantic import BaseModel, HttpUrl
from typing import List, Optional

class FormatOption(BaseModel):
    format_id: str
    resolution: str
    ext: str
    fps: Optional[int] = None
    filesize_mb: Optional[float] = None
    has_audio: bool

class VideoInfoResponse(BaseModel):
    title: str
    duration: Optional[int] = None
    thumbnail: Optional[str] = None
    formats: List[FormatOption]

class DownloadRequest(BaseModel):
    url: HttpUrl
    resolution: str = "best"  # Options: "2160p", "1440p", "1080p", "720p", "480p", "360p", or "best"

class TaskStatusResponse(BaseModel):
    task_id: str
    status: str  # "queued", "downloading", "completed", "failed"
    download_url: Optional[str] = None
    error: Optional[str] = None
```

### Phase 3: Extraction & Download Service (`app/services.py`)
Implement `yt-dlp` wrappers to extract clean resolution options and perform video+audio muxing via FFmpeg.

```python
import os
import yt_dlp
from pathlib import Path

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

def get_video_formats(url: str) -> dict:
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        
        seen_resolutions = set()
        clean_formats = []
        
        for f in info.get("formats", []):
            height = f.get("height")
            vcodec = f.get("vcodec")
            
            # Filter for valid video streams
            if height and vcodec != "none":
                res_label = f"{height}p"
                if res_label not in seen_resolutions:
                    seen_resolutions.add(res_label)
                    size = f.get("filesize") or f.get("filesize_approx")
                    clean_formats.append({
                        "format_id": f["format_id"],
                        "resolution": res_label,
                        "ext": "mp4",
                        "fps": f.get("fps"),
                        "filesize_mb": round(size / (1024 * 1024), 2) if size else None,
                        "has_audio": f.get("acodec") != "none"
                    })
                    
        # Sort highest resolution first
        clean_formats.sort(key=lambda x: int(x["resolution"].replace("p", "")), reverse=True)
        
        return {
            "title": info.get("title", "Unknown Title"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "formats": clean_formats
        }

def download_and_merge(url: str, resolution: str, task_id: str, task_store: dict):
    try:
        task_store[task_id]["status"] = "downloading"
        output_template = str(DOWNLOAD_DIR / f"{task_id}_%(title)s.%(ext)s")
        
        # Select requested video height + best available audio, fallback to best combined stream
        if resolution != "best":
            height = resolution.replace("p", "")
            format_str = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
        else:
            format_str = "bestvideo+bestaudio/best"

        ydl_opts = {
            "format": format_str,
            "outtmpl": output_template,
            "merge_output_format": "mp4",  # Forces FFmpeg muxing into MP4
            "quiet": True,
            "no_warnings": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            final_path = os.path.splitext(filename)[0] + ".mp4"
            
            task_store[task_id]["status"] = "completed"
            task_store[task_id]["file_path"] = final_path
            task_store[task_id]["download_url"] = f"/api/v1/file/{task_id}"

    except Exception as e:
        task_store[task_id]["status"] = "failed"
        task_store[task_id]["error"] = str(e)
```

### Phase 4: FastAPI Endpoints (`app/main.py`)
Expose REST endpoints to fetch available qualities, queue downloads, check status, and stream the final merged video.

```python
import uuid
import os
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from app.schemas import VideoInfoResponse, DownloadRequest, TaskStatusResponse
from app.services import get_video_formats, download_and_merge

app = FastAPI(
    title="YouTube Media Downloader API",
    version="1.0.0"
)

# In-memory task store (replace with Redis for multi-worker production environments)
tasks = {}

@app.get("/api/v1/formats", response_model=VideoInfoResponse)
def fetch_formats(url: str):
    """Fetch metadata and all available video resolutions for a YouTube URL."""
    try:
        return get_video_formats(url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to extract video info: {str(e)}")

@app.post("/api/v1/download", response_model=TaskStatusResponse)
def start_download(payload: DownloadRequest, background_tasks: BackgroundTasks):
    """Queue a background task to download and merge video + audio."""
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "status": "queued",
        "file_path": None,
        "download_url": None,
        "error": None
    }
    
    background_tasks.add_task(
        download_and_merge,
        str(payload.url),
        payload.resolution,
        task_id,
        tasks
    )
    return TaskStatusResponse(task_id=task_id, status="queued")

@app.get("/api/v1/status/{task_id}", response_model=TaskStatusResponse)
def check_status(task_id: str):
    """Check the current status of a queued or active download task."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    task = tasks[task_id]
    return TaskStatusResponse(
        task_id=task_id,
        status=task["status"],
        download_url=task["download_url"],
        error=task["error"]
    )

@app.get("/api/v1/file/{task_id}")
def get_file(task_id: str):
    """Download the merged MP4 file once the task is completed."""
    task = tasks.get(task_id)
    if not task or task["status"] != "completed":
        raise HTTPException(status_code=400, detail="File not ready or task invalid")
    
    file_path = task["file_path"]
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File expired or missing")
        
    return FileResponse(
        path=file_path,
        media_type="video/mp4",
        filename=os.path.basename(file_path)
    )
```

---

## 6. Running & Testing the API

### Start the Server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Interactive Swagger API docs will be available at: `http://localhost:8000/docs`

### Example Usage Flow (cURL)

1. **List available video qualities:**
   ```bash
   curl -X GET "http://localhost:8000/api/v1/formats?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"
   ```

2. **Start download in 1080p with merged audio:**
   ```bash
   curl -X POST "http://localhost:8000/api/v1/download" \
        -H "Content-Type: application/json" \
        -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "resolution": "1080p"}'
   ```

3. **Poll task status:**
   ```bash
   curl -X GET "http://localhost:8000/api/v1/status/<task_id>"
   ```

4. **Download the final `.mp4` file:**
   ```bash
   curl -O -J "http://localhost:8000/api/v1/file/<task_id>"
   ```

---

## 7. Production Readiness Checklist

| Category | Recommendation |
| :--- | :--- |
| **File Cleanup** | Add a scheduled cron job or post-response background task to delete files in `downloads/` after serving or after a TTL (e.g., 1 hour) to prevent disk exhaustion. |
| **Task Queue & Scaling** | Replace FastAPI's in-memory `tasks` dictionary and `BackgroundTasks` with **Celery + Redis** (or **ARQ**) when running multiple Uvicorn/Gunicorn workers or handling 4K transcoding loads. |
| **Bot Detection & Rate Limits** | Datacenter IPs are frequently rate-limited by YouTube. Configure `yt-dlp` with rotating residential proxies or authenticated cookies (`cookiefile`) if deploying to cloud infrastructure. |
| **Security & SSRF Protection** | Validate incoming URLs strictly against `youtube.com` and `youtu.be` domains, and protect endpoints with API keys or JWT authentication. |
| **Containerization** | Package the service with a `Dockerfile` based on `python:3.11-slim` that installs `ffmpeg` at build time for consistent deployments. |