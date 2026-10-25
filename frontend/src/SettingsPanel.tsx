import { Check, SlidersHorizontal, Sparkles, Turtle, Zap } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { Session, Settings } from './types'
import { api } from './api'

const fields: { key: keyof Settings; label: string; help: string; min: number; max: number; step: number; unit?: string }[] = [
  { key: 'processing_fps', label: 'Processing rate', help: 'Analysis frames per second. The preview stays smooth.', min: 1, max: 10, step: 1, unit: 'fps' },
  { key: 'stability_seconds', label: 'Stability duration', help: 'How long the board must remain still.', min: 0.25, max: 15, step: 0.25, unit: 's' },
  { key: 'blur_threshold', label: 'Minimum sharpness', help: 'Laplacian variance. Higher values reject more images.', min: 0, max: 1000, step: 1 },
  { key: 'change_threshold', label: 'Meaningful change', help: 'Combined normalized content-change threshold.', min: 0.0001, max: 0.2, step: 0.0001 },
  { key: 'ssim_threshold', label: 'SSIM sensitivity', help: 'Higher similarity thresholds detect smaller differences.', min: 0.5, max: 1, step: 0.001 },
  { key: 'motion_threshold', label: 'Motion tolerance', help: 'Maximum fraction of moving board pixels.', min: 0.0001, max: 0.5, step: 0.0001 },
  { key: 'obstruction_threshold', label: 'Person overlap limit', help: 'Fraction of the board covered by person boxes.', min: 0.005, max: 0.8, step: 0.005 },
  { key: 'capture_interval', label: 'Capture cooldown', help: 'Minimum interval; pending changes remain eligible.', min: 0, max: 120, step: 0.5, unit: 's' },
  { key: 'detector_interval', label: 'AI detection interval', help: 'Every capture candidate still gets a fresh detection.', min: 0.1, max: 5, step: 0.1, unit: 's' },
  { key: 'person_confidence', label: 'Person confidence', help: 'Minimum actual model confidence for person boxes.', min: 0.1, max: 0.95, step: 0.05 },
]
const toggles: { key: keyof Settings; label: string; help: string }[] = [
  { key: 'auto_capture', label: 'Automatic capture', help: 'Save stable, meaningful whiteboard changes.' },
  { key: 'ai_enabled', label: 'AI person detection', help: 'Use the local YOLO11n model to suppress obstructed captures.' },
  { key: 'ocr_enabled', label: 'Recognize text after capture', help: 'Optional EasyOCR installation and offline models required.' },
  { key: 'enhanced_export', label: 'Export enhanced images', help: 'Use contrast-enhanced copies in PDF and ZIP exports.' },
  { key: 'save_cleared_board', label: 'Save cleared boards', help: 'Save an image in addition to recording the board-cleared event.' },
]

export default function SettingsPanel({ session, onSaved, onError }: { session: Session; onSaved: (session: Session) => void; onError: (text: string) => void }) {
  const [draft, setDraft] = useState(session.settings)
  const [saving, setSaving] = useState(false)
  useEffect(() => { setDraft(session.settings) }, [session.id, JSON.stringify(session.settings)])
  const preset = async (name: string) => {
    try { onSaved(await api<Session>(`/sessions/${session.id}/presets/${name}`, 'POST')) }
    catch (error) { onError(String(error)) }
  }
  return <div className="settings-content">
    <div className="section-intro"><div className="section-icon"><SlidersHorizontal size={23} /></div><div><h2>A little fine-tuning.</h2><p>Make capture work for your room, camera, and teaching style.</p></div></div>
    <div className="preset-grid">{[{ name: 'high', title: 'High sensitivity', icon: Zap, text: 'Keep the smaller details.' }, { name: 'balanced', title: 'Balanced', icon: Sparkles, text: 'A good place to start.' }, { name: 'conservative', title: 'Conservative', icon: Turtle, text: 'Wait for a clearer signal.' }].map(p => <button key={p.name} className={`preset-card ${p.name === 'balanced' ? 'recommended' : ''}`} onClick={() => preset(p.name)}><p.icon size={20} /><strong>{p.title}</strong><span>{p.text}</span>{p.name === 'balanced' && <small>RECOMMENDED</small>}</button>)}</div>
    <form onSubmit={async event => { event.preventDefault(); setSaving(true); try { onSaved(await api<Session>(`/sessions/${session.id}/settings`, 'PATCH', draft)) } catch (error) { onError(String(error)) } finally { setSaving(false) } }}>
      <div className="settings-card"><div className="card-title"><h3>Capture intelligence</h3><span>Applied to this lecture session</span></div><div className="settings-fields">{fields.map(field => <label key={field.key} className="setting-field"><span><strong>{field.label}</strong><small>{field.help}</small></span><div><input type="number" min={field.min} max={field.max} step={field.step} required value={draft[field.key] as number} onChange={e => setDraft({ ...draft, [field.key]: Number(e.target.value) })} />{field.unit && <em>{field.unit}</em>}</div></label>)}</div></div>
      <div className="settings-card"><div className="card-title"><h3>Features & output</h3></div>{toggles.map(field => <label className="toggle-setting" key={field.key}><span><strong>{field.label}</strong><small>{field.help}</small></span><input type="checkbox" role="switch" checked={draft[field.key] as boolean} onChange={e => setDraft({ ...draft, [field.key]: e.target.checked })} /></label>)}</div>
      <div className="settings-actions"><span>Changes affect the actual analysis pipeline.</span><button className="button primary" disabled={saving}><Check size={16} />{saving ? 'Applying…' : 'Apply settings'}</button></div>
    </form>
  </div>
}
