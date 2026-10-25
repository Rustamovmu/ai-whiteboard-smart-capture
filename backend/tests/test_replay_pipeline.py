import time

import cv2
import pytest

from backend.app.schemas import SessionCreate
from backend.app.services.ocr import OCRService
from backend.app.services.pipeline import Pipeline
from scripts.demo_assets import board
from .conftest import FULL_CALIBRATION, create_calibrated


def test_video_upload_validation(client):
    session = create_calibrated(client)
    url = f"/api/sessions/{session['id']}/replays"
    assert client.post(url, files={"file": ("lecture.exe", b"bad", "application/octet-stream")}).status_code == 400
    assert client.post(url, files={"file": ("lecture.mp4", b"not a video", "video/mp4")}).status_code == 400


def test_replay_pause_seek_cancel_releases_owner(client, tmp_path):
    path = tmp_path / "controls.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 5, (800, 450))
    assert writer.isOpened()
    for _ in range(50):
        writer.write(board(1))
    writer.release()
    session = create_calibrated(client)
    sid = session["id"]
    with path.open("rb") as stream:
        job = client.post(f"/api/sessions/{sid}/replays", files={"file": ("controls.avi", stream, "video/x-msvideo")}).json()
    root = f"/api/sessions/{sid}/replays/{job['id']}"
    client.put(f"/api/sessions/{sid}/calibration", json={**FULL_CALIBRATION, "source_id": job["source_id"]})
    assert client.post(f"{root}/start").status_code == 200
    assert client.post(f"{root}/control", json={"action": "pause"}).json()["status"] == "paused"
    assert client.post(f"{root}/control", json={"action": "seek", "seconds": 1}).status_code == 200
    assert client.post(f"{root}/control", json={"action": "resume"}).json()["status"] == "running"
    assert client.post(f"{root}/control", json={"action": "cancel"}).json()["status"] == "cancelled"
    deadline = time.monotonic() + 5
    while sid in client.app.state.pipeline.owners and time.monotonic() < deadline:
        time.sleep(.02)
    assert sid not in client.app.state.pipeline.owners


def test_replay_manual_warning_force_and_duplicate(client, tmp_path):
    path = tmp_path / "manual.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 5, (800, 450))
    assert writer.isOpened()
    for _ in range(10):
        writer.write(board(1))
    writer.release()
    session = create_calibrated(client)
    sid = session["id"]
    with path.open("rb") as stream:
        job = client.post(f"/api/sessions/{sid}/replays", files={"file": ("manual.avi", stream, "video/x-msvideo")}).json()
    client.put(f"/api/sessions/{sid}/calibration", json={**FULL_CALIBRATION, "source_id": job["source_id"]})
    root = f"/api/sessions/{sid}/replays/{job['id']}/manual"
    assert client.post(root, json={"frame_id": "manual"}).json()["decision"] == "confirm"
    result = client.post(root, json={"frame_id": "manual", "force": True}).json()
    assert result["capture"]["capture_type"] == "manual"
    assert result["capture"]["source_seconds"] == 0
    assert client.post(root, json={"frame_id": "manual", "force": True}).json()["decision"] == "ignore"


def test_replay_uses_shared_pipeline_and_source_time(client, tmp_path):
    path = tmp_path / "lecture.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 5, (800, 450))
    assert writer.isOpened()
    for i in range(17 * 5):
        seconds = i / 5
        stage = 0 if seconds < 1 or seconds >= 13 else 1 if seconds < 5 or seconds >= 9 else 2
        writer.write(board(stage))
    writer.release()
    session = create_calibrated(client)
    sid = session["id"]
    with path.open("rb") as stream:
        response = client.post(f"/api/sessions/{sid}/replays", files={"file": ("lecture.avi", stream, "video/x-msvideo")})
    assert response.status_code == 201
    job = response.json()
    client.put(f"/api/sessions/{sid}/calibration", json={**FULL_CALIBRATION, "source_id": job["source_id"]})
    client.patch(f"/api/sessions/{sid}/settings", json={"stability_seconds": .5, "capture_interval": .5})
    assert client.post(f"/api/sessions/{sid}/replays/{job['id']}/start").status_code == 200
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        job = client.get(f"/api/sessions/{sid}/replays/{job['id']}").json()
        if job["status"] in {"completed", "error"}:
            break
        time.sleep(.05)
    assert job["status"] == "completed", job.get("error")
    result = client.get(f"/api/sessions/{sid}").json()
    assert len(result["captures"]) == 3
    assert [c["measurements"]["change"]["change_type"] for c in result["captures"]] == ["new_content", "new_content", "content_removed"]
    assert len([e for e in result["events"] if e["event"] == "board_cleared"]) == 1
    assert all(c["source_seconds"] is not None for c in result["captures"])
    assert [c["source_seconds"] for c in result["captures"]] == sorted(c["source_seconds"] for c in result["captures"])
    assert client.get(f"/api/sessions/{sid}/export/pdf").content.startswith(b"%PDF")


class CandidateBlockedDetector:
    """Test double proves the candidate uses fresh inference, not stale clear boxes."""
    def __init__(self):
        self.calls = 0

    def status(self):
        return {"available": True, "installed": True, "status": "active", "model": "EXPLICIT TEST DOUBLE", "device": "test"}

    def detect(self, frame, confidence):
        self.calls += 1
        return {**self.status(), "boxes": [] if self.calls == 1 else [{"box": [.2, 0, .6, 1], "confidence": .9}],
                "detected_at": "test-timestamp", "inference_ms": 0}


def test_fresh_ai_candidate_check_suppresses_capture(store, tmp_path):
    session = store.create(SessionCreate(title="Detector contract"))
    sid = session["id"]
    store.patch(sid, {"calibration": {**FULL_CALIBRATION, "revision": "test-revision"},
                      "settings": {**session["settings"], "detector_interval": 5}})
    detector = CandidateBlockedDetector()
    pipeline = Pipeline(store, detector, OCRService(store, tmp_path))
    pipeline.acquire(sid, "test")
    try:
        pipeline.process(sid, board(1), 0, "test-camera", "1", "test")
        pipeline.process(sid, board(1), .2, "test-camera", "2", "test")
        result = pipeline.process(sid, board(1), 2.3, "test-camera", "3", "test")
        assert detector.calls == 2
        assert result["state"] == "MOTION_OR_OCCLUSION"
        assert result["capture"] is None
        assert result["obstruction_fraction"] > .3
        for stamp in (2.5, 3, 4):
            assert pipeline.process(sid, board(1), stamp, "test-camera", str(stamp), "test")["capture"] is None
    finally:
        pipeline.release(sid, "test")


def test_one_owner_per_session_and_ocrlib_optional(store, session, tmp_path):
    pipeline = Pipeline(store, CandidateBlockedDetector(), OCRService(store, tmp_path))
    sid = session["id"]
    pipeline.acquire(sid, "first")
    with pytest.raises(ValueError, match="active analysis source"):
        pipeline.acquire(sid, "second")
    pipeline.release(sid, "first")
    pipeline.acquire(sid, "second")
    pipeline.release(sid, "second")
    capture, _ = store.save_capture(sid, board(1), board(1), "ocr-test", "manual", {}, "r")
    pipeline.ocr.submit(sid, capture["id"])
    assert store.read(sid)["captures"][0]["ocr"]["status"] == "unavailable"
