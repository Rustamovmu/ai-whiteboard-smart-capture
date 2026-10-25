# Algorithms and defaults

## Board localization and rectification

OpenCV converts to grayscale, Gaussian-blurs, computes Canny edges, closes small gaps and inspects the largest contours. Polygon approximation looks for a convex quadrilateral covering 8–99% of the image. The suggested boundary is inset 0.8% on each side to exclude common metal frames, then requires user confirmation. It can select another rectangular object; it is not semantic board recognition.

Manual points must be normalized, finite, convex, cover at least 2.5% of the image and have adequately separated corners. Points are canonicalized around their center. Perspective transformation uses `getPerspectiveTransform` and `warpPerspective`, with inclusive pixel dimensions to avoid needless resampling of an axis-aligned crop. Analysis width is capped at 960 pixels and height at 1,600.

Keep the camera fixed. Normalized points handle same-aspect resolution changes, but do not track physical camera movement.

## Quality, enhancement and illumination

Laplacian variance measures sharpness on the rectified image. Mean brightness, dark-pixel fraction, clipped highlights and ink density are also calculated. Brightness below 45 or more than 65% very dark pixels rejects an image. More than 98% clipped highlights on an otherwise textureless board rejects it as uncertain.

A whiteboard is naturally bright. Highlight fraction above 25% is reported as possible glare, not automatically treated as proof of glare. A textureless board cannot establish focus; the result exposes `focus_uncertain` and avoids blindly rejecting a truly empty surface. Strong blur can also remove all texture, so this heuristic cannot guarantee focus.

Content normalization divides grayscale intensity by a Gaussian-smoothed local background. This suppresses moderate exposure shifts and broad shadows. Ink masks combine locally dark pixels and saturated marker colors, excluding connected components smaller than five pixels. Original rectified RGB images are saved alongside separate, mild CLAHE-in-LAB enhanced versions. No grayscale threshold replaces the authoritative original.

## Motion and stability

Normalize adjacent rectified boards, Gaussian-blur, take absolute differences above 18, and morphologically open a 3×3 mask. Its nonzero fraction is the motion score. Motion or significant person obstruction resets stability. Timestamp reversals and gaps over three seconds reset it as well.

Balanced mode requires two seconds of continuously observed low motion. A long interval without observations is not evidence of stability. Manual capture can bypass motion/stability after explicit warnings when appropriate.

## Genuine AI person obstruction

YOLO11n pretrained on COCO runs locally on CPU at a 640-pixel inference size, requesting only class `person`. Its actual normalized boxes/confidences are returned. Rasterizing the union of the person boxes and intersecting it with the actual calibrated polygon estimates board obstruction without double-counting overlapping people. The mask is at most 640 pixels wide; overlap is approximate.

Periodic detections reduce CPU cost, but each automatic capture candidate requires inference on its current frame. A fresh significant obstruction blocks the candidate and resets stability even if the scene is still. Manual candidates also request current inference. Model errors/missing weights/disabled detection produce unknown visibility and an explicit motion-only fallback. A detector can miss a small hand, partial person or unusual pose; boxes are conservative approximations, not segmentation masks.

## Meaningful change

Compare against the last successfully accepted board state, independently of adjacent-frame motion. Calculate:

- SSIM on illumination-normalized grayscale.
- Pixel fraction differing by more than 25 intensity levels.
- Added/removed Canny edges with a one-pixel spatial tolerance.
- Added/removed ink pixels with a one-pixel tolerance.

The combined normalized score is `0.55 × ink_difference + 0.30 × edge_difference + 0.15 × pixel_difference`. A meaningful change requires the score threshold, SSIM or stronger ink evidence, and corroborating ink/edge evidence. SSIM alone never triggers a save. An initial board needs sufficient ink density.

Added/removed ink balance labels potential new content or removed content; larger/mixed changes are major updates or uncertain. Near-zero ink after previously meaningful writing is board-cleared. These are appearance heuristics, not understanding of formulas or diagram meaning.

Duplicate-equivalent states are ignored. Cooldown only delays an otherwise eligible change; comparison remains against the accepted state so the change can be captured afterward. A cleared-board event commits an internal empty baseline even when its image is not added to the gallery. Earlier notes remain intact.

## Central decision order

1. Require matching valid source calibration.
2. Calculate board, person and quality/motion/change measurements.
3. Wait on person obstruction or motion; reset stability.
4. Reject poor quality; reset stability.
5. Wait for the elapsed stability requirement.
6. Ignore insignificant/duplicate states.
7. Respect automatic-capture switch and cooldown.
8. Refresh candidate person inference, then persist the accepted capture/event.
9. Commit the comparison baseline after persistence succeeds.

Manual captures retain their own label and measurements. Blurry/obstructed/AI-unprotected images require explicit override. Unknown AI is never represented as a confidently clear board. Optional OCR executes afterward and has no authority over capture acceptance.

## Configurable values

These are starting values supported by deterministic fixtures, not universal camera-independent thresholds.

| Setting | Balanced | High sensitivity | Conservative |
| --- | ---: | ---: | ---: |
| Processing FPS | 5 | unchanged | unchanged |
| Stable seconds | 2 | 1.25 | 3 |
| Laplacian threshold | 25 | 15 | 40 |
| Change score minimum | 0.0025 | 0.001 | 0.005 |
| SSIM threshold | 0.995 | 0.998 | 0.985 |
| Motion fraction maximum | 0.004 | 0.008 | 0.002 |
| Person overlap fraction | 0.05 | 0.05 | 0.05 |
| Minimum capture interval, seconds | 3 | 2 | 4 |
| Periodic detector interval, seconds | 0.5 | unchanged | unchanged |
| Person confidence minimum | 0.35 | unchanged | unchanged |

Feature defaults: automatic capture/person detection on; OCR, enhanced export and save-cleared-image off. Presets change sensitivity values, preserving feature switches and operational FPS/detector preferences. All settings are validated by Pydantic and consumed by the actual pipeline on subsequent frames. Blur thresholds were lowered after testing ordinary perspective interpolation: sharpness depends strongly on resolution and interpolation, while the synthetic strong-blur fixture remains far below the chosen default.
