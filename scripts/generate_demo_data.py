"""Generate a 38-second synthetic lecture and explicit ground-truth stage labels."""
import argparse
import json
from pathlib import Path

import cv2

from demo_assets import CALIBRATION, board, frame_at


def generate(destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / "synthetic-lecture.avi"
    fps = 10
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (960, 540))
    if not writer.isOpened():
        raise RuntimeError("This OpenCV build cannot encode MJPEG AVI")
    labels = []
    try:
        for i in range(38 * fps):
            seconds = i / fps
            frame, label = frame_at(seconds)
            writer.write(frame)
            labels.append({"seconds": seconds, "stage": label})
    finally:
        writer.release()
    cv2.imwrite(str(destination / "empty.jpg"), board(0))
    cv2.imwrite(str(destination / "first-equation.jpg"), board(1))
    cv2.imwrite(str(destination / "second-equation.jpg"), board(2))
    # A native Chromium fake-camera fixture for reproducible browser integration tests.
    still, _ = frame_at(8)
    planar = cv2.cvtColor(still, cv2.COLOR_BGR2YUV_I420).tobytes()
    with (destination / "camera.y4m").open("wb") as stream:
        stream.write(b"YUV4MPEG2 W960 H540 F10:1 Ip A1:1 C420jpeg\n")
        for _ in range(40):
            stream.write(b"FRAME\n")
            stream.write(planar)
    (destination / "ground-truth.json").write_text(json.dumps({
        "synthetic": True, "person_detection_evidence": False, "calibration": CALIBRATION,
        "expected_change_windows": [[5, 11], [14, 19], [28, 33]],
        "cleared_window": [33, 38], "labels": labels,
    }, indent=2))
    print(f"Created {path}. This synthetic fixture does not demonstrate real-person detection accuracy.")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "demo")
    generate(parser.parse_args().output)
