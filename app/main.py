import os
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import HttpUrl

from app.schemas import DownloadRequest, TaskStatusResponse, VideoInfoResponse
from app.services import download_and_merge, get_video_formats

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="YouTube Media Downloader API",
    version="1.0.0",
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# In-memory task store (replace with Redis for multi-worker production environments)
tasks: Dict[str, Dict[str, Any]] = {}


@app.get("/", include_in_schema=False)
def serve_ui():
    """Serve the built-in single-page downloader UI."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/v1/formats", response_model=VideoInfoResponse)
def fetch_formats(url: HttpUrl):
    """Fetch metadata and all available video resolutions for a YouTube URL."""
    try:
        return get_video_formats(str(url))
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to extract video info: {str(exc)}",
        ) from exc


@app.post("/api/v1/download", response_model=TaskStatusResponse)
def start_download(payload: DownloadRequest, background_tasks: BackgroundTasks):
    """Queue a background task to download and merge video + audio."""
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "status": "queued",
        "progress": None,
        "stage": "Queued",
        "file_path": None,
        "download_url": None,
        "error": None,
    }

    background_tasks.add_task(
        download_and_merge,
        str(payload.url),
        payload.resolution,
        task_id,
        tasks,
    )
    return TaskStatusResponse(task_id=task_id, status="queued", stage="Queued")


@app.get("/api/v1/status/{task_id}", response_model=TaskStatusResponse)
def check_status(task_id: str):
    """Check the current status of a queued or active download task."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    task = tasks[task_id]
    return TaskStatusResponse(
        task_id=task_id,
        status=task["status"],
        progress=task.get("progress"),
        stage=task.get("stage"),
        download_url=task["download_url"],
        error=task["error"],
    )


@app.get("/api/v1/file/{task_id}")
def get_file(task_id: str):
    """Download the merged MP4 file once the task is completed."""
    task = tasks.get(task_id)
    if not task or task["status"] != "completed":
        raise HTTPException(status_code=400, detail="File not ready or task invalid")

    file_path = task["file_path"]
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File expired or missing")

    return FileResponse(
        path=file_path,
        media_type="video/mp4",
        filename=os.path.basename(file_path),
    )
