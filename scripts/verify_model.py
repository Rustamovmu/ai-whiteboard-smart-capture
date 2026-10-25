"""Run the REAL person detector on a supplied image. Does not download any image."""
import argparse
import json
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.vision.person_detection import PersonDetector

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    image = cv2.imread(str(args.image))
    if image is None:
        raise SystemExit("Cannot decode the supplied image")
    result = PersonDetector(ROOT / "models", ROOT / "data" / "runtime").detect(image, 0.35)
    print(json.dumps(result, indent=2))
    if not result["available"]:
        raise SystemExit(1)
