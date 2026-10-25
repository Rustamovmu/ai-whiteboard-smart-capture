"""Optional post-capture OCR; one worker and a bounded queue, no runtime downloads."""
import importlib.util
import queue
import threading
from pathlib import Path

from .storage import Store


class OCRService:
    def __init__(self, store: Store, model_dir: Path):
        self.store, self.model_dir = store, model_dir / "ocr"
        self.jobs: queue.Queue = queue.Queue(maxsize=16)
        self.reader = None
        self.thread: threading.Thread | None = None

    def status(self) -> dict:
        return {"installed": importlib.util.find_spec("easyocr") is not None,
                "models_present": self.model_dir.is_dir() and any(self.model_dir.glob("*.pth")),
                "pending": self.jobs.qsize()}

    def submit(self, session_id: str, capture_id: str) -> None:
        if not self.status()["installed"] or not self.status()["models_present"]:
            self.store.edit_capture(session_id, capture_id, {"ocr": {"status": "unavailable", "text": "", "segments": [],
                                                                  "error": "Install optional OCR and run its model setup command"}})
            return
        try:
            self.store.edit_capture(session_id, capture_id, {"ocr": {"status": "queued", "text": "", "segments": []}})
            self.jobs.put_nowait((session_id, capture_id))
        except queue.Full:
            self.store.edit_capture(session_id, capture_id, {"ocr": {"status": "skipped", "text": "", "segments": [], "error": "OCR queue is full"}})
            return
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._run, daemon=True, name="whiteboard-ocr")
            self.thread.start()

    def _run(self) -> None:
        while True:
            job = self.jobs.get()
            if job is None:
                self.jobs.task_done()
                return
            sid, cid = job
            try:
                if self.reader is None:
                    import easyocr
                    self.reader = easyocr.Reader(["en"], gpu=False, model_storage_directory=str(self.model_dir), download_enabled=False)
                path = self.store.capture_path(sid, cid)
                result = self.reader.readtext(str(path))
                segments = [{"text": text, "confidence": float(confidence)} for _, text, confidence in result]
                self.store.edit_capture(sid, cid, {"ocr": {"status": "complete", "text": "\n".join(s["text"] for s in segments), "segments": segments}})
            except FileNotFoundError:
                pass  # Capture was explicitly deleted while OCR was running.
            except Exception as exc:
                try:
                    self.store.edit_capture(sid, cid, {"ocr": {"status": "error", "text": "", "segments": [], "error": str(exc)}})
                except FileNotFoundError:
                    pass
            finally:
                self.jobs.task_done()

    def close(self) -> None:
        if self.thread and self.thread.is_alive():
            # Drain already queued work on shutdown; never hold up server termination.
            try:
                self.jobs.put_nowait(None)
            except queue.Full:
                pass
