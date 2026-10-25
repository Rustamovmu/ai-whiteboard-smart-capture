# Five-minute university demonstration

## Prepare

Install dependencies and YOLO weights using the README. Start both local servers, open the dashboard, and create a lecture with a real title/course. Prepare a high-contrast marker, a fixed camera and an evenly lit board. Keep the whole writable surface visible, remove strong reflections and avoid moving the camera afterward.

Generate `data/demo/synthetic-lecture.avi` beforehand for a hardware-independent backup. Make one complete trial on the actual presentation machine. Check that the dashboard says person detection is active after analysis begins; installed weights alone are not a successful inference. Optional OCR is unnecessary for this demonstration.

## Demonstration schedule

| Time | Action | Evidence to show |
| --- | --- | --- |
| 0:00–0:40 | Explain the local-first application; create session and start camera. | Actual live video, visible camera indicator, local backend status. |
| 0:40–1:15 | Calibrate by contour suggestion or drag four corners. | Editable normalized boundary and corrected image after capture. |
| 1:15–2:00 | Write an equation, continue writing briefly, then move away. | Motion/stability transitions, one accepted meaningful state after settling. |
| 2:00–2:40 | Stand still in front of the board, then move aside without changing it. | Real person boxes/confidence and overlap suppress capture; unchanged board does not duplicate. |
| 2:40–3:20 | Add another equation, step away; then erase part and step away. | Chronological additions/erasure captures and actual score/quality measurements. |
| 3:20–4:00 | Open a capture, switch original/enhanced, add a note and use manual capture. | Persisted real images, annotations, manual label and warning override if needed. |
| 4:00–4:35 | Export PDF and reopen the session. | Actual images, lecture cover, timestamps, readable aspect ratios, persisted notes. |
| 4:35–5:00 | Show replay mode and state limitations. | Same pipeline on a labeled synthetic video; no claim of real-person accuracy from the rectangle. |

## Explain the intelligence accurately

OpenCV finds a geometric board proposal, corrects perspective, normalizes illumination and computes blur, motion, pixel/edge/ink differences. SSIM provides another signal. The state machine waits for low motion and checks against the last accepted image.

YOLO11n is a real pretrained neural network detecting people. Intersections between its boxes and the board estimate obstruction. Capture candidates request current-frame inference, so being motionless does not make a detected person disappear. OCR is another optional local neural model but cannot reliably read all handwritten equations and never controls capture.

The appearance classifier says **potential** addition/erasure. It does not understand mathematical meaning. The whole system can miss small changes, subtle occlusion or unusual lighting; show the decision journal when explaining this.

## Failure cases worth showing

- Disable person detection briefly: the interface must report unknown obstruction/motion-only fallback. A still person may then be accepted; this is a documented limitation, not a success.
- Defocus or shake the camera: inspect the actual quality/stability decision. Focus heuristics depend on marker density and resolution.
- Put the person next to the board: their box should not block capture if it has no board intersection.
- Try an incorrect contour proposal and correct it manually.
- Clear the board: earlier captures remain; the default records an event rather than adding an empty page.
- Stop the camera: the browser camera indicator should switch off. Real hardware permission and disconnection behavior must be tested on the presentation machine.

## Replay backup

Create a fresh session, choose Video replay, upload the generated AVI, propose/adjust the board interior and confirm. Start replay. The synthetic video contains an empty board, two writing stages, no-change intervals, a moving rectangular obstruction, blur, exposure change, partial erasure and clearing. Expect three meaningful capture states under Balanced settings with the supplied calibration; results may differ with incorrect corners. Pause, seek or manually capture to demonstrate controls.

## Present evaluation honestly

Show `data/evaluation.json` and explain its labeled time windows, CPU timing and baseline comparison. Identify generated footage as synthetic. Real classroom precision/recall needs separately recorded, manually labeled footage. The public sample-photo smoke check proves model execution, not classroom detection accuracy. See TESTING.md for a repeatable real-world evaluation protocol.
