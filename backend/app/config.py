"""Local-only application configuration."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("WHITEBOARD_DATA_DIR", ROOT / "data")).resolve()
MODEL_DIR = Path(os.environ.get("WHITEBOARD_MODEL_DIR", ROOT / "models")).resolve()
ORIGINS = {"http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"}
MAX_FRAME_BYTES = 2 * 1024 * 1024
MAX_VIDEO_BYTES = 500 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
