import base64

import cv2
import numpy as np
import pytest

from backend.app.schemas import Settings
from backend.app.services.pipeline import decode_jpeg
from backend.app.vision.decision_engine import DecisionEngine
from backend.app.vision.geometry import obstruction_fraction, rectify, suggest_board, validate_points
from backend.app.vision.metrics import compare, motion_score, quality
from scripts.demo_assets import board, frame_at, CALIBRATION
from .conftest import FULL_CALIBRATION


def test_sharpness_and_blur():
    sharp = quality(board(2), Settings())
    blurry = quality(cv2.GaussianBlur(board(2), (25, 25), 9), Settings())
    assert sharp["status"] == "acceptable"
    assert blurry["sharpness"] < sharp["sharpness"] * 0.1
    assert blurry["status"] == "rejected"


def test_empty_board_is_not_automatically_called_blurry():
    result = quality(board(0), Settings())
    assert result["status"] == "acceptable"
    assert result["focus_uncertain"]


def test_dark_and_clipped_images():
    assert quality(np.zeros((120, 200, 3), np.uint8), Settings())["status"] == "rejected"
    assert quality(np.full((120, 200, 3), 255, np.uint8), Settings())["status"] == "rejected"


def test_perspective_rectification():
    raw, _ = frame_at(8)
    result = rectify(raw, CALIBRATION)
    assert abs(result.shape[1] / result.shape[0] - 800 / 450) < 0.02
    assert compare(board(1), cv2.resize(result, (800, 450)), Settings())["score"] < 0.003


@pytest.mark.parametrize("points", [
    [{"x": 0, "y": 0}] * 4,
    [{"x": 0, "y": 0}, {"x": 1, "y": 1}, {"x": 1, "y": 0}, {"x": 0, "y": 1}],
    [{"x": 0, "y": 0}, {"x": 0.001, "y": 0}, {"x": 0.001, "y": 0.001}, {"x": 0, "y": 0.001}],
])
def test_invalid_quadrilaterals(points):
    with pytest.raises(ValueError):
        validate_points(points)


def test_board_detection_proposes_not_commits():
    raw, _ = frame_at(8)
    points = suggest_board(raw)
    assert points is not None
    validate_points(points)


def test_proposed_writable_interior_handles_sharp_writing_and_empty_board():
    raw, _ = frame_at(8)
    points = suggest_board(raw)
    assert quality(rectify(raw, points), Settings())["status"] == "acceptable"
    empty, _ = frame_at(36)
    result = quality(rectify(empty, points), Settings())
    assert result["status"] == "acceptable"
    assert result["ink_density"] < 0.0005


def test_person_overlap_is_polygon_union():
    points = FULL_CALIBRATION["points"]
    box = {"box": [0, 0, 0.5, 1], "confidence": 0.9}
    single = obstruction_fraction((450, 800, 3), points, [box])
    duplicate = obstruction_fraction((450, 800, 3), points, [box, box])
    assert 0.49 < single < 0.51
    assert single == duplicate
    inner = [{"x": .2, "y": .2}, {"x": .8, "y": .2}, {"x": .8, "y": .8}, {"x": .2, "y": .8}]
    assert obstruction_fraction((450, 800, 3), inner, [{"box": [0, 0, .1, 1]}]) == 0


def test_multisignal_addition_erasure_and_clear():
    assert compare(board(1), board(2), Settings())["change_type"] == "new_content"
    assert compare(board(2), board(1), Settings())["change_type"] == "content_removed"
    assert compare(board(1), board(0), Settings())["change_type"] == "board_cleared"
    assert compare(board(1), board(2), Settings())["ssim"] < 1


def test_duplicates_brightness_noise_and_compression():
    image = board(2)
    rng = np.random.default_rng(7)
    noisy = np.clip(image.astype(float) + rng.normal(0, 1, image.shape), 0, 255).astype(np.uint8)
    darker = np.clip(image.astype(float) * 0.85, 0, 255).astype(np.uint8)
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
    assert ok
    compressed = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    for variant in (image, noisy, darker, compressed):
        result = compare(image, variant, Settings())
        assert not result["meaningful"], result


def test_motion_difference():
    assert motion_score(board(2), board(2)) == 0
    assert motion_score(board(0), board(2)) > 0


def test_stability_requires_elapsed_time_and_occlusion_blocks_stationary_person():
    engine, settings = DecisionEngine(), Settings()
    pixels = board(1)
    assert engine.analyze(pixels, 0, settings, 0)["decision"] == "wait"
    assert engine.analyze(pixels, .2, settings, 0)["state"] == "WAITING_FOR_STABILITY"
    assert engine.analyze(pixels, 1, settings, 0)["decision"] == "wait"
    assert engine.analyze(pixels, 2.3, settings, 0)["decision"] == "capture"
    engine.commit(pixels, 2.3)
    assert engine.analyze(pixels, 2.5, settings, 0)["decision"] == "ignore"
    for timestamp in (3, 4, 5):
        assert engine.analyze(board(2), timestamp, settings, .3)["state"] == "MOTION_OR_OCCLUSION"


def test_cooldown_keeps_real_change_eligible():
    engine, settings = DecisionEngine(), Settings(stability_seconds=.25, capture_interval=3)
    engine.commit(board(1), 0)
    engine.analyze(board(2), .2, settings, 0)
    engine.analyze(board(2), .4, settings, 0)
    assert engine.analyze(board(2), .8, settings, 0)["reason"] == "Meaningful change pending capture cooldown"
    assert engine.analyze(board(2), 3.1, settings, 0)["decision"] == "capture"


def test_interrupted_motion_and_clock_reset():
    engine, settings = DecisionEngine(), Settings()
    engine.analyze(board(1), 0, settings, 0)
    engine.analyze(board(1), .2, settings, 0)
    engine.analyze(board(1), 1, settings, 0)
    assert engine.analyze(board(1), 10, settings, 0)["stable_seconds"] == 0
    assert engine.analyze(board(1), .5, settings, 0)["stable_seconds"] == 0


@pytest.mark.parametrize("encoded", ["", "not-base64!", base64.b64encode(b"not an image").decode()])
def test_invalid_image_handling(encoded):
    with pytest.raises(ValueError):
        decode_jpeg(encoded, 800, 450)


def test_declared_dimensions_are_verified(packet):
    with pytest.raises(ValueError, match="dimensions"):
        decode_jpeg(packet()["jpeg"], 20, 20)
