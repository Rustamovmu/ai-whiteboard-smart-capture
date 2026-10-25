"""Deterministic synthetic fixtures. A rectangular obstruction is NOT an AI person test."""
import cv2
import numpy as np


def board(stage: int = 0, width: int = 800, height: int = 450) -> np.ndarray:
    image = np.full((height, width, 3), 235, np.uint8)
    # No border in rectified fixtures: avoids treating the board frame as writing.
    scale = width / 800
    if stage >= 1:
        cv2.putText(image, "A = pi r^2", (round(70 * scale), round(130 * scale)), cv2.FONT_HERSHEY_SIMPLEX, 1.6 * scale, (55, 65, 55), max(2, round(3 * scale)), cv2.LINE_AA)
    if stage == 2:
        cv2.putText(image, "C = 2 pi r", (round(70 * scale), round(260 * scale)), cv2.FONT_HERSHEY_SIMPLEX, 1.6 * scale, (140, 65, 40), max(2, round(3 * scale)), cv2.LINE_AA)
        cv2.circle(image, (round(610 * scale), round(220 * scale)), round(65 * scale), (60, 95, 60), max(2, round(3 * scale)), cv2.LINE_AA)
    return image


def frame_at(seconds: float) -> tuple[np.ndarray, str]:
    if seconds < 3:
        pixels, label = board(0), "empty"
    elif seconds < 5:
        pixels, label = board(1), "writing_first"
        x = min(800, int(70 + (seconds - 3) / 2 * 470))
        pixels[:, x:] = 235
        cv2.rectangle(pixels, (x - 15, 80), (x + 15, 155), (95, 105, 110), -1)
    elif seconds < 12:
        pixels, label = board(1), "first_equation"
    elif seconds < 14:
        pixels, label = board(2), "writing_second"
        x = min(800, int(70 + (seconds - 12) / 2 * 650))
        pixels[160:, x:] = 235
        cv2.rectangle(pixels, (x - 15, 205), (x + 15, 280), (95, 105, 110), -1)
    elif seconds < 19:
        pixels, label = board(2), "second_equation"
    elif seconds < 20.4:
        pixels, label = board(2), "synthetic_obstruction_not_person"
        x = int((seconds - 19) / 1.4 * 1000) - 180
        cv2.rectangle(pixels, (x, 0), (x + 180, 449), (75, 85, 90), -1)
    elif seconds < 24:
        pixels, label = board(2), "no_change"
    elif seconds < 26:
        pixels, label = cv2.GaussianBlur(board(2), (25, 25), 9), "blur"
    elif seconds < 28:
        pixels, label = np.clip(board(2).astype(np.float32) * 0.85, 0, 255).astype(np.uint8), "brightness_change"
    elif seconds < 33:
        pixels, label = board(1), "partial_erasure"
    else:
        pixels, label = board(0), "fully_cleared"
    frame = np.full((540, 960, 3), (64, 74, 68), np.uint8)
    cv2.rectangle(frame, (76, 41), (883, 498), (180, 188, 179), -1)
    frame[45:495, 80:880] = pixels
    return frame, label


CALIBRATION = [{"x": 80 / 959, "y": 45 / 539}, {"x": 879 / 959, "y": 45 / 539},
               {"x": 879 / 959, "y": 494 / 539}, {"x": 80 / 959, "y": 494 / 539}]
