import io
import json
import time
import types
import zipfile

import cv2
import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.schemas import Settings
from backend.app.services.exports import export_session
from backend.app.services.storage import Store
from backend.app.vision.person_detection import PersonDetector
from scripts.demo_assets import board
from .conftest import MissingDetector, create_calibrated

ORIGIN = {"origin": "http://127.0.0.1:5173"}


def test_atomic_storage_save_edit_delete_and_restart(store, session):
    sid = session["id"]
    capture, created = store.save_capture(sid, board(1), board(1), "unique-request", "manual", {}, "rev")
    assert created
    duplicate, created = store.save_capture(sid, board(2), board(2), "unique-request", "manual", {}, "rev")
    assert not created and duplicate["id"] == capture["id"]
    store.edit_capture(sid, capture["id"], {"name": "Formula", "note": "Review this"})
    reopened = Store(store.root.parent).read(sid)
    assert reopened["captures"][0]["note"] == "Review this"
    store.delete_capture(sid, capture["id"])
    assert store.read(sid)["captures"] == []
    assert "unique-request" in store.read(sid)["saved_requests"]


def test_filesystem_and_origin_protection(client, store):
    with pytest.raises(ValueError):
        store.read("../../etc")
    assert client.get("/api/sessions", headers={"origin": "https://evil.example"}).status_code == 403
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/sessions/not-a-session", headers={"origin": "https://evil.example"}):
            pass


def test_rest_validation_and_presets(client):
    assert client.post("/api/sessions", json={"title": ""}).status_code == 422
    session = create_calibrated(client)
    sid = session["id"]
    assert client.patch(f"/api/sessions/{sid}/settings", json={"processing_fps": 100}).status_code == 422
    assert client.patch(f"/api/sessions/{sid}/settings", json={"invented": True}).status_code == 422
    client.patch(f"/api/sessions/{sid}/settings", json={"auto_capture": False})
    result = client.post(f"/api/sessions/{sid}/presets/high").json()
    assert result["settings"]["stability_seconds"] == 1.25
    assert result["settings"]["auto_capture"] is False


def test_websocket_capture_gallery_persistence_and_exports(client, packet, monkeypatch):
    session = create_calibrated(client)
    sid = session["id"]
    clock = [0.0]
    monkeypatch.setattr("backend.app.services.pipeline.time", types.SimpleNamespace(monotonic=lambda: clock[0], perf_counter=time.perf_counter))
    with client.websocket_connect(f"/ws/sessions/{sid}", headers=ORIGIN) as ws:
        assert ws.receive_json()["type"] == "connected"
        results = []
        for index, stamp in enumerate((0, .2, 1, 2.3, 2.6, 3, 4)):
            clock[0] = stamp
            ws.send_json(packet(frame_id=f"frame-{index}"))
            results.append(ws.receive_json())
        assert sum(bool(result["capture"]) for result in results) == 1
        assert results[-1]["decision"] == "ignore"
        assert results[-1]["obstruction_status"] == "unknown"
        capture = next(r["capture"] for r in results if r["capture"])
        assert capture["measurements"]["degraded"] is True
    saved = client.get(f"/api/sessions/{sid}").json()
    assert len(saved["captures"]) == 1
    assert saved["stats"]["frames_analyzed"] == 7
    assert client.get(f"/api/sessions/{sid}/captures/{capture['id']}/image").headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/sessions/{sid}/captures/{capture['id']}/image?variant=../../metadata").status_code == 400
    pdf = client.get(f"/api/sessions/{sid}/export/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
    assert b"/Subtype /Image" in pdf.content
    archive = client.get(f"/api/sessions/{sid}/export/zip")
    with zipfile.ZipFile(io.BytesIO(archive.content)) as zipped:
        assert "capture_0001.jpg" in zipped.namelist()
        assert len(json.loads(zipped.read("metadata.json"))["captures"]) == 1
    assert client.get(f"/api/sessions/{sid}/export/json").json()["title"] == "Test lecture"


def test_websocket_malformed_input_and_disconnect_recovery(client, packet):
    session = create_calibrated(client)
    sid = session["id"]
    for _ in range(2):
        with client.websocket_connect(f"/ws/sessions/{sid}", headers=ORIGIN) as ws:
            assert ws.receive_json()["type"] == "connected"
            ws.send_text("invalid-json")
            assert ws.receive_json()["type"] == "error"
            ws.send_json({**packet(), "jpeg": "bad-data"})
            assert ws.receive_json()["type"] == "error"
            ws.send_json(packet())
            assert ws.receive_json()["type"] == "analysis"


def test_manual_warning_override_and_idempotence(client, packet):
    session = create_calibrated(client)
    sid = session["id"]
    with client.websocket_connect(f"/ws/sessions/{sid}", headers=ORIGIN) as ws:
        ws.receive_json()
        ws.send_json(packet(frame_id="manual-1", kind="manual"))
        assert ws.receive_json()["decision"] == "confirm"
        ws.send_json(packet(frame_id="manual-1", kind="manual", force=True))
        result = ws.receive_json()
        assert result["capture"]["capture_type"] == "manual"
        ws.send_json(packet(frame_id="manual-1", kind="manual", force=True))
        assert ws.receive_json()["decision"] == "ignore"
    assert len(client.get(f"/api/sessions/{sid}").json()["captures"]) == 1


def test_missing_ai_files_are_explicit(tmp_path):
    detector = PersonDetector(tmp_path / "missing", tmp_path / "config")
    result = detector.detect(board(1), .35)
    assert result["available"] is False
    assert result["status"] == "unavailable"
    assert result["detected_at"] is None and result["boxes"] == []


def test_session_survives_app_restart(tmp_path, packet):
    first = create_app(tmp_path, tmp_path / "models", MissingDetector())
    with TestClient(first) as client:
        session = create_calibrated(client)
        sid = session["id"]
        with client.websocket_connect(f"/ws/sessions/{sid}", headers=ORIGIN) as ws:
            ws.receive_json()
            ws.send_json(packet(kind="manual", force=True))
            assert ws.receive_json()["capture"]
    with TestClient(create_app(tmp_path, tmp_path / "models", MissingDetector())) as client:
        restored = client.get(f"/api/sessions/{sid}").json()
        assert restored["title"] == "Test lecture"
        assert len(restored["captures"]) == 1


def test_export_empty_session_and_long_notes(store, session):
    empty = export_session(store, session["id"], "pdf")
    assert empty.read_bytes().startswith(b"%PDF")
    empty_size = empty.stat().st_size
    capture, _ = store.save_capture(session["id"], board(2), board(2), "long", "automatic", {}, "r")
    store.edit_capture(session["id"], capture["id"], {"note": "<formula> & important text. " * 1500})
    assert export_session(store, session["id"], "pdf").stat().st_size > empty_size
