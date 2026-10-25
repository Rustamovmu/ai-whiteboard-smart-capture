export interface Point { x: number; y: number }
export interface Calibration { points: Point[]; source_id: string; aspect_ratio: number; revision: string }
export interface Settings {
  processing_fps: number; stability_seconds: number; blur_threshold: number; change_threshold: number;
  ssim_threshold: number; motion_threshold: number; obstruction_threshold: number; capture_interval: number;
  detector_interval: number; person_confidence: number; ai_enabled: boolean; auto_capture: boolean;
  ocr_enabled: boolean; enhanced_export: boolean; save_cleared_board: boolean;
}
export interface Detector {
  model: string; device: string; available: boolean; installed: boolean; status: string; error?: string | null;
  boxes?: { box: [number, number, number, number]; confidence: number }[];
  detected_at?: string | null; inference_ms?: number | null;
}
export interface Quality { status: string; sharpness: number; brightness: number; glare: string; focus_uncertain: boolean; reasons: string[]; ink_density: number }
export interface Change { score: number; ssim: number | null; pixel_difference: number | null; edge_difference: number | null; ink_difference: number; meaningful: boolean; change_type: string }
export interface Analysis {
  type: string; frame_id: string; state: string; reason: string; decision?: string;
  calibration?: Calibration | null; suggestion?: Point[] | null; quality?: Quality; change?: Change;
  detector: Detector; motion_score?: number; stable_seconds?: number; obstruction_fraction?: number | null;
  obstruction_status?: string; capture: Capture | null; stats?: Record<string, number>;
  board_preview?: string; processing_ms?: number; source_seconds?: number | null; warnings?: string[];
}
export interface Capture {
  id: string; sequence: number; name: string; note: string; timestamp: string; source_seconds: number | null;
  capture_type: 'manual' | 'automatic'; calibration_revision: string; measurements: Analysis;
  ocr: { status: string; text: string; segments: { text: string; confidence: number }[]; error?: string };
}
export interface Session {
  id: string; title: string; course: string; description: string; created_at: string;
  settings: Settings; calibration: Calibration | null; captures: Capture[];
  stats: Record<string, number>; events: { timestamp: string; event: string }[];
}
export interface SessionSummary extends Omit<Session, 'captures' | 'events'> { capture_count: number }
export interface Replay {
  id: string; session_id: string; source_id: string; width: number; height: number; fps: number;
  duration: number; position: number; progress: number; status: string; preview: string;
  analysis: Analysis | null; error: string | null;
}
