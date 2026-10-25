"""Explicit, one-time model download. Runtime inference never calls this script."""
import argparse
import hashlib
import json
import os
import ssl
import sys
import urllib.request
from pathlib import Path

import certifi

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def setup_person(destination: Path):
    url = "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt"
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / "yolo11n.pt"
    if not target.exists():
        print("Downloading official YOLO11n weights…", flush=True)
        temporary = target.with_suffix(".download")
        try:
            context = ssl.create_default_context(cafile=certifi.where())
            with urllib.request.urlopen(url, timeout=60, context=context) as response, temporary.open("wb") as stream:
                while chunk := response.read(1024 * 1024):
                    stream.write(chunk)
            if temporary.stat().st_size < 1_000_000:
                raise RuntimeError("Model download is unexpectedly small")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    checksum = hashlib.sha256(target.read_bytes()).hexdigest()
    (destination / "person-model.json").write_text(json.dumps({
        "model": "YOLO11n", "source": url, "sha256": checksum,
        "license": "Ultralytics AGPL-3.0 / commercial licensing; see https://www.ultralytics.com/license",
    }, indent=2))
    from backend.app.vision.person_detection import PersonDetector
    import numpy as np
    result = PersonDetector(destination, ROOT / "data" / "runtime").detect(np.full((360, 640, 3), 235, np.uint8), 0.35)
    if not result["available"]:
        raise RuntimeError(result.get("error") or "Model could not run")
    print(f"YOLO11n ready on CPU. Smoke inference: {result['inference_ms']} ms. SHA256: {checksum}")


def setup_ocr(destination: Path):
    os.environ.setdefault("TORCH_HOME", str(destination / "torch"))
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    import easyocr
    easyocr.Reader(["en"], gpu=False, model_storage_directory=str(destination / "ocr"), download_enabled=True)
    print("English EasyOCR models cached. Runtime downloads remain disabled.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ocr", action="store_true", help="Download optional English OCR models instead")
    parser.add_argument("--model-dir", type=Path, default=ROOT / "models")
    args = parser.parse_args()
    setup_ocr(args.model_dir) if args.ocr else setup_person(args.model_dir)
