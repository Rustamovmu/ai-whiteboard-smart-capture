"""Central state machine: analysis is separate from committing a successful save."""
import numpy as np

from ..schemas import Settings
from .metrics import compare, motion_score, quality


class DecisionEngine:
    def __init__(self):
        self.previous: np.ndarray | None = None
        self.baseline: np.ndarray | None = None
        self.stable_since: float | None = None
        self.last_timestamp: float | None = None
        self.last_capture: float | None = None

    def reset_temporal(self) -> None:
        self.previous = None
        self.stable_since = None
        self.last_timestamp = None
        self.last_capture = None

    def analyze(self, board: np.ndarray, timestamp: float, settings: Settings, obstruction: float | None) -> dict:
        measured_quality = quality(board, settings)
        motion = motion_score(self.previous, board)
        if self.last_timestamp is not None and (timestamp <= self.last_timestamp or timestamp - self.last_timestamp > 3):
            self.stable_since = None
            motion = 1.0
        self.previous = board.copy()
        self.last_timestamp = timestamp
        blocked = obstruction is not None and obstruction >= settings.obstruction_threshold
        if motion > settings.motion_threshold or blocked:
            self.stable_since = None
        elif self.stable_since is None:
            self.stable_since = timestamp
        stable_for = max(0, timestamp - self.stable_since) if self.stable_since is not None else 0
        change = compare(self.baseline, board, settings)
        result = {"quality": measured_quality, "motion_score": motion, "stable_seconds": round(stable_for, 3),
                  "change": change, "obstruction_fraction": obstruction,
                  "obstruction_status": "unknown" if obstruction is None else "blocked" if blocked else "clear",
                  "decision": "wait", "state": "OBSERVING", "reason": "Observing whiteboard"}
        if blocked:
            result.update(state="MOTION_OR_OCCLUSION", reason="Person blocking whiteboard", counter="obstruction_delayed")
        elif motion > settings.motion_threshold:
            result.update(state="MOTION_OR_OCCLUSION", reason="Motion detected; waiting for writing to finish", counter="motion_delayed")
        elif measured_quality["status"] != "acceptable":
            counter = "blur_rejected" if any("sharpness" in r for r in measured_quality["reasons"]) else "quality_rejected"
            result.update(state="REJECTED", decision="reject", reason="; ".join(measured_quality["reasons"]), counter=counter)
            self.stable_since = None
        elif stable_for + 1e-6 < settings.stability_seconds:
            result.update(state="WAITING_FOR_STABILITY", reason="Waiting for stable board")
        elif not change["meaningful"]:
            counter = "duplicates_ignored" if self.baseline is not None and change["score"] < settings.change_threshold * 0.4 else "insignificant_ignored"
            result.update(state="NO_CHANGE", decision="ignore", reason="No meaningful change / duplicate board state", counter=counter)
        elif not settings.auto_capture:
            result.update(state="CHANGE_ANALYSIS", reason="Meaningful change detected; automatic capture is paused")
        elif self.last_capture is not None and timestamp - self.last_capture < settings.capture_interval:
            result.update(state="CHANGE_ANALYSIS", reason="Meaningful change pending capture cooldown")
        else:
            result.update(state="CAPTURE_ACCEPTED", decision="capture", reason="Stable, clear, meaningful board change")
        return result

    def commit(self, board: np.ndarray, timestamp: float) -> None:
        self.baseline = board.copy()
        self.last_capture = timestamp
