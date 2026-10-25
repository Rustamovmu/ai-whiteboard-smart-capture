"""Filesystem repository with atomic metadata replacement and per-session locking."""
import copy
import json
import os
import threading
import uuid
from pathlib import Path

import cv2
import numpy as np

from ..schemas import Settings, SessionCreate, utcnow


class Store:
    def __init__(self, root: Path):
        self.root = root / "sessions"
        self.root.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.RLock] = {}
        self._guard = threading.Lock()

    def directory(self, session_id: str) -> Path:
        try:
            if str(uuid.UUID(session_id)) != session_id:
                raise ValueError()
        except (ValueError, AttributeError):
            raise ValueError("Invalid session identifier") from None
        return self.root / session_id

    def lock(self, session_id: str) -> threading.RLock:
        self.directory(session_id)
        with self._guard:
            return self._locks.setdefault(session_id, threading.RLock())

    def read(self, session_id: str) -> dict:
        with self.lock(session_id):
            path = self.directory(session_id) / "metadata.json"
            if not path.is_file():
                raise FileNotFoundError("Session not found")
            try:
                return json.loads(path.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Cannot read session metadata: {exc}") from exc

    def write(self, session: dict) -> None:
        with self.lock(session["id"]):
            folder = self.directory(session["id"])
            folder.mkdir(parents=True, exist_ok=True)
            temporary = folder / f"metadata.{uuid.uuid4().hex}.tmp"
            try:
                with temporary.open("w") as stream:
                    json.dump(session, stream, ensure_ascii=False, indent=2, allow_nan=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.replace(folder / "metadata.json")
            finally:
                temporary.unlink(missing_ok=True)

    def create(self, payload: SessionCreate) -> dict:
        session = {
            "id": str(uuid.uuid4()), **payload.model_dump(), "created_at": utcnow(),
            "settings": Settings().model_dump(), "calibration": None, "captures": [],
            "events": [], "saved_requests": [], "next_sequence": 1,
            "stats": {key: 0 for key in (
                "frames_analyzed", "captures_accepted", "duplicates_ignored", "blur_rejected",
                "motion_delayed", "obstruction_delayed", "quality_rejected", "meaningful_changes", "manual_captures", "insignificant_ignored",
            )},
        }
        self.write(session)
        return session

    def list(self) -> list[dict]:
        result = []
        for path in self.root.glob("*/metadata.json"):
            data = self.read(path.parent.name)
            result.append({**{k: v for k, v in data.items() if k not in {"captures", "events", "saved_requests"}},
                           "capture_count": len(data["captures"])})
        return sorted(result, key=lambda x: x["created_at"], reverse=True)

    @staticmethod
    def public(session: dict) -> dict:
        return {k: copy.deepcopy(v) for k, v in session.items() if k != "saved_requests"}

    def patch(self, session_id: str, changes: dict) -> dict:
        with self.lock(session_id):
            data = self.read(session_id)
            data.update(changes)
            self.write(data)
            return data

    def capture_path(self, session_id: str, capture_id: str, variant: str = "original") -> Path:
        if variant not in {"original", "enhanced", "thumbnail"}:
            raise ValueError("Unknown image variant")
        session = self.read(session_id)
        if not any(c["id"] == capture_id for c in session["captures"]):
            raise FileNotFoundError("Capture not found")
        return self.directory(session_id) / "captures" / f"{capture_id}_{variant}.jpg"

    def save_capture(self, session_id: str, image: np.ndarray, enhanced: np.ndarray, request_id: str,
                     kind: str, measurements: dict, revision: str, source_seconds: float | None = None) -> tuple[dict | None, bool]:
        with self.lock(session_id):
            session = self.read(session_id)
            if request_id in session["saved_requests"]:
                return next((c for c in session["captures"] if c["request_id"] == request_id), None), False
            capture_id = str(uuid.uuid4())
            folder = self.directory(session_id) / "captures"
            folder.mkdir(exist_ok=True)
            thumb = cv2.resize(image, (320, max(1, round(image.shape[0] * 320 / image.shape[1]))))
            written = []
            try:
                for variant, pixels in (("original", image), ("enhanced", enhanced), ("thumbnail", thumb)):
                    path = folder / f"{capture_id}_{variant}.jpg"
                    if not cv2.imwrite(str(path), pixels, [cv2.IMWRITE_JPEG_QUALITY, 94]):
                        raise OSError("Image encoder could not save capture")
                    written.append(path)
                capture = {
                    "id": capture_id, "sequence": session["next_sequence"], "name": f"Capture {session['next_sequence']:02d}",
                    "note": "", "timestamp": utcnow(), "source_seconds": source_seconds,
                    "capture_type": kind, "request_id": request_id, "calibration_revision": revision,
                    "measurements": measurements, "ocr": {"status": "disabled", "text": "", "segments": []},
                }
                session["captures"].append(capture)
                session["next_sequence"] += 1
                session["saved_requests"].append(request_id)
                session["stats"]["captures_accepted"] += 1
                if kind == "manual":
                    session["stats"]["manual_captures"] += 1
                self.write(session)
            except Exception:
                for path in written:
                    path.unlink(missing_ok=True)
                raise
            return capture, True

    def edit_capture(self, session_id: str, capture_id: str, changes: dict) -> dict:
        with self.lock(session_id):
            data = self.read(session_id)
            capture = next((c for c in data["captures"] if c["id"] == capture_id), None)
            if capture is None:
                raise FileNotFoundError("Capture not found")
            capture.update(changes)
            self.write(data)
            return capture

    def delete_capture(self, session_id: str, capture_id: str) -> None:
        with self.lock(session_id):
            session = self.read(session_id)
            paths = [self.capture_path(session_id, capture_id, v) for v in ("original", "enhanced", "thumbnail")]
            session["captures"] = [c for c in session["captures"] if c["id"] != capture_id]
            self.write(session)
            for path in paths:
                path.unlink(missing_ok=True)

    def record_event(self, session_id: str, event: dict) -> None:
        with self.lock(session_id):
            data = self.read(session_id)
            data["events"] = (data["events"] + [{"timestamp": utcnow(), **event}])[-1000:]
            self.write(data)

    def add_stats(self, session_id: str, counters: dict) -> None:
        if not any(counters.values()):
            return
        with self.lock(session_id):
            data = self.read(session_id)
            for key, count in counters.items():
                data["stats"][key] = data["stats"].get(key, 0) + count
            self.write(data)
