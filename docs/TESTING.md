# Testing and evaluation

## Automated checks

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q backend scripts main.py
.venv/bin/python -m pip check
npm --prefix frontend run build
.venv/bin/python scripts/generate_demo_data.py
npm --prefix frontend test
```

Backend tests cover sharpness, empty-board focus uncertainty, dark/clipped exposure, normalized calibration, perspective correction, invalid quadrilaterals, contour proposals, polygon/box union, additions/erasures/clearing, duplicate/noise/brightness/JPEG suppression, motion/stability/cooldown/clock gaps, invalid images/dimensions, atomic persistence and reopening, safe download paths, origin restrictions, settings/presets, WebSocket save/gallery/export/disconnect, manual override/idempotence, absent AI/OCR, shared timestamped replay and fresh candidate inference gating.

Detector contract tests use clearly labeled test doubles to control box outputs. Production uses `PersonDetector`, never these test doubles. Deterministic timing tests inject a test clock rather than waiting for wall time. A separate real-model smoke check should run with actual local weights and a real image:

```bash
.venv/bin/python scripts/verify_model.py /path/to/local/person-image.jpg
```

Browser tests use installed Google Chrome with its native fake-camera command-line driver and a generated Y4M input. This tests real `getUserMedia`, frame encoding, WebSocket analysis, automatic/manual saving, camera stop, edit/zoom/enhancement, download, settings, reload persistence, search, theme, replay and tablet overflow. It does not establish hardware permissions, autofocus or physical camera disconnection behavior. Tests create real persisted verification sessions and screenshots in `frontend/test-results`. No production responses are mocked.

## Synthetic evaluation

```bash
.venv/bin/python scripts/evaluate.py data/demo/synthetic-lecture.avi data/demo/ground-truth.json
```

The generator fixes content, timing and labels. Evaluation samples five frames per source second and invokes the same pipeline as live/replay processing. Ground truth defines three acceptable capture windows after completed writing/erasure, with clearing treated as a separate event. One capture per matching window is a true acceptance; additional captures in that window are duplicate false positives; unmatched captures are false positives; unmatched windows are misses. Capture delay is relative to each window's start. Zero-denominator precision/recall is null, not fabricated.

The baseline compares grayscale pixels with its last accepted frame, uses an intensity difference above 20 and a changed fraction at least 0.0025, and has no quality, stability, illumination or person gate. Its thresholds and definitions are recorded in source. Report both false captures and duplicates; do not call all baseline false captures duplicates.

The synthetic rectangle is not a person, and model performance on it is not a meaningful human-detection test. A synthetic perfect precision/recall result is only evidence about these fixtures and timing labels.

## Real-world protocol

1. Fix a webcam and manually calibrate the writable interior. Record camera model, native resolution, room lighting, marker colors, settings, machine and model version.
2. Obtain appropriate permission before recording people. Keep recordings local. Record at least three runs of the same scripted lecture sequence under normal lighting, stronger shadows and glare.
3. Include at least ten labeled content changes: isolated symbols, longer equations, colored diagrams, partial erasure and full clearing. Include no-change intervals, continuous writing, small hand movements, people passing and a person standing still in front of the board.
4. A human annotator records each finished meaningful change and the first sufficiently clear/unobstructed instant. Define an acceptable capture window ending before the next obstruction/change. Mark privacy/occlusion and poor-quality intervals separately.
5. Use the label format below with `scripts/evaluate.py`. Review accepted images as well as timestamps; adjust labels only to correct annotation mistakes, not to favor the algorithm.
6. Compare the full pipeline and the simple baseline with the same input, calibrated region, sampling rate and labels. Record misses, false captures, duplicates, mean delay and measured processing FPS. Evaluate missed/false person detections separately with labeled boxes or obstruction intervals.
7. Repeat on the actual live camera to measure browser transport and permission behavior. The evaluator's FPS includes decoding/inference/storage, but not browser capture/transport or a target source-rate cap.

```json
{
  "synthetic": false,
  "calibration": [
    {"x": 0.1, "y": 0.1}, {"x": 0.9, "y": 0.1},
    {"x": 0.9, "y": 0.9}, {"x": 0.1, "y": 0.9}
  ],
  "expected_change_windows": [[10.0, 18.0], [25.0, 32.0]]
}
```

Coordinates/windows above illustrate the file format; replace them with measurements from the actual video. The evaluator explicitly reports that real-person detection accuracy was not evaluated, because content-event windows alone do not provide person-box ground truth.

## Acceptance evidence

Maintain docs/VERIFICATION.md with executed checks, actual counts/results and unverified environment-dependent cases. Never mark a live classroom scenario passed merely because a synthetic or mocked counterpart passed. Backend restart tests use a newly created application instance over the same persistent directory; browser reload tests separately verify client restoration.
