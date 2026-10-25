"""Bounded, cancellable OpenCV replay jobs using source time rather than wall time."""
import threading
import time
import uuid
from pathlib import Path

import cv2

from .pipeline import preview_jpeg


class ReplayManager:
    def __init__(self, pipeline):
        self.pipeline = pipeline
        self.jobs: dict[str, dict] = {}
        self.lock = threading.RLock()
        self.threads: dict[str, threading.Thread] = {}

    def register(self, sid: str, path: Path) -> dict:
        reader = cv2.VideoCapture(str(path))
        try:
            fps = float(reader.get(cv2.CAP_PROP_FPS))
            frames = int(reader.get(cv2.CAP_PROP_FRAME_COUNT))
            width, height = int(reader.get(cv2.CAP_PROP_FRAME_WIDTH)), int(reader.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if width <= 0 or height <= 0 or width * height > 16_000_000 or not 0 < fps <= 240 or frames <= 0:
                raise ValueError("Video has invalid dimensions, timestamps, or unsupported codec")
            ok, first = reader.read()
            if not ok:
                raise ValueError("Video codec cannot be decoded by this OpenCV installation")
            with self.lock:
                if len(self.jobs) >= 20:
                    old = next((key for key, j in self.jobs.items() if j["status"] not in {"running", "paused"}), None)
                    if old is None:
                        raise ValueError("Replay job limit reached")
                    removed = self.jobs.pop(old)
                    removed["path"].unlink(missing_ok=True)
                    self.threads.pop(old, None)
                job_id = str(uuid.uuid4())
                job = {"id": job_id, "session_id": sid, "source_id": f"video:{job_id}", "path": path,
                       "width": width, "height": height, "fps": fps, "duration": frames / fps,
                       "position": 0.0, "progress": 0.0, "status": "ready", "preview": preview_jpeg(first, 960),
                       "analysis": None, "error": None, "run_id": str(uuid.uuid4()), "seek": None}
                self.jobs[job_id] = job
                return self.public(job)
        finally:
            reader.release()

    @staticmethod
    def public(job: dict) -> dict:
        return {k: v for k, v in job.items() if k not in {"path", "seek", "run_id", "manual_frame", "owner"}}

    def get(self, sid: str, job_id: str) -> dict:
        with self.lock:
            job = self.jobs.get(job_id)
            if not job or job["session_id"] != sid:
                raise FileNotFoundError("Replay job not found; upload the video again after a server restart")
            return self.public(job)

    def start(self, sid: str, job_id: str) -> dict:
        with self.lock:
            self.get(sid, job_id)
            job = self.jobs[job_id]
            if job["status"] in {"running", "paused"}:
                return self.public(job)
            if self.threads.get(job_id) and self.threads[job_id].is_alive():
                raise ValueError("Previous replay is finishing; try again in a moment")
            if sum(j["status"] in {"running", "paused"} for j in self.jobs.values()) >= 4:
                raise ValueError("At most four replay jobs can run concurrently")
            session = self.pipeline.store.read(sid)
            if not session["calibration"] or session["calibration"]["source_id"] != job["source_id"]:
                raise ValueError("Calibrate the uploaded video before starting replay")
            owner = f"replay:{job_id}:{uuid.uuid4()}"
            self.pipeline.acquire(sid, owner)
            job.update(status="running", error=None, run_id=str(uuid.uuid4()), position=0, progress=0, seek=None, owner=owner)
            self.pipeline.reset(sid)
            thread = threading.Thread(target=self._run, args=(job_id,), daemon=True, name=f"replay-{job_id[:8]}")
            self.threads[job_id] = thread
            thread.start()
            return self.public(job)

    def manual(self, sid: str, job_id: str, frame_id: str, force: bool) -> dict:
        with self.lock:
            self.get(sid, job_id)
            job = self.jobs[job_id]
            if job["status"] == "running":
                job["status"] = "paused"
            existing = job.get("manual_frame")
            if existing and existing[0] == frame_id:
                _, pixels, timestamp = existing
            else:
                timestamp = job["position"]
                reader = cv2.VideoCapture(str(job["path"]))
                try:
                    reader.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
                    ok, pixels = reader.read()
                    if not ok:
                        raise ValueError("Cannot decode this replay position")
                finally:
                    reader.release()
                job["manual_frame"] = (frame_id, pixels, timestamp)
            active = job["status"] in {"running", "paused"}
            owner = job["owner"] if active else f"manual:{uuid.uuid4()}"
        if not active:
            self.pipeline.acquire(sid, owner)
        try:
            result = self.pipeline.process(sid, pixels, timestamp, job["source_id"], frame_id, owner, kind="manual", force=force, replay=True)
            with self.lock:
                job["analysis"] = result
            return result
        finally:
            if not active:
                self.pipeline.release(sid, owner)

    def command(self, sid: str, job_id: str, action: str, seconds: float) -> dict:
        with self.lock:
            self.get(sid, job_id)
            job = self.jobs[job_id]
            if action == "cancel":
                job["status"] = "cancelled"
            elif action == "pause" and job["status"] == "running":
                job["status"] = "paused"
            elif action == "resume" and job["status"] == "paused":
                job["status"] = "running"
            elif action == "seek" and job["status"] in {"running", "paused"}:
                job["seek"] = min(seconds, max(0, job["duration"] - 1 / job["fps"]))
            else:
                raise ValueError("That replay control is not valid in the current state")
            return self.public(job)

    def _run(self, job_id: str) -> None:
        job = self.jobs[job_id]
        sid, owner = job["session_id"], job["owner"]
        reader = cv2.VideoCapture(str(job["path"]))
        last_sample = -1e12
        index = 0
        try:
            while True:
                with self.lock:
                    status, seek = job["status"], job["seek"]
                    if seek is not None:
                        job["seek"] = None
                if status == "cancelled":
                    break
                if seek is not None:
                    reader.set(cv2.CAP_PROP_POS_MSEC, seek * 1000)
                    index = round(seek * job["fps"])
                    last_sample = -1e12
                    job["run_id"] = str(uuid.uuid4())
                    self.pipeline.reset(sid)
                if status == "paused":
                    time.sleep(0.1)
                    continue
                ok, frame = reader.read()
                if not ok:
                    with self.lock:
                        job.update(status="completed", progress=1.0)
                    break
                raw_time = reader.get(cv2.CAP_PROP_POS_MSEC) / 1000
                fallback = index / job["fps"]
                source_time = raw_time if raw_time > 0 and abs(raw_time - fallback) < 2 else fallback
                index += 1
                settings = self.pipeline.store.read(sid)["settings"]
                if source_time - last_sample < 1 / settings["processing_fps"] - 1e-5:
                    continue
                last_sample = source_time
                result = self.pipeline.process(sid, frame, source_time, job["source_id"], f"{job['run_id']}:{index}", owner, replay=True)
                with self.lock:
                    job.update(position=source_time, progress=min(1, source_time / job["duration"]),
                               analysis=result, preview=preview_jpeg(frame, 960))
                time.sleep(0.02)
        except Exception as exc:
            with self.lock:
                job.update(status="error", error=f"{type(exc).__name__}: {exc}")
        finally:
            reader.release()
            self.pipeline.release(sid, owner)

    def close(self) -> None:
        with self.lock:
            for job in self.jobs.values():
                if job["status"] in {"running", "paused"}:
                    job["status"] = "cancelled"
        for thread in list(self.threads.values()):
            thread.join(timeout=2)
