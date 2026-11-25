from typing import List, Optional, Union
import re
from pydantic import BaseModel, HttpUrl, field_validator


class FormatOption(BaseModel):
    """Represents a selectable video stream quality option."""

    format_id: str
    resolution: str
    ext: str
    fps: Optional[Union[int, float]] = None
    filesize_mb: Optional[float] = None
    has_audio: bool


class VideoInfoResponse(BaseModel):
    """Metadata and available video formats for a YouTube URL."""

    title: str
    duration: Optional[Union[int, float]] = None
    thumbnail: Optional[str] = None
    formats: List[FormatOption]


class DownloadRequest(BaseModel):
    """Request payload for queuing a video download and merge task."""

    url: HttpUrl
    resolution: str = "best"  # Options: "2160p", "1440p", "1080p", "720p", "480p", "360p", or "best"

    @field_validator("resolution")
    @classmethod
    def validate_resolution(cls, value: str) -> str:
        """Ensure resolution is either 'best' or a numeric height such as '1080p'."""
        normalized = value.strip().lower()
        if normalized == "best":
            return normalized
        if re.fullmatch(r"\d{3,4}p", normalized):
            return normalized
        raise ValueError("resolution must be 'best' or a height like '1080p', '720p', '480p'")


class TaskStatusResponse(BaseModel):
    """Status payload for an asynchronous download task."""

    task_id: str
    status: str  # "queued", "downloading", "completed", "failed", "cancelled"
    progress: Optional[float] = None
    stage: Optional[str] = None
    downloaded_mb: Optional[float] = None
    total_mb: Optional[float] = None
    speed_mb_s: Optional[float] = None
    download_url: Optional[str] = None
    error: Optional[str] = None
