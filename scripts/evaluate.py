"""Compare the actual pipeline against frame-difference-only capture on labeled video.

Labels: {"calibration": [{"x":...,"y":...}, ...], "expected_change_windows": [[start,end], ...]}.
Windows represent acceptable capture times after each meaningful change. A second capture
inside an already matched window is a duplicate false positive. Unmatched captures are false
positives; unmatched windows are misses. Labels must be supplied by a human for real videos.
"""
import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.schemas import SessionCreate
from backend.app.services.ocr import OCRService
from backend.app.services.pipeline import Pipeline
from backend.app.services.storage import Store
from backend.app.vision.geometry import rectify
from backend.app.vision.person_detection import PersonDetector


def score(predictions: list[float], windows: list[list[float]]) -> dict:
    matched, delays, duplicates = set(), [], 0
    for timestamp in predictions:
        candidates = [i for i, (start, end) in enumerate(windows) if start <= timestamp <= end]
        available = [i for i in candidates if i not in matched]
        if available:
            index = available[0]
            matched.add(index)
            delays.append(timestamp - windows[index][0])
        elif candidates:
            duplicates += 1
    tp, fp, fn = len(matched), len(predictions) - len(matched), len(windows) - len(matched)
    return {"true_accepted_changes": tp, "false_captures": fp, "missed_changes": fn,
            "duplicate_captures": duplicates, "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "mean_capture_delay_seconds": sum(delays) / len(delays) if delays else None,
            "capture_times": predictions}


def evaluate(video: Path, labels_path: Path, output: Path, disable_ai: bool = False) -> dict:
    labels = json.loads(labels_path.read_text())
    reader = cv2.VideoCapture(str(video))
    if not reader.isOpened():
        raise ValueError("Cannot decode evaluation video")
    fps = reader.get(cv2.CAP_PROP_FPS)
    if not 0 < fps <= 240:
        raise ValueError("Invalid video frame rate")
    count, baseline, simple_captures, accepted = 0, None, [], []
    last_sample = -1e9
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="whiteboard-evaluation-") as folder:
        root = Path(folder)
        store = Store(root)
        session = store.create(SessionCreate(title="Evaluation"))
        sid = session["id"]
        detector = PersonDetector(ROOT / "models", ROOT / "data" / "runtime")
        pipeline = Pipeline(store, detector, OCRService(store, ROOT / "models"))
        owner = "evaluation"
        pipeline.acquire(sid, owner)
        index = 0
        try:
            while True:
                ok, frame = reader.read()
                if not ok:
                    break
                timestamp = index / fps
                index += 1
                if timestamp - last_sample < .2 - 1e-5:
                    continue
                last_sample = timestamp
                if count == 0:
                    store.patch(sid, {"calibration": {"points": labels["calibration"], "source_id": "evaluation",
                                                       "revision": "evaluation", "aspect_ratio": frame.shape[1] / frame.shape[0]},
                                      "settings": {**session["settings"], "ai_enabled": not disable_ai}})
                board = rectify(frame, labels["calibration"])
                values = cv2.cvtColor(board, cv2.COLOR_BGR2GRAY)
                if baseline is None:
                    baseline = values
                elif np.mean(cv2.absdiff(values, baseline) > 20) >= 0.0025:
                    simple_captures.append(round(timestamp, 3))
                    baseline = values
                result = pipeline.process(sid, frame, timestamp, "evaluation", str(index), owner, replay=True)
                if result["capture"]:
                    accepted.append(round(timestamp, 3))
                count += 1
        finally:
            reader.release()
            pipeline.release(sid, owner)
        elapsed = time.perf_counter() - started
        result = {"synthetic": labels.get("synthetic", False), "real_person_accuracy_evaluated": False,
                  "video": video.name, "analyzed_frames": count, "wall_seconds": round(elapsed, 3),
                  "processing_fps_including_io": round(count / elapsed, 2), "detector": detector.status(),
                  "ai_enabled": not disable_ai,
                  "full_pipeline": score(accepted, labels["expected_change_windows"]),
                  "frame_difference_baseline": score(simple_captures, labels["expected_change_windows"]),
                  "stats": store.read(sid)["stats"]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("labels", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "evaluation.json")
    parser.add_argument("--disable-ai", action="store_true", help="Evaluate explicitly degraded motion-only mode")
    args = parser.parse_args()
    print(json.dumps(evaluate(args.video, args.labels, args.output, args.disable_ai), indent=2))
