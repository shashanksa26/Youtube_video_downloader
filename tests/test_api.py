from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app import main, services

client = TestClient(main.app)


def setup_function():
    main.tasks.clear()


def test_get_video_formats_filters_and_sorts():
    mock_info = {
        "title": "Sample Video",
        "duration": 125.5,
        "thumbnail": "https://example.com/thumb.jpg",
        "formats": [
            {
                "format_id": "140",
                "height": None,
                "vcodec": "none",
                "acodec": "mp4a.40.2",
            },
            {
                "format_id": "18",
                "height": 360,
                "vcodec": "avc1",
                "acodec": "mp4a.40.2",
                "fps": 30,
                "filesize": 5 * 1024 * 1024,
            },
            {
                "format_id": "137",
                "height": 1080,
                "vcodec": "avc1",
                "acodec": "none",
                "fps": 29.97,
                "filesize": None,
            },
            {
                "format_id": "248",
                "height": 1080,
                "vcodec": "vp9",
                "acodec": "none",
                "fps": 60,
                "filesize_approx": 20 * 1024 * 1024,
            },
        ],
    }

    mock_ydl = MagicMock()
    mock_ydl.extract_info.return_value = mock_info
    mock_ydl.__enter__.return_value = mock_ydl
    mock_ydl.__exit__.return_value = False

    with patch("app.services.yt_dlp.YoutubeDL", return_value=mock_ydl):
        result = services.get_video_formats("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result["title"] == "Sample Video"
    assert result["duration"] == 125.5
    assert [f["resolution"] for f in result["formats"]] == ["1080p", "360p"]
    assert result["formats"][0]["format_id"] == "248"
    assert result["formats"][0]["filesize_mb"] == 20.0
    assert result["formats"][0]["has_audio"] is False
    assert result["formats"][1]["has_audio"] is True


def test_fetch_formats_endpoint_success_and_error():
    mock_payload = {
        "title": "Demo",
        "duration": 60,
        "thumbnail": None,
        "formats": [
            {
                "format_id": "137",
                "resolution": "1080p",
                "ext": "mp4",
                "fps": 30,
                "filesize_mb": 12.5,
                "has_audio": False,
            }
        ],
    }
    with patch("app.main.get_video_formats", return_value=mock_payload):
        resp = client.get(
            "/api/v1/formats",
            params={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Demo"

    invalid_resp = client.get("/api/v1/formats", params={"url": "not-a-url"})
    assert invalid_resp.status_code == 422

    with patch("app.main.get_video_formats", side_effect=RuntimeError("boom")):
        err_resp = client.get(
            "/api/v1/formats",
            params={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        )
    assert err_resp.status_code == 400


def test_download_status_and_file_flow(tmp_path: Path):
    output_file = tmp_path / "sample.mp4"
    output_file.write_bytes(b"fake-mp4-content")

    def fake_download(url: str, resolution: str, task_id: str, task_store: dict):
        task_store[task_id]["status"] = "completed"
        task_store[task_id]["file_path"] = str(output_file)
        task_store[task_id]["download_url"] = f"/api/v1/file/{task_id}"

    with patch("app.main.download_and_merge", side_effect=fake_download):
        resp = client.post(
            "/api/v1/download",
            json={
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "resolution": "1080p",
            },
        )

    assert resp.status_code == 200
    task_id = resp.json()["task_id"]
    assert resp.json()["status"] == "queued"

    status_resp = client.get(f"/api/v1/status/{task_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "completed"
    assert status_resp.json()["download_url"] == f"/api/v1/file/{task_id}"

    file_resp = client.get(f"/api/v1/file/{task_id}")
    assert file_resp.status_code == 200
    assert file_resp.headers["content-type"] == "video/mp4"
    assert file_resp.content == b"fake-mp4-content"


def test_download_validation_and_error_cases():
    bad_res = client.post(
        "/api/v1/download",
        json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "resolution": "4k-invalid",
        },
    )
    assert bad_res.status_code == 422

    assert client.get("/api/v1/status/missing-id").status_code == 404
    assert client.get("/api/v1/file/missing-id").status_code == 400

    main.tasks["missing-file"] = {
        "status": "completed",
        "file_path": "/nonexistent/path/video.mp4",
        "download_url": "/api/v1/file/missing-file",
        "error": None,
    }
    assert client.get("/api/v1/file/missing-file").status_code == 404


def test_download_and_merge_builds_expected_opts_and_handles_failure(tmp_path: Path):
    captured_opts = {}
    expected_file = tmp_path / "t1_video.mp4"
    expected_file.write_bytes(b"mp4")

    mock_ydl = MagicMock()
    mock_ydl.extract_info.return_value = {
        "title": "video",
        "requested_downloads": [{"filepath": str(expected_file)}],
    }
    mock_ydl.__enter__.return_value = mock_ydl
    mock_ydl.__exit__.return_value = False

    def fake_ydl_ctor(opts):
        captured_opts.update(opts)
        return mock_ydl

    store = {"t1": {"status": "queued", "file_path": None, "download_url": None, "error": None}}
    with patch("app.services.yt_dlp.YoutubeDL", side_effect=fake_ydl_ctor):
        services.download_and_merge("https://youtu.be/abc", "720p", "t1", store)

    assert captured_opts["format"] == "bestvideo[height<=720]+bestaudio/best[height<=720]"
    assert captured_opts["merge_output_format"] == "mp4"
    assert store["t1"]["status"] == "completed"
    assert store["t1"]["file_path"] == str(expected_file)

    store_err = {"t2": {"status": "queued", "file_path": None, "download_url": None, "error": None}}
    with patch("app.services.yt_dlp.YoutubeDL", side_effect=RuntimeError("network error")):
        services.download_and_merge("https://youtu.be/abc", "best", "t2", store_err)

    assert store_err["t2"]["status"] == "failed"
    assert "network error" in store_err["t2"]["error"]


def test_builtin_ui_and_static_assets_served():
    root_resp = client.get("/")
    assert root_resp.status_code == 200
    assert "text/html" in root_resp.headers["content-type"]
    assert "YouTube Video Downloader" in root_resp.text
    assert "/static/app.js" in root_resp.text

    css_resp = client.get("/static/styles.css")
    assert css_resp.status_code == 200

    js_resp = client.get("/static/app.js")
    assert js_resp.status_code == 200
    assert "progress-bar-text" in root_resp.text


def test_progress_hooks_populate_speed_and_mb(tmp_path: Path):
    expected_file = tmp_path / "t_prog.mp4"
    expected_file.write_bytes(b"0" * (2 * 1024 * 1024))
    snapshots = []

    class FakeYdl:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=True):
            hook = self.opts["progress_hooks"][0]
            hook(
                {
                    "status": "downloading",
                    "downloaded_bytes": 5 * 1024 * 1024,
                    "total_bytes": 10 * 1024 * 1024,
                    "speed": 2.5 * 1024 * 1024,
                    "info_dict": {"vcodec": "avc1", "acodec": "none"},
                }
            )
            snapshots.append(dict(store["t_prog"]))
            return {"title": "v", "requested_downloads": [{"filepath": str(expected_file)}]}

    store = {"t_prog": {"status": "queued"}}
    with patch("app.services.yt_dlp.YoutubeDL", side_effect=FakeYdl):
        services.download_and_merge("https://youtu.be/abc", "1080p", "t_prog", store)

    assert snapshots[0]["progress"] == 50.0
    assert snapshots[0]["downloaded_mb"] == 5.0
    assert snapshots[0]["total_mb"] == 10.0
    assert snapshots[0]["speed_mb_s"] == 2.5
    assert store["t_prog"]["status"] == "completed"
    assert store["t_prog"]["total_mb"] == 2.0
    assert store["t_prog"]["speed_mb_s"] is None


def test_cancel_endpoint_and_hook_cleanup(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(services, "DOWNLOAD_DIR", tmp_path)
    part_file = tmp_path / "t_cancel_video.mp4.part"
    part_file.write_bytes(b"partial")

    main.tasks["queued-id"] = {
        "status": "queued",
        "progress": None,
        "stage": "Queued",
        "downloaded_mb": None,
        "total_mb": None,
        "speed_mb_s": None,
        "cancel_requested": False,
        "file_path": None,
        "download_url": None,
        "error": None,
    }
    cancel_resp = client.post("/api/v1/cancel/queued-id")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"
    assert cancel_resp.json()["stage"] == "Cancelled"

    assert client.post("/api/v1/cancel/missing-id").status_code == 404

    main.tasks["done-id"] = {
        "status": "completed",
        "progress": 100.0,
        "stage": "Ready to download",
        "downloaded_mb": 1.0,
        "total_mb": 1.0,
        "speed_mb_s": None,
        "cancel_requested": False,
        "file_path": None,
        "download_url": "/api/v1/file/done-id",
        "error": None,
    }
    assert client.post("/api/v1/cancel/done-id").status_code == 400

    class CancellingYdl:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=True):
            store["t_cancel"]["cancel_requested"] = True
            self.opts["progress_hooks"][0]({"status": "downloading"})
            return {}

    store = {"t_cancel": {"status": "queued", "cancel_requested": False}}
    with patch("app.services.yt_dlp.YoutubeDL", side_effect=CancellingYdl):
        services.download_and_merge("https://youtu.be/abc", "1080p", "t_cancel", store)

    assert store["t_cancel"]["status"] == "cancelled"
    assert store["t_cancel"]["stage"] == "Cancelled"
    assert not part_file.exists()

