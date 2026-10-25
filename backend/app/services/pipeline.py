"""One shared processing path for webcam and timestamped video replay."""
import base64
import collections
import io
import time

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

from ..config import MAX_FRAME_BYTES, MAX_IMAGE_PIXELS
from ..schemas import FrameRequest, Settings
from ..vision.decision_engine import DecisionEngine
from ..vision.geometry import obstruction_fraction, rectify, suggest_board
from ..vision.metrics import enhance
from .storage import Store


def decode_jpeg(encoded: str, width: int, height: int) -> np.ndarray:
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        raise ValueError("Frame is not valid base64") from None
    if not data or len(data) > MAX_FRAME_BYTES:
        raise ValueError("Frame exceeds 2 MB or is empty")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format != "JPEG" or probe.width * probe.height > MAX_IMAGE_PIXELS:
                raise ValueError("Only bounded JPEG camera frames are accepted")
            if probe.size != (width, height):
                raise ValueError("Declared image dimensions do not match the JPEG")
            probe.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Cannot decode JPEG frame") from exc
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Cannot decode JPEG frame")
    return frame


def preview_jpeg(image: np.ndarray, width: int = 480) -> str:
    if image.shape[1] > width:
        image = cv2.resize(image, (width, max(1, round(image.shape[0] * width / image.shape[1]))))
    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 75])
    if not ok:
        raise ValueError("Could not encode preview")
    return base64.b64encode(buffer).decode()


class Pipeline:
    def __init__(self, store: Store, detector, ocr):
        self.store, self.detector, self.ocr = store, detector, ocr
        self.engines: dict[str, DecisionEngine] = {}
        self.revisions: dict[str, str] = {}
        self.detections: dict[str, tuple[float, dict]] = {}
        self.counters: dict[str, collections.Counter] = {}
        self.last_flush: dict[str, float] = {}
        self.owners: dict[str, str] = {}

    def acquire(self, sid: str, owner: str) -> None:
        with self.store.lock(sid):
            self.store.read(sid)
            if sid in self.owners and self.owners[sid] != owner:
                raise ValueError("This session already has an active analysis source")
            self.owners[sid] = owner

    def release(self, sid: str, owner: str) -> None:
        with self.store.lock(sid):
            if self.owners.get(sid) == owner:
                self.flush(sid)
                self.owners.pop(sid, None)
                self.engines.pop(sid, None)
                self.revisions.pop(sid, None)
                self.detections.pop(sid, None)

    def flush(self, sid: str) -> None:
        pending = self.counters.pop(sid, collections.Counter())
        self.store.add_stats(sid, dict(pending))
        self.last_flush[sid] = time.monotonic()

    def reset(self, sid: str) -> None:
        self.flush(sid)
        self.engines.pop(sid, None)
        self.revisions.pop(sid, None)
        self.detections.pop(sid, None)

    def _engine(self, sid: str, revision: str, session: dict) -> DecisionEngine:
        if sid not in self.engines or self.revisions.get(sid) != revision:
            engine = DecisionEngine()
            reference = self.store.directory(sid) / "baseline.png"
            if session.get("baseline_revision") == revision and reference.exists():
                engine.baseline = cv2.imread(str(reference))
            self.engines[sid] = engine
            self.revisions[sid] = revision
        return self.engines[sid]

    def _commit(self, sid: str, engine: DecisionEngine, board: np.ndarray, timestamp: float, revision: str) -> None:
        path = self.store.directory(sid) / "baseline.next.png"
        if not cv2.imwrite(str(path), board):
            raise OSError("Cannot persist comparison baseline")
        path.replace(path.with_name("baseline.png"))
        self.store.patch(sid, {"baseline_revision": revision})
        engine.commit(board, timestamp)

    def process_request(self, sid: str, request: FrameRequest, owner: str) -> dict:
        frame = decode_jpeg(request.jpeg, request.width, request.height)
        return self.process(sid, frame, time.monotonic(), request.source_id, request.frame_id,
                            owner, request.type, request.force)

    def process(self, sid: str, frame: np.ndarray, timestamp: float, source_id: str, frame_id: str,
                owner: str, kind: str = "frame", force: bool = False, replay: bool = False) -> dict:
        started = time.perf_counter()
        with self.store.lock(sid):
            if self.owners.get(sid) != owner:
                raise ValueError("Session analysis source is no longer active")
            session = self.store.read(sid)
            settings = Settings(**session["settings"])
            response = {"type": "analysis", "frame_id": frame_id, "capture": None,
                        "detector": self.detector.status(), "calibration": session["calibration"]}
            if kind == "suggest":
                return {**response, "suggestion": suggest_board(frame), "state": "UNCALIBRATED", "reason": "Confirm or adjust the proposed board corners"}
            calibration = session["calibration"]
            ratio = frame.shape[1] / frame.shape[0]
            if (not calibration or calibration["source_id"] != source_id or
                    abs(ratio / calibration["aspect_ratio"] - 1) > 0.02):
                return {**response, "state": "UNCALIBRATED", "decision": "wait", "reason": "Calibrate this camera or video before capture"}
            revision = calibration["revision"]
            board = rectify(frame, calibration["points"])
            engine = self._engine(sid, revision, session)
            cached_at, detection = self.detections.get(sid, (-1e12, {}))
            inferred = False
            if settings.ai_enabled and (not detection or timestamp - cached_at >= settings.detector_interval or timestamp < cached_at):
                detection = self.detector.detect(frame, settings.person_confidence)
                self.detections[sid] = (timestamp, detection)
                inferred = True
            if not settings.ai_enabled:
                detection = {**self.detector.status(), "status": "disabled", "available": False, "boxes": [], "detected_at": None}
            overlap = obstruction_fraction(frame.shape, calibration["points"], detection["boxes"]) if detection.get("available") else None
            analysis = engine.analyze(board, timestamp, settings, overlap)
            # Capture candidates and manual overrides always use inference on the CURRENT frame.
            if settings.ai_enabled and not inferred and (analysis["decision"] == "capture" or kind == "manual"):
                detection = self.detector.detect(frame, settings.person_confidence)
                self.detections[sid] = (timestamp, detection)
                overlap = obstruction_fraction(frame.shape, calibration["points"], detection["boxes"]) if detection.get("available") else None
                analysis["obstruction_fraction"] = overlap
                analysis["obstruction_status"] = "unknown" if overlap is None else "blocked" if overlap >= settings.obstruction_threshold else "clear"
                if overlap is not None and overlap >= settings.obstruction_threshold:
                    engine.stable_since = None
                    analysis.update(state="MOTION_OR_OCCLUSION", decision="wait", stable_seconds=0,
                                    reason="Person blocking whiteboard", counter="obstruction_delayed")
            warnings = list(analysis["quality"]["reasons"])
            if analysis["obstruction_status"] == "blocked":
                warnings.append("A person is obstructing the whiteboard")
            elif analysis["obstruction_status"] == "unknown":
                warnings.append("AI obstruction detection is unavailable or disabled")
            request_key = f"{source_id}:{frame_id}"
            if kind == "manual" and request_key in session["saved_requests"]:
                return {**response, **analysis, "state": "NO_CHANGE", "decision": "ignore", "reason": "Manual request already saved"}
            should_save = analysis["decision"] == "capture"
            if kind == "manual":
                should_save = not warnings or force
                analysis.update(decision="capture" if should_save else "confirm", state="CAPTURE_ACCEPTED" if should_save else "MANUAL_WARNING",
                                reason="Manual capture requested" if should_save else "; ".join(warnings))
            counts = self.counters.setdefault(sid, collections.Counter())
            counts["frames_analyzed"] += 1
            if kind != "manual" and analysis.get("counter"):
                counts[analysis["counter"]] += 1
            capture = None
            if should_save:
                analysis["degraded"] = not detection.get("available", False)
                analysis["warnings"] = warnings
                analysis["detector"] = detection
                is_clear = analysis["change"]["change_type"] == "board_cleared"
                if kind != "manual" and is_clear and not settings.save_cleared_board:
                    self.store.record_event(sid, {"event": "board_cleared", "source_seconds": timestamp if replay else None,
                                                  "calibration_revision": revision, "measurements": analysis})
                    self._commit(sid, engine, board, timestamp, revision)
                    analysis.update(state="BOARD_CLEARED", decision="event", reason="Board cleared; previous notes preserved")
                    counts["meaningful_changes"] += 1
                else:
                    capture, created = self.store.save_capture(sid, board, enhance(board), request_key,
                                                              "manual" if kind == "manual" else "automatic",
                                                              analysis.copy(), revision, timestamp if replay else None)
                    if created:
                        self._commit(sid, engine, board, timestamp, revision)
                        if kind != "manual":
                            counts["meaningful_changes"] += 1
                        if settings.ocr_enabled:
                            self.ocr.submit(sid, capture["id"])
                    else:
                        analysis.update(state="NO_CHANGE", decision="ignore", reason="Request was already saved")
                        capture = None
            if time.monotonic() - self.last_flush.get(sid, 0) > 5 or capture:
                self.flush(sid)
            stats = self.store.read(sid)["stats"].copy()
            for key, value in self.counters.get(sid, {}).items():
                stats[key] = stats.get(key, 0) + value
            return {**response, **analysis, "detector": detection, "warnings": warnings,
                    "capture": capture, "stats": stats, "board_preview": preview_jpeg(board),
                    "processing_ms": round((time.perf_counter() - started) * 1000, 2),
                    "source_seconds": timestamp if replay else None}
