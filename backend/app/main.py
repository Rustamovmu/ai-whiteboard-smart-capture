"""Local FastAPI application. Run one worker; session state is intentionally process-local."""
import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .config import DATA_DIR, MAX_VIDEO_BYTES, MODEL_DIR, ORIGINS, ROOT
from .schemas import Calibration, CapturePatch, FrameRequest, PRESETS, ReplayCommand, ReplayManual, SessionCreate, SessionPatch, Settings
from .services.exports import export_session
from .services.ocr import OCRService
from .services.pipeline import Pipeline
from .services.replay import ReplayManager
from .services.storage import Store
from .vision.geometry import suggest_board, validate_points
from .vision.person_detection import PersonDetector

logger = logging.getLogger("whiteboard")


def create_app(data_dir: Path = DATA_DIR, model_dir: Path = MODEL_DIR, detector_override=None) -> FastAPI:
    store = Store(data_dir)
    detector = detector_override or PersonDetector(model_dir, data_dir / "runtime")
    ocr = OCRService(store, model_dir)
    pipeline = Pipeline(store, detector, ocr)
    replay = ReplayManager(pipeline)

    @asynccontextmanager
    async def lifespan(application):
        yield
        await asyncio.to_thread(replay.close)
        for sid in list(pipeline.counters):
            pipeline.flush(sid)
        ocr.close()

    app = FastAPI(title="AI Whiteboard Smart Capture", version="1.0.0", lifespan=lifespan)
    app.state.store, app.state.pipeline, app.state.replay = store, pipeline, replay
    app.add_middleware(CORSMiddleware, allow_origins=sorted(ORIGINS),
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Content-Type"])

    @app.middleware("http")
    async def local_origin(request, call_next):
        origin = request.headers.get("origin")
        if origin and origin not in ORIGINS:
            return JSONResponse({"detail": "Origin is not allowed"}, status_code=403)
        # CORS alone does not stop cross-origin form submissions to a local server.
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Cross-site requests are not allowed"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(ValueError)
    async def bad_input(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(FileNotFoundError)
    async def not_found(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "storage": "local", "detector": detector.status(), "ocr": ocr.status()}

    @app.get("/api/models")
    def models():
        return {"person": detector.status(), "ocr": ocr.status()}

    @app.get("/api/presets")
    def presets():
        return {name: value.model_dump() for name, value in PRESETS.items()}

    @app.get("/api/sessions")
    def list_sessions():
        return store.list()

    @app.post("/api/sessions", status_code=201)
    def create_session(payload: SessionCreate):
        return store.public(store.create(payload))

    @app.get("/api/sessions/{sid}")
    def get_session(sid: str):
        with store.lock(sid):
            pipeline.flush(sid)
            return store.public(store.read(sid))

    @app.patch("/api/sessions/{sid}")
    def edit_session(sid: str, payload: SessionPatch):
        return store.public(store.patch(sid, payload.model_dump(exclude_none=True)))

    @app.put("/api/sessions/{sid}/calibration")
    def set_calibration(sid: str, payload: Calibration):
        with store.lock(sid):
            if pipeline.owners.get(sid, "").startswith("replay:"):
                raise HTTPException(409, "Stop replay before changing calibration")
            points = validate_points([p.model_dump() for p in payload.points])
            calibration = {**payload.model_dump(), "points": [{"x": float(x), "y": float(y)} for x, y in points], "revision": str(uuid.uuid4())}
            data = store.patch(sid, {"calibration": calibration})
            pipeline.reset(sid)
            return store.public(data)

    @app.delete("/api/sessions/{sid}/calibration", status_code=204)
    def clear_calibration(sid: str):
        with store.lock(sid):
            if pipeline.owners.get(sid, "").startswith("replay:"):
                raise HTTPException(409, "Stop replay before changing calibration")
            store.patch(sid, {"calibration": None})
            pipeline.reset(sid)

    @app.patch("/api/sessions/{sid}/settings")
    def set_settings(sid: str, payload: dict):
        with store.lock(sid):
            data = store.read(sid)
            try:
                settings = Settings(**{**data["settings"], **payload})
            except ValidationError as exc:
                raise HTTPException(422, json.loads(exc.json())) from exc
            data = store.patch(sid, {"settings": settings.model_dump()})
            # Fresh detections are required after confidence/model switches.
            pipeline.detections.pop(sid, None)
            return store.public(data)

    @app.post("/api/sessions/{sid}/presets/{name}")
    def set_preset(sid: str, name: str):
        if name not in PRESETS:
            raise HTTPException(404, "Unknown preset")
        # Preserve feature toggles; presets adjust sensitivity only.
        threshold_keys = {"stability_seconds", "change_threshold", "ssim_threshold", "motion_threshold", "capture_interval", "blur_threshold", "obstruction_threshold"}
        return set_settings(sid, {key: value for key, value in PRESETS[name].model_dump().items() if key in threshold_keys})

    @app.patch("/api/sessions/{sid}/captures/{cid}")
    def edit_capture(sid: str, cid: str, payload: CapturePatch):
        return store.edit_capture(sid, cid, payload.model_dump(exclude_none=True))

    @app.delete("/api/sessions/{sid}/captures/{cid}", status_code=204)
    def delete_capture(sid: str, cid: str):
        store.delete_capture(sid, cid)

    @app.get("/api/sessions/{sid}/captures/{cid}/image")
    def image(sid: str, cid: str, variant: str = "original", download: bool = False):
        path = store.capture_path(sid, cid, variant)
        return FileResponse(path, media_type="image/jpeg", filename=f"whiteboard-{cid}.jpg" if download else None)

    @app.get("/api/sessions/{sid}/export/{kind}")
    def export(sid: str, kind: str, enhanced: bool | None = None):
        path = export_session(store, sid, kind, enhanced)
        media = {"pdf": "application/pdf", "zip": "application/zip", "json": "application/json", "txt": "text/plain"}
        return FileResponse(path, media_type=media[kind], filename=f"lecture-{sid[:8]}.{kind}")

    @app.post("/api/sessions/{sid}/replays", status_code=201)
    async def upload_replay(sid: str, file: UploadFile = File(...)):
        store.read(sid)
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".mp4", ".mov", ".avi"}:
            await file.close()
            raise HTTPException(400, "Choose an MP4, MOV, or AVI video")
        directory = store.directory(sid) / "videos"
        directory.mkdir(exist_ok=True)
        target = directory / f"{uuid.uuid4()}{suffix}"
        try:
            size = 0
            with target.open("wb") as stream:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_VIDEO_BYTES:
                        raise HTTPException(413, "Video exceeds the 500 MB limit")
                    stream.write(chunk)
            return await asyncio.to_thread(replay.register, sid, target)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        finally:
            await file.close()

    @app.get("/api/sessions/{sid}/replays/{job_id}")
    def replay_status(sid: str, job_id: str):
        return replay.get(sid, job_id)

    @app.post("/api/sessions/{sid}/replays/{job_id}/start")
    def replay_start(sid: str, job_id: str):
        return replay.start(sid, job_id)

    @app.post("/api/sessions/{sid}/replays/{job_id}/suggestion")
    def replay_suggestion(sid: str, job_id: str):
        import cv2
        replay.get(sid, job_id)
        reader = cv2.VideoCapture(str(replay.jobs[job_id]["path"]))
        try:
            ok, frame = reader.read()
            if not ok:
                raise ValueError("Cannot decode the video preview")
            return {"points": suggest_board(frame)}
        finally:
            reader.release()

    @app.post("/api/sessions/{sid}/replays/{job_id}/control")
    def replay_control(sid: str, job_id: str, payload: ReplayCommand):
        return replay.command(sid, job_id, payload.action, payload.seconds)

    @app.post("/api/sessions/{sid}/replays/{job_id}/manual")
    def replay_manual(sid: str, job_id: str, payload: ReplayManual):
        return replay.manual(sid, job_id, payload.frame_id, payload.force)

    @app.websocket("/ws/sessions/{sid}")
    async def frames(websocket: WebSocket, sid: str):
        if websocket.headers.get("origin") not in ORIGINS:
            await websocket.close(code=1008, reason="Origin is not allowed")
            return
        owner = f"ws:{uuid.uuid4()}"
        acquired = False
        try:
            await websocket.accept()
            await asyncio.to_thread(pipeline.acquire, sid, owner)
            acquired = True
            await websocket.send_json({"type": "connected", "session_id": sid})
            while True:
                text = await websocket.receive_text()
                if len(text) > 2_810_000:
                    await websocket.send_json({"type": "error", "message": "Frame message is too large"})
                    continue
                try:
                    payload = json.loads(text)
                    if isinstance(payload, dict) and payload.get("type") == "reset":
                        await asyncio.to_thread(pipeline.reset, sid)
                        await websocket.send_json({"type": "reset"})
                        continue
                    request = FrameRequest.model_validate(payload)
                    result = await asyncio.to_thread(pipeline.process_request, sid, request, owner)
                    await websocket.send_json(result)
                except (ValueError, ValidationError) as exc:
                    await websocket.send_json({"type": "error", "message": str(exc)[:1000]})
                except Exception:
                    logger.exception("Frame analysis failed for session %s", sid)
                    await websocket.send_json({"type": "error", "message": "Frame processing failed; see the local server log"})
        except WebSocketDisconnect:
            pass
        except (ValueError, FileNotFoundError) as exc:
            await websocket.send_json({"type": "error", "message": str(exc)})
            await websocket.close(code=1008)
        finally:
            if acquired:
                await asyncio.to_thread(pipeline.release, sid, owner)

    # A production build is served by the same local backend. No runtime CDN assets.
    if (ROOT / "frontend" / "dist").is_dir():
        app.mount("/", StaticFiles(directory=ROOT / "frontend" / "dist", html=True), name="frontend")
    return app


app = create_app()
