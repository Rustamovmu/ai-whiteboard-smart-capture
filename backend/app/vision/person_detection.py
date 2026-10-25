"""CPU-only YOLO11n adapter. Runtime never downloads weights or fabricates boxes."""
import os
import threading
import time
from pathlib import Path

from ..schemas import utcnow


class PersonDetector:
    def __init__(self, model_dir: Path, config_dir: Path):
        self.path = model_dir / "yolo11n.pt"
        self.config_dir = config_dir
        self._model = None
        self._lock = threading.Lock()
        self.error: str | None = None

    def status(self) -> dict:
        return {"model": "YOLO11n / COCO person", "device": "cpu", "available": self._model is not None,
                "installed": self.path.is_file(), "error": self.error,
                "status": "active" if self._model is not None else "error" if self.error else
                "ready_to_load" if self.path.is_file() else "unavailable"}

    def detect(self, frame, confidence: float) -> dict:
        with self._lock:
            if not self.path.is_file():
                return {**self.status(), "boxes": [], "detected_at": None, "inference_ms": None}
            try:
                if self._model is None:
                    os.environ.setdefault("YOLO_CONFIG_DIR", str(self.config_dir))
                    os.environ["YOLO_OFFLINE"] = "true"
                    os.environ["YOLO_AUTOINSTALL"] = "false"
                    self.config_dir.mkdir(parents=True, exist_ok=True)
                    from ultralytics import YOLO, settings
                    settings.update({key: False for key in ("sync", "clearml", "comet", "dvc", "mlflow", "raytune", "wandb")})
                    import torch
                    torch.set_num_threads(2)
                    self._model = YOLO(str(self.path), task="detect")
                started = time.perf_counter()
                result = self._model.predict(frame, device="cpu", imgsz=640, conf=confidence,
                                             classes=[0], verbose=False)[0]
                height, width = frame.shape[:2]
                boxes = []
                for item in result.boxes:
                    x1, y1, x2, y2 = item.xyxy[0].tolist()
                    boxes.append({"box": [max(0, x1 / width), max(0, y1 / height),
                                           min(1, x2 / width), min(1, y2 / height)],
                                  "confidence": float(item.conf[0])})
                self.error = None
                return {**self.status(), "boxes": boxes, "detected_at": utcnow(),
                        "inference_ms": round((time.perf_counter() - started) * 1000, 2)}
            except Exception as exc:
                self.error = f"Person detector unavailable: {type(exc).__name__}: {exc}"
                self._model = None
                return {**self.status(), "boxes": [], "detected_at": None, "inference_ms": None}
