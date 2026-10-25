"""Board detection and normalized calibration; no learned board detector is claimed."""
import cv2
import numpy as np


def validate_points(points: list[dict]) -> np.ndarray:
    array = np.array([[p["x"], p["y"]] for p in points], dtype=np.float32)
    if array.shape != (4, 2) or not np.isfinite(array).all() or (array < 0).any() or (array > 1).any():
        raise ValueError("Select four corners inside the image")
    if not cv2.isContourConvex(array) or cv2.contourArea(array) < 0.025:
        raise ValueError("Corners must form a convex board covering at least 2.5% of the image")
    if min(np.linalg.norm(array[i] - array[(i + 1) % 4]) for i in range(4)) < 0.025:
        raise ValueError("Board corners are too close together")
    # Canonical TL, TR, BR, BL order, including points dragged across the image.
    center = array.mean(axis=0)
    array = array[np.argsort(np.arctan2(array[:, 1] - center[1], array[:, 0] - center[0]))]
    array = np.roll(array, -np.argmin(array.sum(axis=1)), axis=0)
    return array


def rectify(frame: np.ndarray, points: list[dict], max_width: int = 960) -> np.ndarray:
    normalized = validate_points(points)
    height, width = frame.shape[:2]
    src = normalized * np.array([width - 1, height - 1], dtype=np.float32)
    board_width = max(np.linalg.norm(src[1] - src[0]), np.linalg.norm(src[2] - src[3])) + 1
    board_height = max(np.linalg.norm(src[3] - src[0]), np.linalg.norm(src[2] - src[1])) + 1
    scale = min(1, max_width / board_width, 1600 / board_height)
    out_w, out_h = max(32, round(board_width * scale)), max(32, round(board_height * scale))
    dst = np.array([[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]], np.float32)
    transform = cv2.getPerspectiveTransform(src.astype(np.float32), dst)
    return cv2.warpPerspective(frame, transform, (out_w, out_h))


def suggest_board(frame: np.ndarray) -> list[dict] | None:
    height, width = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 120)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:40]:
        poly = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
        area = cv2.contourArea(poly) / (width * height)
        if len(poly) != 4 or not 0.08 < area < 0.99:
            continue
        pts = [{"x": float(p[0][0] / (width - 1)), "y": float(p[0][1] / (height - 1))} for p in poly]
        try:
            ordered = validate_points(pts)
            # Propose the writable interior instead of including a metal frame as ink.
            # This remains a user-confirmed suggestion and all corners can be adjusted.
            center = ordered.mean(axis=0)
            ordered = center + (ordered - center) * 0.984
            return [{"x": float(x), "y": float(y)} for x, y in ordered]
        except ValueError:
            continue
    return None


def obstruction_fraction(shape: tuple, points: list[dict], boxes: list[dict]) -> float:
    # Rasterized union handles overlapping people and clips against the actual board polygon.
    height, width = shape[:2]
    scale = min(1, 640 / width)
    width, height = max(1, round(width * scale)), max(1, round(height * scale))
    board = np.zeros((height, width), np.uint8)
    polygon = np.round(validate_points(points) * [width - 1, height - 1]).astype(np.int32)
    cv2.fillConvexPoly(board, polygon, 1)
    people = np.zeros_like(board)
    for box in boxes:
        x1, y1, x2, y2 = box["box"]
        cv2.rectangle(people, (round(x1 * (width - 1)), round(y1 * (height - 1))),
                      (round(x2 * (width - 1)), round(y2 * (height - 1))), 1, -1)
    return float(np.count_nonzero(board & people) / max(1, np.count_nonzero(board)))
