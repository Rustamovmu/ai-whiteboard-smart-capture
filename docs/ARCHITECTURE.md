# Architecture

## Data flow

```text
Browser getUserMedia → compressed JPEG, one frame in flight → WebSocket
                                                              │
Uploaded video → OpenCV timestamped replay ─────────────────────┤
                                                              ▼
                     Pipeline + per-session owner/lock
                       │ calibration / perspective correction
                       │ quality + normalized content metrics
                       │ CPU YOLO11n + polygon obstruction union
                       │ temporal decision engine
                       ▼
           Atomic capture storage + durable comparison baseline
                       ├─ optional bounded post-capture OCR
                       ├─ gallery + explainable analysis results
                       └─ PDF / ZIP / JSON / text export
```

OpenCV performs image operations. YOLO11n is the pretrained AI component. OCR is a separate optional learned model. There is no trained handwriting-understanding or semantic change model.

## Responsibilities

- `vision`: calibration validation, automatic contour proposals, perspective transformation, quality/change/motion metrics, person inference and the central decision state machine.
- `services`: atomic filesystem repository, shared pipeline orchestration, asynchronous OCR, replay lifecycle and document/archive export.
- FastAPI: validation, localhost origin checks, controlled resource routes, upload limits, WebSocket lifecycle and optional production frontend hosting.
- React: native camera lifecycle, one in-flight compressed frame, source-coordinate overlays, session/gallery management, actual metric display, settings, manual confirmation and download interaction.

The root launcher configures a 3 MB WebSocket message limit and one queued inbound message. Application-level validation allows 2 MB JPEG bytes and 16 million decoded pixels. Frame dimensions must match JPEG headers before OpenCV decoding. Video uploads are capped at 500 MB and require valid dimensions, frame rate, frame count and a decodable first frame.

## Concurrency and persistence

The backend supports **one process/worker**. A session has a single analysis owner: a webcam WebSocket or replay job. Per-session reentrant locks protect metadata and pipeline state. A detector lock serializes all YOLO inference; weights are loaded once. CPU-bound analysis runs off the asynchronous HTTP/WebSocket event loop.

The browser requests one frame at a time and drops automatic sampling opportunities while busy. One pending explicit manual/calibration command is retained so clicking during inference does not silently lose the command. Reconnects have bounded exponential backoff, retrieve persistent state and reset temporal history. Accepted request IDs are retained independently of gallery deletion.

Replay is limited to four concurrent jobs and twenty retained jobs. Completed old uploads are removed when the retained-job limit is reached. Each job keeps one current preview/analysis and one optional manual review frame. Pause/cancel are cooperative; a currently running inference finishes before the worker observes the control. Seeking starts a new run ID and resets temporal stability while preserving previous captures.

Capture image writes complete before metadata commits. Failed writes remove newly written image files. Metadata uses a unique temporary file, flush/fsync and atomic replacement. Comparison baselines update only after an accepted capture or board-cleared event is persisted. The internal baseline is independent of gallery deletion and includes its calibration revision. Baselines are PNGs to avoid repeated JPEG degradation.

Statistics checkpoint roughly every five seconds, after captures, on session reads, and on source disconnection/shutdown. OCR has one background worker and a sixteen-item queue; queue saturation is explicit. Session events retain the latest 1,000 entries. The MVP is not a transactional multi-process database; abrupt crashes can leave harmless orphan images or lose recent counters. See limitations.

## Public interfaces

All API paths below are rooted at `/api`:

| Route | Purpose |
| --- | --- |
| `GET /health`, `GET /models` | Actual service/model availability |
| `GET /presets` | Documented settings presets |
| `GET/POST /sessions` | List/create lectures |
| `GET/PATCH /sessions/{sid}` | Reopen/edit session metadata |
| `PUT/DELETE /sessions/{sid}/calibration` | Confirm/reset normalized corners |
| `PATCH /sessions/{sid}/settings` | Validated, immediately effective pipeline settings |
| `POST /sessions/{sid}/presets/{name}` | Apply sensitivity values without replacing feature toggles |
| `PATCH/DELETE /sessions/{sid}/captures/{cid}` | Rename, annotate, delete |
| `GET /sessions/{sid}/captures/{cid}/image` | Original/enhanced/thumbnail, optional attachment download |
| `GET /sessions/{sid}/export/{pdf,zip,json,txt}` | Export real session data |
| `POST /sessions/{sid}/replays` | Stream an uploaded video into local storage |
| `GET /sessions/{sid}/replays/{job}` | Progress, preview, most recent analysis |
| `POST .../replays/{job}/suggestion` | Propose corners from first video frame |
| `POST .../replays/{job}/start` | Begin a calibrated replay |
| `POST .../replays/{job}/control` | Pause, resume, cancel, seek |
| `POST .../replays/{job}/manual` | Capture/review a video frame with request idempotence |

Exact schemas are also available through FastAPI `/docs` and `/openapi.json`.

The WebSocket path is `/ws/sessions/{sid}`. A frame request contains:

```typescript
{
  type: 'frame' | 'manual' | 'suggest';
  frame_id: string;        // unique per logical request, reused when confirming a manual warning
  source_id: string;       // camera identity or uploaded video identity
  width: number;
  height: number;
  jpeg: string;            // base64 JPEG bytes, without a data: prefix
  force?: boolean;        // explicit manual warning override only
}
```

The server first sends `connected`. Results have `type: analysis`, the matching `frame_id`, state, reason, decision, calibration, actual detector status, optional quality/change/motion/stability/overlap values, a rectified preview, statistics and a capture only when newly saved. Uncalibrated results omit measurements that were not calculated. Errors have `type: error` and an actionable message. `{type: 'reset'}` resets temporal analysis without altering persistent notes or the comparison baseline.

All overlay coordinates use the **unmirrored raw source** normalized to `[0,1]`. Calibration also records source identity, aspect ratio and a generated revision. Comparisons use rectified board coordinates; person boxes remain in source space. Wall timestamps are UTC ISO strings; webcam stability uses server monotonic time and replay uses video source time. In degraded mode, obstruction fraction is `null` and status is `unknown`.

## Local security boundary

Both servers default to localhost. HTTP rejects unexpected Origin and cross-site fetch contexts; WebSocket handshakes require an allowed local origin. Identifiers must be canonical UUIDs and image routes require a capture record. Uploaded names never become storage filenames. The application serves no unrestricted data/model directories, logs no raw camera images, and uses no mandatory external services. Trusted local processes can access this unauthenticated MVP; public hosting is outside its design.
