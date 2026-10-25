# Development rules

- Read README.md and docs/ARCHITECTURE.md before architectural changes. Preserve working features and the separation between vision, orchestration, storage, API and UI.
- OpenCV remains the primary image-processing technology. Person detection must remain genuinely integrated with capture gating. Never fake detections, confidence, metrics, captures, OCR or test results.
- Keep local and offline operation after explicit dependency/model setup. No camera or lecture uploads to external services. Do not add runtime model downloads or telemetry.
- Use reusable, typed Python modules and maintain matching TypeScript/Pydantic contracts. Keep frontend/backend behavior compatible.
- Use one camera loop, one analysis owner per session, one frame in flight, bounded queues, and serialized model inference. Use source timestamps for replay and monotonic time for webcam stability.
- A capture candidate needs fresh person inference when the detector is available. A still person can obstruct a board. Missing AI means unknown obstruction, not definitely clear.
- Compare with the last accepted state. Commit comparison baselines only after successful persistence. Preserve idempotence and previous lecture notes.
- Keep normalized calibration coordinates in unmirrored source-image space. Rectification must preserve sharpness and reject invalid quadrilaterals.
- Keep originals immutable and enhancements separate. Validate identifiers/files/dimensions and prevent arbitrary filesystem access.
- Avoid unnecessary dependencies and abstraction layers. The MVP uses one backend worker and atomic JSON metadata; do not introduce cloud infrastructure or external databases.
- After meaningful changes, update documentation and run appropriate tests: `.venv/bin/python -m pytest -q`, `npm --prefix frontend run build`, and relevant browser workflows.
- Browser tests use Chromium's explicitly synthetic camera driver. Synthetic obstruction tests do not establish real-world person detection accuracy. Report incomplete verification and environment limitations honestly.
