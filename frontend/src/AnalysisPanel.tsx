import { Activity, ArrowUpRight, Check, CheckCheck, CircleDashed, Clock3, Eye, Focus, ScanLine, ShieldCheck, Sparkles } from 'lucide-react'
import type { Analysis, Settings } from './types'

const prettyState: Record<string, string> = {
  UNCALIBRATED: 'Find your board', OBSERVING: 'Taking a look', MOTION_OR_OCCLUSION: 'A little movement',
  WAITING_FOR_STABILITY: 'Let the ideas settle', REJECTED: 'Waiting for clarity', NO_CHANGE: 'All caught up',
  CAPTURE_ACCEPTED: 'An idea, captured', BOARD_CLEARED: 'A fresh start', CHANGE_ANALYSIS: 'Something new', MANUAL_WARNING: 'Review this capture',
}

export default function AnalysisPanel({ analysis, settings, active, log }: {
  analysis: Analysis | null; settings?: Settings; active: boolean;
  log: { reason: string; state: string; time: string }[];
}) {
  const good = analysis?.state === 'CAPTURE_ACCEPTED' || analysis?.state === 'NO_CHANGE'
  const detector = analysis?.detector
  const stable = analysis?.stable_seconds ?? 0
  return <aside className="analysis-panel">
    <div className="panel-heading"><span className="eyebrow">THE BIG PICTURE</span><span className={`tiny-live ${active ? 'active' : ''}`}><i />{active ? 'Live' : 'Standby'}</span></div>
    <div className={`state-illustration ${good ? 'good' : ''}`}><div className="state-ring" /><div className="state-ring two" /><ScanLine size={30} strokeWidth={1.5} /><span className="spark-one">✧</span><span className="spark-two">✧</span></div>
    <h2>{analysis ? prettyState[analysis.state] || 'Observing the board' : 'Ready when you are'}</h2>
    <p className="state-description">{analysis?.reason || 'Start a camera or replay a video. We’ll watch for the moments worth keeping.'}</p>
    <div className="stability-card"><div><span><Activity size={14} />Board stability</span><strong>{stable ? `${stable.toFixed(1)}s` : '—'}<small> / {settings?.stability_seconds ?? 2}s</small></strong></div>
      <div className="meter"><i style={{ width: `${Math.min(100, stable / (settings?.stability_seconds ?? 2) * 100)}%` }} /></div>
      <span className="micro-copy">A short pause makes a clearer picture.</span>
    </div>
    <div className="measurement-list">
      <div><span><Focus />Image sharpness</span><strong>{analysis?.quality ? analysis.quality.sharpness.toFixed(1) : '—'}</strong></div>
      <div><span><Sparkles />Content change</span><strong>{analysis?.change ? `${(analysis.change.score * 100).toFixed(2)}%` : '—'}</strong></div>
      <div><span><Eye />Board obstruction</span><strong className={analysis?.obstruction_status === 'blocked' ? 'amber-text' : ''}>{analysis?.obstruction_fraction != null ? `${(analysis.obstruction_fraction * 100).toFixed(1)}%` : 'Unknown'}</strong></div>
      <div><span><CircleDashed />Processing time</span><strong>{analysis?.processing_ms != null ? `${Math.round(analysis.processing_ms)} ms` : '—'}</strong></div>
    </div>
    <div className={`detector-notice ${detector?.available ? 'available' : ''}`}><ShieldCheck size={17} /><div><strong>{detector?.available ? 'Person detection active' : detector?.status === 'disabled' ? 'Person detection off' : 'AI detection unavailable'}</strong>
      <p>{detector?.available ? 'YOLO11n · on-device CPU inference' : 'Motion-only fallback. Obstruction is uncertain.'}</p></div></div>
    <div className="decision-heading"><span className="eyebrow">DECISION JOURNAL</span><Clock3 size={14} /></div>
    <div className="decision-log">{!log.length ? <div className="journal-empty"><CheckCheck size={19} /><span>Decisions will appear here as your session unfolds.</span></div> : log.slice(0, 5).map((entry, index) => <div className="decision-entry" key={`${entry.time}-${index}`}><span className={`decision-dot ${entry.state === 'CAPTURE_ACCEPTED' ? 'accepted' : ''}`}>{entry.state === 'CAPTURE_ACCEPTED' ? <Check size={10} /> : <span />}</span><div><p>{entry.reason}</p><time>{entry.time}</time></div></div>)}</div>
    <div className="local-footnote"><ShieldCheck size={13} /><span>Your classroom stays your classroom.<br />Everything is processed locally.</span><ArrowUpRight size={13} /></div>
  </aside>
}
