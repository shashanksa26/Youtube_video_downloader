import os
from pathlib import Path
from typing import Any, Dict

import yt_dlp

DOWNLOAD_DIR = Path(__file__).resolve().parent.parent / "downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


def get_video_formats(url: str) -> Dict[str, Any]:
    """Extract video metadata and deduplicated resolution options without downloading."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    formats_by_res: Dict[str, Dict[str, Any]] = {}

    for fmt in info.get("formats", []):
        height = fmt.get("height")
        vcodec = fmt.get("vcodec")

        # Filter for valid video streams
        if height and vcodec and vcodec != "none":
            res_label = f"{height}p"
            size = fmt.get("filesize") or fmt.get("filesize_approx")
            candidate = {
                "format_id": str(fmt["format_id"]),
                "resolution": res_label,
                "ext": "mp4",
                "fps": fmt.get("fps"),
                "filesize_mb": round(size / (1024 * 1024), 2) if size else None,
                "has_audio": fmt.get("acodec") not in (None, "none"),
            }

            existing = formats_by_res.get(res_label)
            if existing is None or (
                existing["filesize_mb"] is None and candidate["filesize_mb"] is not None
            ):
                formats_by_res[res_label] = candidate

    clean_formats = sorted(
        formats_by_res.values(),
        key=lambda x: int(x["resolution"].replace("p", "")),
        reverse=True,
    )

    return {
        "title": info.get("title", "Unknown Title"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "formats": clean_formats,
    }


def _resolve_output_path(ydl: yt_dlp.YoutubeDL, info: Dict[str, Any]) -> str:
    """Resolve the final merged MP4 file path produced by yt-dlp."""
    requested = info.get("requested_downloads") or []
    for item in requested:
        filepath = item.get("filepath")
        if filepath and os.path.exists(filepath):
            return filepath

    filename = ydl.prepare_filename(info)
    mp4_path = os.path.splitext(filename)[0] + ".mp4"
    if os.path.exists(mp4_path):
        return mp4_path
    return mp4_path


def download_and_merge(
    url: str,
    resolution: str,
    task_id: str,
    task_store: Dict[str, Dict[str, Any]],
) -> None:
    """Download requested video resolution + best audio and mux into MP4 via FFmpeg."""
    try:
        task_store[task_id]["status"] = "downloading"
        task_store[task_id]["stage"] = "Starting download"
        task_store[task_id]["progress"] = None
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        output_template = str(DOWNLOAD_DIR / f"{task_id}_%(title)s.%(ext)s")

        # Select requested video height + best available audio, fallback to best combined stream
        if resolution != "best":
            height = resolution.replace("p", "")
            format_str = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
        else:
            format_str = "bestvideo+bestaudio/best"

        def on_progress(data: Dict[str, Any]) -> None:
            status = data.get("status")
            if status == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate")
                downloaded = data.get("downloaded_bytes")
                info_dict = data.get("info_dict") or {}
                vcodec = info_dict.get("vcodec")
                acodec = info_dict.get("acodec")
                if vcodec and vcodec != "none" and acodec in (None, "none"):
                    task_store[task_id]["stage"] = "Downloading video stream"
                elif acodec and acodec != "none" and vcodec in (None, "none"):
                    task_store[task_id]["stage"] = "Downloading audio stream"
                else:
                    task_store[task_id]["stage"] = "Downloading media"

                if total and downloaded is not None:
                    pct = round(min(99.0, (downloaded / total) * 100), 1)
                    task_store[task_id]["progress"] = pct
            elif status == "finished":
                task_store[task_id]["progress"] = 100.0
                task_store[task_id]["stage"] = "Processing downloaded stream"

        def on_postprocess(data: Dict[str, Any]) -> None:
            if data.get("status") in ("started", "processing"):
                task_store[task_id]["stage"] = "Merging video & audio with FFmpeg"
                task_store[task_id]["progress"] = None

        ydl_opts = {
            "format": format_str,
            "outtmpl": output_template,
            "merge_output_format": "mp4",  # Forces FFmpeg muxing into MP4
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [on_progress],
            "postprocessor_hooks": [on_postprocess],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            final_path = _resolve_output_path(ydl, info)

        task_store[task_id]["file_path"] = final_path
        task_store[task_id]["download_url"] = f"/api/v1/file/{task_id}"
        task_store[task_id]["progress"] = 100.0
        task_store[task_id]["stage"] = "Ready to download"
        task_store[task_id]["status"] = "completed"

    except Exception as exc:
        task_store[task_id]["error"] = str(exc)
        task_store[task_id]["stage"] = "Failed"
        task_store[task_id]["status"] = "failed"
