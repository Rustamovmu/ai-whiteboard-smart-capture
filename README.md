# AI Whiteboard Smart Capture

**Boardly** is a local-first whiteboard capture application for classroom lectures. OpenCV rectifies the board and measures quality, motion and content changes. A real CPU YOLO11n detector suppresses captures when people overlap the board. A React dashboard manages live camera analysis, prerecorded videos, lecture sessions, original/enhanced images and note exports.

No account, external database, paid AI API or cloud service is required. After dependency installation and explicit model setup, the application works offline. Camera images and uploaded lecture videos stay on your machine.

## Quick start on macOS

Requires Python 3.11, a compatible Node.js installation (Node 24 was verified), and a current browser. Apple Silicon is supported without CUDA.

From the project directory:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-lock.txt
python scripts/setup_models.py
npm --prefix frontend ci
```

Start the backend in one terminal:

```bash
source .venv/bin/activate
python main.py
```

Start the frontend in another terminal:

```bash
npm --prefix frontend run dev
```

Open **http://127.0.0.1:5173**. The backend runs at **http://127.0.0.1:8000**, with interactive API documentation at `/docs`. Use one backend worker. Both servers bind to localhost.

For a single local server after building:

```bash
npm --prefix frontend run build
.venv/bin/python main.py
```

Then open **http://127.0.0.1:8000**. Restart the backend after creating or updating the production build. It serves compiled frontend files only if the build exists when it starts.

`requirements-lock.txt` records the verified Python 3.11/Apple Silicon environment. For another supported platform, use `backend/requirements.txt` to resolve compatible wheels, then run tests. `frontend/package-lock.json` locks frontend dependencies.

## First capture

1. Choose **New session**, enter the lecture title and optional course/context.
2. Click **Start camera** and grant camera permission. The preview is unmirrored. Select another camera from the menu if needed.
3. Click **Calibrate board**. OpenCV proposes a boundary if it finds a suitable rectangle; otherwise drag the four corners manually. Select the writable interior, excluding the board's metal frame. Confirm the board.
4. Write, move away and let the board settle. Balanced mode waits for two seconds of low motion before accepting a clear, meaningful change. The first stable, nonempty board becomes the first capture.
5. An unchanged board does not produce additional automatic captures. Manual captures remain available; poor quality, detected obstruction or unknown AI protection prompts explicit confirmation.
6. Review the gallery. Open a capture to zoom, choose original/enhanced, rename, add notes, inspect actual measurements or delete it.
7. Use **Export notes** for PDF, ZIP images, JSON metadata or available OCR text.

**Pause** suspends analysis while keeping the camera preview visible. **Stop** releases the camera tracks and closes its WebSocket. Changing sessions or sources stops the current source. Keep the physical camera fixed after calibration. Same-aspect-ratio resolution changes preserve normalized corners; another source or changed aspect ratio requires calibration again.

## AI setup and offline operation

```bash
.venv/bin/python scripts/setup_models.py
```

This explicitly downloads **YOLO11n COCO detection weights** from the official Ultralytics assets release, caches `models/yolo11n.pt`, records its URL and SHA256, and runs a real CPU inference smoke check. The runtime uses existing local files, disables Ultralytics synchronization/integrations and automatic dependency installation, and does not download missing weights. The model is loaded once per backend process.

If weights or dependencies are missing, analysis reports **AI detection unavailable** and **unknown obstruction**. Motion-only automatic capture still works, but cannot reliably reject a person who remains still. Never interpret this fallback as guaranteed clear visibility.

- Model documentation: https://docs.ultralytics.com/models/yolo11/
- Exact weights source: https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt
- License: https://www.ultralytics.com/license (AGPL-3.0/commercial terms apply to Ultralytics code and weights; review these before redistribution).

To verify the detector on your own local image:

```bash
.venv/bin/python scripts/verify_model.py /absolute/path/to/image.jpg
```

Only calculated boxes and confidence values are returned. This command does not download or upload the image.

## Optional offline OCR

```bash
.venv/bin/python -m pip install -r backend/requirements-ocr.txt
.venv/bin/python scripts/setup_models.py --ocr
```

Restart the backend and enable OCR in the session's Settings. English EasyOCR runs after a capture has been saved, on a single background worker with a 16-job queue. The runtime disables OCR model downloads. Missing dependencies/models are explicit and do not stop capture. Recognized words, user notes and capture titles are searchable in Saved notes. Confidence is displayed per recognized segment. Mathematics, diagrams and handwriting remain unreliable; the original image is authoritative. OCR on this environment is optional and was not used to establish the capture evaluation results.

## Prerecorded demonstration

```bash
.venv/bin/python scripts/generate_demo_data.py
```

Creates `data/demo/synthetic-lecture.avi`, deterministic images, labeled ground truth and a synthetic browser-camera fixture. In a new session choose **Video replay**, upload the AVI, calibrate, then start replay. MP4, MOV and AVI are accepted up to 500 MB when the installed OpenCV build can decode their codec. Uploads are validated by decoding, not just by filename.

Replay uses the same pipeline as the webcam, sampled using video time. Pause/resume, stop, seeking and manual capture are supported. Manual capture pauses a running replay. Seeking resets temporal stability and starts a new run identifier; previously saved notes stay available. Replay jobs are not resumed after a server restart; saved captures and sessions are persistent. A session supports only one active analysis source.

The synthetic moving rectangle is explicitly **not a human-detector accuracy test**.

## Tests and evaluation

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
npm --prefix frontend run build
.venv/bin/python scripts/generate_demo_data.py
npm --prefix frontend test
```

Browser tests require installed Google Chrome and use its synthetic camera driver; no physical webcam permission is requested. They start/reuse localhost servers. Tests create real sessions labeled `Browser verification`/`Replay verification`; they are test data in your local data directory. Screenshots and failure traces are written to `frontend/test-results/`. Build the frontend before running the production-origin browser test.

Compare the real pipeline with a frame-difference-only baseline:

```bash
.venv/bin/python scripts/evaluate.py data/demo/synthetic-lecture.avi data/demo/ground-truth.json
```

Results are written to `data/evaluation.json`. Supply your own video and manually labeled windows in the same format for real evaluations. Do not generalize synthetic precision/recall to classroom performance. See [testing](docs/TESTING.md) and [verification results](docs/VERIFICATION.md).

## Storage and privacy

```text
data/sessions/<uuid>/
  metadata.json         # session, settings, calibration, captures, statistics, events
  baseline.png          # internal comparison reference, including board-cleared states
  captures/             # separate original, enhanced and thumbnail JPEGs
  videos/               # explicitly uploaded lecture files
  exports/              # generated PDF, ZIP, JSON, text
models/                 # explicit downloads; ignored by version control
```

Metadata replacement is atomic and guarded by per-session locks. Originals are never overwritten by enhancement. Capture requests are idempotent, including after deleting a capture. Session statistics are checkpointed about every five seconds, after captures and on disconnection; a sudden process crash can lose the last few counters. UUID-based, metadata-checked routes serve images; there is no general static data-directory endpoint. Exports contain actual saved images and notes. A durable baseline remains after a capture is deleted to prevent immediate recapture of the same board.

`WHITEBOARD_DATA_DIR` and `WHITEBOARD_MODEL_DIR` can override the data/model roots before backend startup. Data/model files are excluded from version control. Back up `data/sessions` to preserve notes.

## Troubleshooting

- **Backend offline:** run `.venv/bin/python main.py`, check port 8000, and refresh. A Vite port other than 5173 requires updating the local-origin allowlist and proxy configuration.
- **Camera denied:** allow the site in your browser and the browser under macOS **System Settings → Privacy & Security → Camera**. A camera may also be in use by another app. Use Video replay when hardware is unavailable.
- **No capture:** confirm the correct source is calibrated, automatic capture is enabled, and the board is sharp/still. Examine the decision journal. Lower sharpness/change thresholds or use High sensitivity for small writing; validate against your camera's actual results.
- **Empty board called blurry:** exclude borders during calibration. Sparse surfaces make focus ambiguous; the application reports this rather than proving focus quality.
- **Wrong automatic boundary:** drag the corners. Auto detection is a geometric suggestion, not semantic whiteboard recognition.
- **Video rejected:** an extension does not guarantee codec support. Re-encode locally to H.264 MP4 or MJPEG AVI using an available encoder. The application does not require FFmpeg as a separate installation.
- **Missing model:** run the explicit setup command and retry analysis. A damaged weight file should be replaced using that command after removing only the damaged cached file.
- **Python TLS errors:** the setup script uses certifi's trusted certificate bundle; keep certificates installed. Do not disable TLS verification.
- **Performance:** reduce processing FPS and increase detector interval. Fresh inference still runs for every candidate. CPU inference is serialized and preview rendering stays in the browser.
- **Multi-user/network deployment:** unsupported by this local university MVP. Do not expose the server publicly without designing authentication, permissions and multi-worker coordination.

Read [architecture](docs/ARCHITECTURE.md), [algorithms and thresholds](docs/ALGORITHMS.md), [demo guide](docs/DEMO_GUIDE.md), and [limitations](docs/LIMITATIONS.md) for presentation and engineering detail.
