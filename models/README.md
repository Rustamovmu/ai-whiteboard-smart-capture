# Local model cache

Run `.venv/bin/python scripts/setup_models.py` from the project root. It downloads the official YOLO11n asset, records its provenance/SHA256 and verifies CPU inference. Runtime processing only loads existing files.

Optional OCR requires `backend/requirements-ocr.txt` and `scripts/setup_models.py --ocr`. Neither model cache is committed to source control. See the root README for upstream sources and Ultralytics licensing.
