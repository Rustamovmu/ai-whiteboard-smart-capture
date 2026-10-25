"""Explainable OpenCV heuristics for illumination, motion, quality and content."""
import cv2
import numpy as np
from skimage.metrics import structural_similarity

from ..schemas import Settings


def gray(image: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def normalize(image: np.ndarray) -> np.ndarray:
    values = gray(image) if image.ndim == 3 else image
    # Divide by a smooth local background: reduces slow shadows and exposure shifts.
    background = cv2.GaussianBlur(values, (0, 0), 21)
    return cv2.divide(values, np.maximum(background, 1), scale=240)


def ink_mask(image: np.ndarray) -> np.ndarray:
    # Local luminance plus saturated marker strokes retains red/blue/green writing.
    normal = normalize(image)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = ((normal < 195) | ((hsv[:, :, 1] > 95) & (hsv[:, :, 2] < 250))).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    keep = np.zeros(count, np.uint8)
    if count > 1:
        keep[1:] = (stats[1:, cv2.CC_STAT_AREA] >= 5).astype(np.uint8)
    return keep[labels]


def enhance(image: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    light, a, b = cv2.split(lab)
    light = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(8, 8)).apply(light)
    return cv2.cvtColor(cv2.merge((light, a, b)), cv2.COLOR_LAB2BGR)


def quality(image: np.ndarray, settings: Settings) -> dict:
    values = gray(image)
    sharpness = float(cv2.Laplacian(values, cv2.CV_64F).var())
    brightness = float(values.mean())
    dark_fraction = float(np.mean(values < 30))
    clipped_fraction = float(np.mean(values > 253))
    density = float(ink_mask(image).mean())
    textureless = density < 0.0005
    reasons = []
    if brightness < 45 or dark_fraction > 0.65:
        reasons.append("Image is too dark")
    if sharpness < settings.blur_threshold and not textureless:
        reasons.append("Low sharpness / possible blur")
    # A white board is naturally bright; clipping alone is reported, not blindly rejected.
    if clipped_fraction > 0.98 and textureless:
        reasons.append("Almost entirely clipped highlights; board content is uncertain")
    return {"status": "rejected" if reasons else "acceptable", "sharpness": round(sharpness, 3),
            "brightness": round(brightness, 2), "dark_fraction": dark_fraction,
            "highlight_fraction": clipped_fraction, "ink_density": density,
            "focus_uncertain": textureless, "glare": "possible" if clipped_fraction > 0.25 else "low",
            "reasons": reasons}


def motion_score(previous: np.ndarray | None, current: np.ndarray) -> float:
    if previous is None or previous.shape != current.shape:
        return 1.0
    a = cv2.GaussianBlur(normalize(previous), (5, 5), 0)
    b = cv2.GaussianBlur(normalize(current), (5, 5), 0)
    mask = (cv2.absdiff(a, b) > 18).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return float(mask.mean())


def compare(previous: np.ndarray | None, current: np.ndarray, settings: Settings) -> dict:
    current_ink = ink_mask(current)
    density = float(current_ink.mean())
    if previous is None:
        return {"ssim": None, "pixel_difference": None, "edge_difference": None,
                "ink_difference": density, "added_fraction": density, "removed_fraction": 0.0,
                "score": density, "meaningful": density >= settings.change_threshold,
                "change_type": "new_content" if density >= settings.change_threshold else "empty_board"}
    if previous.shape != current.shape:
        previous = cv2.resize(previous, (current.shape[1], current.shape[0]))
    a, b = normalize(previous), normalize(current)
    similarity = float(structural_similarity(a, b, data_range=255))
    difference = float(np.mean(cv2.absdiff(a, b) > 25))
    edges_a, edges_b = cv2.Canny(a, 60, 140), cv2.Canny(b, 60, 140)
    kernel = np.ones((3, 3), np.uint8)
    edges_added = (edges_b > 0) & (cv2.dilate(edges_a, kernel) == 0)
    edges_removed = (edges_a > 0) & (cv2.dilate(edges_b, kernel) == 0)
    edge_difference = float(np.mean(edges_added | edges_removed))
    old_ink = ink_mask(previous)
    # A one-pixel tolerance suppresses codec jitter around unchanged strokes.
    added = float(np.mean((current_ink > 0) & (cv2.dilate(old_ink, kernel) == 0)))
    removed = float(np.mean((old_ink > 0) & (cv2.dilate(current_ink, kernel) == 0)))
    ink_difference = added + removed
    score = 0.55 * ink_difference + 0.3 * edge_difference + 0.15 * difference
    meaningful = (score >= settings.change_threshold and
                  (similarity < settings.ssim_threshold or ink_difference > 2 * settings.change_threshold) and
                  (ink_difference >= settings.change_threshold * 0.5 or edge_difference >= settings.change_threshold))
    if not meaningful:
        kind = "no_change" if score < settings.change_threshold * 0.4 else "insignificant"
    elif density < 0.0005 and float(old_ink.mean()) > settings.change_threshold:
        kind = "board_cleared"
    elif score > 0.08 or (added > settings.change_threshold and removed > settings.change_threshold):
        kind = "major_update"
    else:
        kind = "new_content" if added > removed * 1.4 else "content_removed" if removed > added * 1.4 else "uncertain"
    return {"ssim": similarity, "pixel_difference": difference, "edge_difference": edge_difference,
            "ink_difference": ink_difference, "added_fraction": added, "removed_fraction": removed,
            "score": score, "meaningful": meaningful, "change_type": kind}
