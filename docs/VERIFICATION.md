# Verification report

Verified on **2026-10-25**, on this native arm64 macOS environment using Python 3.11.9 and Node 24.19.0. The repository began with an empty `main.py`.

## Implemented application

- Working local FastAPI backend and React/TypeScript/Vite/Tailwind dashboard, plus a production build served from the backend origin.
- Native webcam lifecycle, compressed/acknowledged WebSocket frames, bounded transport, reconnect/reset handling, editable normalized calibration, OpenCV contour proposals and perspective correction.
- Quality checks, illumination normalization, motion/stability analysis, SSIM plus pixel/edge/ink change signals, duplicate prevention, cooldown, cleared-board events and centralized decisions.
- Actual YOLO11n CPU person inference, polygon overlap gating and explicit degraded/unknown status when unavailable. No CUDA or external inference API.
- Persisted sessions, metadata, original/enhanced images, thumbnails, capture notes/names, zoom, search, explanations, statistics and configurable presets.
- Manual capture with warnings/override for both webcam and video. Validated replay upload, shared processing, pause/resume/seek/cancel and progress.
- Actual-image A4 PDF, ZIP image archive, JSON metadata and available OCR text exports.
- Optional bounded asynchronous EasyOCR integration and separate model setup. **Optional OCR dependencies/models were not installed or accuracy-tested here.**

## Executed checks

| Check | Result |
| --- | --- |
| Backend unit/integration suite | **35 passed**, including real JPEG WebSocket processing, storage, exports and timestamped replay |
| Python imports/compileall | Passed |
| `pip check` | No broken requirements |
| TypeScript strict checks, including unused symbols | Passed |
| React production build | Passed |
| Camera browser workflow | Passed: native synthetic camera → calibration → automatic capture → no duplicate → manual capture → editing/enhancement/zoom → PDF download → settings → reload/search/theme |
| Camera ended-event handling | Passed with an explicitly simulated track-ended event; physical device unplug remains unverified |
| Replay browser workflow | Passed: actual AVI upload → contour proposal/confirmation → same pipeline → three meaningful captures → tablet layout → manual capture |
| Production-origin/mobile browser workflow | Passed: compiled React app served directly by FastAPI, healthy API, mobile menu, saved notes and no horizontal overflow at 390 px |
| PDF visual inspection | Parsed and rendered a real three-page browser-exported PDF with native macOS PDFKit (Poppler unavailable), then inspected cover, image pages, note, margins and page numbers |

Backend tests produce a Starlette deprecation warning about its current HTTPX test-client adapter. It does not fail the suite. Browser tests use installed Google Chrome with an explicitly generated Y4M camera source, not physical classroom footage. They do not mock production API results.

## Actual model evidence

The official cached `yolo11n.pt` loaded and ran on CPU. SHA256:

```text
0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1
```

A separate smoke check on the public Ultralytics `bus.jpg` example returned **four person boxes**, with actual confidences approximately 0.888, 0.879, 0.856 and 0.623. One measured cold/load-inclusive call took 1,036 ms. This confirms genuine inference on a real photograph; it is not a classroom accuracy benchmark. Person-box overlap and fresh-candidate blocking were separately tested with explicit, deterministic detector contract test doubles.

## Measured synthetic evaluation

Command:

```bash
.venv/bin/python scripts/evaluate.py data/demo/synthetic-lecture.avi data/demo/ground-truth.json
```

One run on the generated 38-second lecture analyzed **190 sampled frames** in **35.940 wall seconds**, or **5.29 processing FPS including decoding, inference and storage**. Browser testing was also running on the machine; this is a measured run, not a hardware-wide guarantee. Source sampling was 5 FPS. The metric does not include browser transport.

| Metric | Full pipeline | Frame-difference-only baseline |
| --- | ---: | ---: |
| True accepted changes | 3 | 3 |
| Missed labeled changes | 0 | 0 |
| False captures | 0 | 30 |
| Duplicate false captures inside matched windows | 0 | 1 |
| Precision on this synthetic fixture | 1.000 | 0.091 |
| Recall on this synthetic fixture | 1.000 | 1.000 |
| Mean delay from allowed capture-window start | 2.2 s | 0.0 s |

Full-pipeline captures occurred at video times **7.2, 16.2 and 30.2 seconds**. The cleared-board event was recorded separately. Nine sampled frames were rejected for blur, 34 delayed for motion, and 69 duplicate-equivalent accepted-board observations ignored. The evaluator also distinguishes insignificant/initial-empty observations from duplicates.

The baseline saves during incomplete writing, transient obstruction, exposure/blur changes and clearing. Its false captures are not all duplicates. The synthetic rectangular obstruction is **not evidence of human-detector accuracy**, and these precision/recall values must not be generalized to real classrooms.

## Acceptance scenarios

| Scenario | Evidence and honest status |
| --- | --- |
| A — New writing | Verified on generated video and native synthetic browser-camera input; physical classroom trial still required. |
| B — Duplicate frame | Verified by metrics/state-machine tests, repeated WebSocket frames and browser no-extra-capture assertion. |
| C — Walking/stationary person in front | Candidate gating, polygon union and stationary obstruction suppression verified with controlled detector outputs; real person model execution verified separately. **A real person blocking a physical whiteboard was not tested.** |
| D — Continued writing | Verified by generated writing sequences, timestamp stability/cooldown tests and absence of intermediate evaluation captures. |
| E — Blurry image | Verified by deterministic blur tests and generated video rejection counts. |
| F — Erased content | Verified by partial erasure capture and fully cleared-board event in generated replay. |
| G — Manual capture | Verified through webcam browser workflow, replay browser workflow and warning/override/idempotence integration tests. |
| H — Export | Valid real-image PDF/ZIP/JSON tested; browser PDF download and three-page visual review completed. |
| I — Video replay | Actual generated AVI decoded through the shared pipeline in backend and browser integration tests. |
| J — Restart | Fresh backend application instance reopened the same persistent session/images; browser reload restored saved notes. |

No real-world precision/recall, physical autofocus, camera permission-denial trial or hardware disconnection trial is claimed. Follow TESTING.md and DEMO_GUIDE.md on the presentation machine before a live demonstration.
