"""Validated public REST/WebSocket models. Coordinates refer to unmirrored source images."""
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    processing_fps: float = Field(5, ge=1, le=10)
    stability_seconds: float = Field(2, ge=0.25, le=15)
    blur_threshold: float = Field(25, ge=0, le=1000)
    change_threshold: float = Field(0.0025, ge=0.0001, le=0.2)
    ssim_threshold: float = Field(0.995, ge=0.5, le=1)
    motion_threshold: float = Field(0.004, ge=0.0001, le=0.5)
    obstruction_threshold: float = Field(0.05, ge=0.005, le=0.8)
    capture_interval: float = Field(3, ge=0, le=120)
    detector_interval: float = Field(0.5, ge=0.1, le=5)
    person_confidence: float = Field(0.35, ge=0.1, le=0.95)
    ai_enabled: bool = True
    auto_capture: bool = True
    ocr_enabled: bool = False
    enhanced_export: bool = False
    save_cleared_board: bool = False


PRESETS = {
    "balanced": Settings(),
    "high": Settings(stability_seconds=1.25, blur_threshold=15, change_threshold=0.001, ssim_threshold=0.998, motion_threshold=0.008, capture_interval=2),
    "conservative": Settings(stability_seconds=3, blur_threshold=40, change_threshold=0.005, ssim_threshold=0.985, motion_threshold=0.002, capture_interval=4),
}


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    course: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=5000)


class SessionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    course: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class CapturePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=10000)


class Point(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class Calibration(BaseModel):
    points: list[Point] = Field(min_length=4, max_length=4)
    source_id: str = Field(min_length=1, max_length=200)
    aspect_ratio: float = Field(gt=0.1, lt=10)
    revision: str = ""


class FrameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["frame", "manual", "suggest"] = "frame"
    frame_id: str = Field(min_length=1, max_length=100)
    source_id: str = Field(min_length=1, max_length=200)
    width: int = Field(ge=16, le=8192)
    height: int = Field(ge=16, le=8192)
    jpeg: str = Field(max_length=2_800_000)
    force: bool = False


class ReplayCommand(BaseModel):
    action: Literal["pause", "resume", "cancel", "seek"]
    seconds: float = Field(default=0, ge=0)


class ReplayManual(BaseModel):
    frame_id: str = Field(min_length=1, max_length=100)
    force: bool = False
