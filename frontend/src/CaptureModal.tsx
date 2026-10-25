import { Check, ChevronLeft, ChevronRight, Copy, Download, Info, ScanText, Trash2, X, ZoomIn, ZoomOut } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, imageUrl, timeLabel } from './api'
import type { Capture, Session } from './types'

export default function CaptureModal({ capture, session, onClose, onNavigate, onRefresh, onError }: {
  capture: Capture; session: Session; onClose: () => void; onNavigate: (id: string) => void;
  onRefresh: () => Promise<void>; onError: (message: string) => void;
}) {
  const [enhanced, setEnhanced] = useState(false)
  const [zoom, setZoom] = useState(1)
  const [name, setName] = useState(capture.name)
  const [note, setNote] = useState(capture.note)
  const [metadata, setMetadata] = useState(false)
  const [saving, setSaving] = useState(false)
  const index = session.captures.findIndex(c => c.id === capture.id)
  useEffect(() => { setName(capture.name); setNote(capture.note); setZoom(1) }, [capture.id, capture.name, capture.note])
  useEffect(() => { const key = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }; window.addEventListener('keydown', key); return () => window.removeEventListener('keydown', key) }, [onClose])
  return <div className="modal-backdrop" onClick={onClose}><section className="capture-modal" role="dialog" aria-modal="true" aria-label="Capture details" onClick={e => e.stopPropagation()}>
    <div className="modal-top"><div><span className="eyebrow">CAPTURE {String(capture.sequence).padStart(2, '0')}</span><h2>{capture.name}</h2></div><button className="icon-button" aria-label="Close capture details" onClick={onClose}><X size={21} /></button></div>
    <div className="capture-modal-body"><div className="image-review"><div className="image-toolbar"><div className="segmented"><button className={!enhanced ? 'selected' : ''} onClick={() => setEnhanced(false)}>Original</button><button className={enhanced ? 'selected' : ''} onClick={() => setEnhanced(true)}>Enhanced</button></div><div className="button-row"><button className="icon-button" aria-label="Zoom out" onClick={() => setZoom(Math.max(0.5, zoom - 0.25))}><ZoomOut size={17} /></button><span>{Math.round(zoom * 100)}%</span><button className="icon-button" aria-label="Zoom in" onClick={() => setZoom(Math.min(3, zoom + 0.25))}><ZoomIn size={17} /></button></div></div>
      <div className="image-scroll"><img src={imageUrl(session.id, capture.id, enhanced ? 'enhanced' : 'original')} alt={capture.name} style={{ width: `${zoom * 100}%`, maxWidth: 'none' }} /></div>
      <div className="image-navigation"><button className="button subtle" disabled={index <= 0} onClick={() => onNavigate(session.captures[index - 1].id)}><ChevronLeft size={16} />Previous</button><span>{index + 1} of {session.captures.length}</span><button className="button subtle" disabled={index >= session.captures.length - 1} onClick={() => onNavigate(session.captures[index + 1].id)}>Next<ChevronRight size={16} /></button></div>
    </div><div className="capture-details"><div className="capture-meta"><span className={`tag ${capture.capture_type === 'automatic' ? 'green' : ''}`}>{capture.capture_type}</span><time>{timeLabel(capture.timestamp)}</time>{capture.source_seconds != null && <span>Video · {capture.source_seconds.toFixed(1)}s</span>}</div>
      <form onSubmit={async e => { e.preventDefault(); setSaving(true); try { await api(`/sessions/${session.id}/captures/${capture.id}`, 'PATCH', { name, note }); await onRefresh() } catch (error) { onError(String(error)) } finally { setSaving(false) } }}>
        <label className="form-field">Capture name<input required maxLength={200} value={name} onChange={e => setName(e.target.value)} /></label><label className="form-field">Your notes<textarea rows={4} maxLength={10000} placeholder="Add context, a question, or a thought…" value={note} onChange={e => setNote(e.target.value)} /></label><button className="button primary full" disabled={saving}><Check size={15} />{saving ? 'Saving…' : 'Save changes'}</button>
      </form>
      <div className="ocr-section"><h4><ScanText size={16} />Recognized text<span className="tag">{capture.ocr.status}</span></h4>{capture.ocr.text ? <><p className="ocr-text">{capture.ocr.text}</p><small>Recognition may contain errors. The image is authoritative.</small><div className="ocr-confidence">{capture.ocr.segments.map((s, i) => <span key={i}>{s.text}: {Math.round(s.confidence * 100)}%</span>)}</div><button className="button subtle" onClick={() => navigator.clipboard.writeText(capture.ocr.text).catch(() => onError('Clipboard access was denied. Select the text to copy it.'))}><Copy size={14} />Copy text</button></> : <p>{capture.ocr.error || 'Enable optional offline OCR in Settings to recognize future captures.'}</p>}</div>
      <div className="button-row"><a className="button secondary" href={imageUrl(session.id, capture.id, enhanced ? 'enhanced' : 'original', true)}><Download size={15} />Image</a><button className="button secondary" onClick={() => setMetadata(!metadata)}><Info size={15} />Details</button></div>
      {metadata && <pre className="metadata-box">{JSON.stringify(capture.measurements, null, 2)}</pre>}
      <button className="delete-capture" onClick={async () => { if (!window.confirm(`Delete “${capture.name}”? This removes its saved images.`)) return; try { await api(`/sessions/${session.id}/captures/${capture.id}`, 'DELETE'); await onRefresh(); onClose() } catch (error) { onError(String(error)) } }}><Trash2 size={14} />Delete capture</button>
    </div></div>
  </section></div>
}
