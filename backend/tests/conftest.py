import base64
from pathlib import Path

import cv2
import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.schemas import SessionCreate
from backend.app.services.storage import Store
from scripts.demo_assets import board


class MissingDetector:
    """Explicit missing-model test double; never installed in the production app."""
    def status(self):
        return {"model": "unavailable-test-fixture", "device": "cpu", "available": False,
                "installed": False, "status": "unavailable", "error": None}

    def detect(self, frame, confidence):
        return {**self.status(), "boxes": [], "detected_at": None, "inference_ms": None}


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


@pytest.fixture
def session(store):
    return store.create(SessionCreate(title="Vision lecture", course="Computer Vision"))


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path, tmp_path / "models", MissingDetector())
    with TestClient(app) as client:
        yield client


@pytest.fixture
def packet():
    def make(image=None, frame_id="frame-1", kind="frame", force=False):
        image = board(1) if image is None else image
        ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
        assert ok
        return {"type": kind, "frame_id": frame_id, "source_id": "test-camera", "width": image.shape[1],
                "height": image.shape[0], "jpeg": base64.b64encode(buffer).decode(), "force": force}
    return make


FULL_CALIBRATION = {"points": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}, {"x": 0, "y": 1}],
                    "source_id": "test-camera", "aspect_ratio": 800 / 450}


def create_calibrated(client):
    session = client.post("/api/sessions", json={"title": "Test lecture", "course": "AI"}).json()
    response = client.put(f"/api/sessions/{session['id']}/calibration", json=FULL_CALIBRATION)
    assert response.status_code == 200
    return response.json()
