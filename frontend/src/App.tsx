import { useCallback, useEffect, useRef, useState } from 'react'
import { Activity, ArrowDownToLine, ArrowRight, ArrowUpRight, BookOpen, Camera, Check, ChevronDown, CircleHelp, Clock3, Ellipsis, FolderOpen, Grid2X2, ImagePlus, Leaf, ListFilter, LoaderCircle, Maximize2, MonitorPlay, Moon, PanelLeftClose, Pause, Play, Plus, Scan, Search, Settings2, ShieldCheck, Sparkles, Square, Sun, Upload, Video, X } from 'lucide-react'
import { api, duration, imageUrl, timeLabel } from './api'
import type { Analysis, Point, Replay, Session, SessionSummary, Settings } from './types'
import { useCamera } from './useCamera'
import BoardOverlay, { defaultCorners } from './BoardOverlay'
import AnalysisPanel from './AnalysisPanel'
import SettingsPanel from './SettingsPanel'
import CaptureModal from './CaptureModal'

type Page = 'dashboard' | 'live' | 'sessions' | 'notes' | 'settings'
type Journal = { reason: string; state: string; time: string }

export default function App() {
  const [page, setPage] = useState<Page>('dashboard')
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [session, setSession] = useState<Session | null>(null)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [log, setLog] = useState<Journal[]>([])
  const [mode, setMode] = useState<'camera' | 'video'>('camera')
  const [replay, setReplay] = useState<Replay | null>(null)
  const [uploading, setUploading] = useState(false)
  const [editing, setEditing] = useState(false)
  const [points, setPoints] = useState<Point[]>(defaultCorners)
  const [newSession, setNewSession] = useState(false)
  const [editSession, setEditSession] = useState(false)
  const [selectedCapture, setSelectedCapture] = useState<string | null>(null)
  const [manualWarning, setManualWarning] = useState<Analysis | null>(null)
  const [toast, setToast] = useState<{ text: string; error: boolean } | null>(null)
  const [backend, setBackend] = useState<'connecting' | 'connected' | 'offline'>('connecting')
  const [dark, setDark] = useState(() => localStorage.getItem('boardly-theme') === 'dark')
  const [help, setHelp] = useState(false)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [exporting, setExporting] = useState(false)
  const [exportMenu, setExportMenu] = useState(false)
  const [now, setNow] = useState(Date.now())
  const [device, setDevice] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const uploadInput = useRef<HTMLInputElement>(null)
  const canvasContainer = useRef<HTMLDivElement>(null)
  const sessionRef = useRef<Session | null>(session)
  sessionRef.current = session
  const lastJournal = useRef('')
  const lastCapture = useRef('')
  const replayManualId = useRef('')

  const notify = useCallback((text: string, error = false) => setToast({ text, error }), [])
  const onError = useCallback((message: string) => notify(message.replace(/^Error: /, ''), true), [notify])
  const refreshList = useCallback(async () => { setSessions(await api<SessionSummary[]>('/sessions')) }, [])
  const refreshSession = useCallback(async () => {
    if (sessionRef.current) {
      const current = await api<Session>(`/sessions/${sessionRef.current.id}`)
      if (current.id === sessionRef.current?.id) setSession(current)
    }
    await refreshList()
  }, [refreshList])

  const onAnalysis = useCallback((value: Analysis) => {
    setAnalysis(value)
    if (value.suggestion) { setPoints(value.suggestion); setEditing(true); notify('Board boundary found. Adjust the corners, then confirm calibration.') }
    else if ('suggestion' in value) { notify('No clear boundary found. Position the four corners manually.', true); setEditing(true) }
    if (value.decision === 'confirm') setManualWarning(value)
    if (value.capture && lastCapture.current !== value.capture.id) {
      lastCapture.current = value.capture.id
      notify(value.capture.capture_type === 'manual' ? 'Your whiteboard has been captured.' : 'A new idea, safely captured.')
      refreshSession().catch(error => onError(String(error)))
    }
    if (value.reason && value.reason !== lastJournal.current) {
      lastJournal.current = value.reason
      setLog(previous => [{ reason: value.reason, state: value.state, time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) }, ...previous].slice(0, 12))
    }
  }, [notify, refreshSession, onError])

  const camera = useCamera(session?.id, session?.settings.processing_fps ?? 5, onAnalysis, onError, editing)
  const sourceId = mode === 'camera' ? camera.sourceId : replay?.source_id || ''
  const dimensions = mode === 'camera' ? camera.dimensions : { width: replay?.width || 1280, height: replay?.height || 720 }
  const calibrated = !!session?.calibration && session.calibration.source_id === sourceId &&
    Math.abs(session.calibration.aspect_ratio / (dimensions.width / dimensions.height) - 1) < 0.02
  const active = mode === 'camera' ? !!camera.stream && !camera.paused && camera.connection === 'connected' : replay?.status === 'running'
  const sourceReady = mode === 'camera' ? !!camera.stream : !!replay
  const busyReplay = replay?.status === 'running' || replay?.status === 'paused'
  const stats = analysis?.stats || session?.stats || {}
  const captures = session?.captures || []
  const matchingCaptures = captures.filter(c => (!query || `${c.name} ${c.note} ${c.ocr.text}`.toLowerCase().includes(query.toLowerCase())) && (filter === 'all' || c.capture_type === filter))
  const shownCaptures = page === 'notes' ? matchingCaptures : captures.slice(-4).reverse()

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? 'dark' : 'light'
    localStorage.setItem('boardly-theme', dark ? 'dark' : 'light')
  }, [dark])
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer) }, [])
  useEffect(() => { if (!toast) return; const timer = setTimeout(() => setToast(null), toast.error ? 11000 : 5000); return () => clearTimeout(timer) }, [toast])
  useEffect(() => {
    let cancelled = false
    const boot = async () => {
      try {
        await api('/health')
        const list = await api<SessionSummary[]>('/sessions')
        if (cancelled) return
        setBackend('connected')
        setSessions(list)
        const saved = localStorage.getItem('boardly-session')
        const candidate = list.find(s => s.id === saved) || list[0]
        if (candidate) {
          const data = await api<Session>(`/sessions/${candidate.id}`)
          if (!cancelled) setSession(data)
        }
      } catch (error) { if (!cancelled) { setBackend('offline'); onError(`Cannot connect to the backend. Start .venv/bin/python main.py. ${String(error)}`) } }
    }
    boot()
    const timer = setInterval(() => api('/health').then(() => { if (!cancelled) setBackend('connected') }).catch(() => { if (!cancelled) setBackend('offline') }), 15000)
    return () => { cancelled = true; clearInterval(timer) }
  }, [onError])
  useEffect(() => {
    if (!replay || !session || !busyReplay) return
    let cancelled = false, loading = false
    const timer = setInterval(async () => {
      if (loading) return
      loading = true
      try {
        const value = await api<Replay>(`/sessions/${session.id}/replays/${replay.id}`)
        if (cancelled) return
        setReplay(value)
        if (value.analysis) onAnalysis(value.analysis)
        if (value.error) onError(value.error)
        if (value.status === 'completed') { notify('Replay complete. Your captures are ready to review.'); await refreshSession() }
      } catch (error) { if (!cancelled) onError(String(error)) }
      finally { loading = false }
    }, 400)
    return () => { cancelled = true; clearInterval(timer) }
  }, [replay?.id, busyReplay, session?.id, onAnalysis, onError, notify, refreshSession])
  useEffect(() => {
    if (!session || !session.captures.some(c => ['queued', 'running'].includes(c.ocr.status))) return
    const timer = setInterval(() => refreshSession().catch(error => onError(String(error))), 3000)
    return () => clearInterval(timer)
  }, [session?.id, session?.captures, refreshSession, onError])

  const replayControl = async (action: string, seconds = 0) => {
    if (!session || !replay) return
    try { setReplay(await api<Replay>(`/sessions/${session.id}/replays/${replay.id}/control`, 'POST', { action, seconds })) }
    catch (error) { onError(String(error)) }
  }
  const manualReplay = async (force = false) => {
    if (!session || !replay) return
    if (!force) replayManualId.current = crypto.randomUUID()
    try {
      const result = await api<Analysis>(`/sessions/${session.id}/replays/${replay.id}/manual`, 'POST', { frame_id: replayManualId.current, force })
      onAnalysis(result)
      setReplay(await api<Replay>(`/sessions/${session.id}/replays/${replay.id}`))
    } catch (error) { onError(String(error)) }
  }
  const stopCurrent = async () => {
    camera.stop()
    if (busyReplay) await replayControl('cancel')
  }
  const openSession = async (id: string) => {
    await stopCurrent()
    try {
      setSession(await api<Session>(`/sessions/${id}`))
      localStorage.setItem('boardly-session', id)
      setAnalysis(null); setLog([]); setReplay(null); setEditing(false); setSelectedCapture(null); setMode('camera'); setPage('dashboard')
      lastJournal.current = ''; lastCapture.current = ''
    } catch (error) { onError(String(error)) }
  }
  const updateSettings = async (patch: Partial<Settings>) => {
    if (!session) return
    try { setSession(await api<Session>(`/sessions/${session.id}/settings`, 'PATCH', patch)) }
    catch (error) { onError(String(error)) }
  }
  const saveCalibration = async () => {
    if (!session) return
    try {
      setSession(await api<Session>(`/sessions/${session.id}/calibration`, 'PUT', { points, source_id: sourceId, aspect_ratio: dimensions.width / dimensions.height }))
      setEditing(false); setAnalysis(null)
      notify('Board calibrated. You’re ready to capture.')
    } catch (error) { onError(String(error)) }
  }
  const suggest = async () => {
    setPoints(calibrated ? session!.calibration!.points : defaultCorners)
    setEditing(true)
    if (mode === 'camera') camera.send('suggest')
    else if (session && replay) {
      try {
        const result = await api<{ points: Point[] | null }>(`/sessions/${session.id}/replays/${replay.id}/suggestion`, 'POST')
        if (result.points) setPoints(result.points)
        else notify('No clear boundary found. Drag the four corners to your board.')
      } catch (error) { onError(String(error)) }
    }
  }
  const exportFile = async (kind: string) => {
    if (!session) return
    setExporting(true); setExportMenu(false)
    try {
      const response = await fetch(`/api/sessions/${session.id}/export/${kind}`)
      if (!response.ok) throw new Error('Export failed. Check the backend log and try again.')
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement('a'); link.href = url; link.download = `${session.title.replace(/[^a-z0-9_-]/gi, '_')}.${kind}`; link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      notify(`Your ${kind.toUpperCase()} export is ready.`)
    } catch (error) { onError(String(error)) }
    finally { setExporting(false) }
  }
  const navigate = async (target: Page) => { if (['sessions', 'notes', 'settings'].includes(target)) await stopCurrent(); setPage(target); setSidebarOpen(false); setExportMenu(false); setQuery(''); setFilter('all') }
  const elapsed = session ? Math.max(0, (now - new Date(session.created_at).getTime()) / 1000) : 0
  const pageLabel = { dashboard: 'Workspace', live: 'Live capture', sessions: 'Lecture sessions', notes: 'Saved notes', settings: 'Settings' }[page]

  return <div className="app-shell">
    <aside className={`sidebar ${sidebarOpen ? 'is-open' : ''}`}>
      <a className="brand" href="#" onClick={e => { e.preventDefault(); navigate('dashboard') }}><span className="brand-mark"><BookOpen size={24} strokeWidth={1.7} /><i /></span><span>boardly<span className="brand-period">.</span><small>LESS CLICKING. MORE LEARNING.</small></span></a>
      <div className="workspace-label"><span className="workspace-avatar">W</span><div>My workspace<small>Local & private</small></div><ChevronDown size={14} /></div>
      <span className="nav-label">WORKSPACE</span>
      <nav>{[{ id: 'dashboard', label: 'Overview', icon: Grid2X2 }, { id: 'live', label: 'Live capture', icon: Video }, { id: 'sessions', label: 'Lecture sessions', icon: FolderOpen }, { id: 'notes', label: 'Saved notes', icon: BookOpen }, { id: 'settings', label: 'Settings', icon: Settings2 }].map(item => <button key={item.id} className={`nav-item ${page === item.id ? 'selected' : ''}`} onClick={() => navigate(item.id as Page)}><item.icon size={19} strokeWidth={1.8} /><span>{item.label}</span>{item.id === 'live' && active && <i className="live-nav-dot" />}{item.id === 'notes' && captures.length > 0 && <em>{captures.length}</em>}</button>)}</nav>
      <div className="sidebar-session-heading"><span className="nav-label">RECENT LECTURES</span><button aria-label="Create lecture session" className="icon-button" onClick={() => setNewSession(true)}><Plus size={15} /></button></div>
      <div className="recent-sessions">{sessions.slice(0, 4).map((s, index) => <button key={s.id} className={session?.id === s.id ? 'current' : ''} onClick={() => openSession(s.id)}><span className={`session-color color-${index % 3}`} /><span>{s.title}</span></button>)}{!sessions.length && <p>Your next lecture<br />belongs here.</p>}</div>
      <div className="sidebar-bottom"><div className="quiet-card"><span className="quiet-art"><Leaf size={27} strokeWidth={1.2} /><span>✧</span></span><strong>Be here. We’ll take notes.</strong><p>More attention for the moment.<br />A little help with the rest.</p><button onClick={() => setHelp(true)}>Meet your capture assistant<ArrowUpRight size={13} /></button></div>
        <button className="sidebar-help" onClick={() => setHelp(true)}><CircleHelp size={17} /><span>How it works</span><ArrowUpRight size={13} /></button>
        <div className="sidebar-footer"><span className="profile-avatar">YO</span><div>Your local workspace<small>No account needed</small></div><button className="icon-button" aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'} onClick={() => setDark(!dark)}>{dark ? <Sun size={17} /> : <Moon size={17} />}</button></div>
      </div>
    </aside>
    <main className="main-shell"><header className="topbar"><div className="breadcrumb"><button className="icon-button mobile-nav" aria-label="Toggle navigation" onClick={() => setSidebarOpen(!sidebarOpen)}><PanelLeftClose size={19} /></button><span>My workspace</span><span className="breadcrumb-slash">/</span><strong>{pageLabel}</strong></div><div className="topbar-right"><span className={`backend-indicator ${backend === 'connected' ? 'connected' : ''}`}><i />{backend === 'connected' ? 'Local system online' : backend === 'connecting' ? 'Connecting…' : 'Backend offline'}</span><button className="icon-button help-circle" aria-label="Open help" onClick={() => setHelp(true)}><CircleHelp size={18} /></button><span className="topbar-avatar">YO</span></div></header>
      <div className="page-content"><div className="page-heading"><div><div className="eyebrow heading-eyebrow"><span />YOUR IDEAS, IN GOOD HANDS</div><h1>{page === 'sessions' ? 'A home for every lecture.' : page === 'notes' ? 'Good ideas. All in one place.' : page === 'settings' ? 'Make yourself at home.' : 'Stay in the moment.'}</h1><p>{page === 'sessions' ? 'Pick up where you left off, or start something new.' : page === 'notes' ? 'The whiteboard moments you’ll want to come back to.' : page === 'settings' ? 'A few thoughtful settings for a clearer capture.' : 'We’ll keep the whiteboard. You keep the focus.'}</p></div><button className="button primary new-session-button" onClick={() => setNewSession(true)}><Plus size={17} />New session</button></div>

      {page === 'sessions' ? <><div className="section-title"><h2>Your lecture library <span className="count-pill">{sessions.length}</span></h2><button className="button subtle" onClick={() => refreshList().catch(error => onError(String(error)))}>Refresh<Activity size={14} /></button></div><div className="session-grid">{sessions.map(s => <button key={s.id} className="session-card" onClick={() => openSession(s.id)}><div className="session-card-art"><BookOpen size={35} strokeWidth={1.2} /><span>{String(s.capture_count).padStart(2, '0')}<small>CAPTURES</small></span></div><div className="session-card-details"><small>{s.course || 'LECTURE SESSION'}</small><h3>{s.title}</h3><p>{new Date(s.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}<ArrowUpRight size={17} /></p></div></button>)}<button className="session-card new-card" onClick={() => setNewSession(true)}><span><Plus size={23} /></span><strong>A new place for your ideas</strong><p>Create a lecture session</p></button></div></> : page === 'settings' ? session ? <SettingsPanel session={session} onSaved={value => { setSession(value); notify('Settings applied to the analysis pipeline.') }} onError={onError} /> : <EmptySession onCreate={() => setNewSession(true)} /> : <>

      <div className="session-strip"><div className="session-strip-icon"><BookOpen size={20} strokeWidth={1.6} /></div><div className="session-strip-title"><span>{session?.course || 'YOUR LECTURE SPACE'}</span><h2>{session?.title || 'Let’s make room for a new idea.'}</h2></div><div className="session-strip-meta"><span><Clock3 size={14} />{session ? new Date(session.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : 'Ready to begin'}</span>{session && <span className="elapsed-time">{duration(elapsed)}</span>}</div>{session && <button className="icon-button" aria-label="Edit lecture session" onClick={() => setEditSession(true)}><Ellipsis size={20} /></button>}<div className="export-container"><button className="button secondary" disabled={!session || exporting} onClick={() => setExportMenu(!exportMenu)}>{exporting ? <LoaderCircle className="spin" size={15} /> : <ArrowDownToLine size={15} />}Export notes<ChevronDown size={13} /></button>{exportMenu && <div className="dropdown-menu">{['pdf', 'zip', 'json', 'txt'].map(kind => <button key={kind} onClick={() => exportFile(kind)}>{kind === 'pdf' ? 'Lecture PDF' : kind === 'zip' ? 'All images (ZIP)' : kind === 'json' ? 'Session metadata' : 'Recognized text'}</button>)}</div>}</div></div>

      {page !== 'notes' && <><div className="stat-grid">{[{ label: 'CAPTURED MOMENTS', value: String(captures.length).padStart(2, '0'), icon: Camera, text: 'The ideas worth keeping', green: true }, { label: 'FRAMES ANALYZED', value: (stats.frames_analyzed || 0).toLocaleString(), icon: Scan, text: 'Quietly watching for changes' }, { label: 'DUPLICATES SKIPPED', value: (stats.duplicates_ignored || 0).toLocaleString(), icon: ImagePlus, text: 'Less clutter in your notes' }, { label: 'LAST CAPTURE', value: captures.length ? timeLabel(captures[captures.length - 1].timestamp) : '—', icon: Clock3, text: captures.length ? 'Saved safely on this device' : 'Your first capture is up next', time: true }].map(stat => <div key={stat.label} className={`stat-card ${stat.green ? 'mint' : ''}`}><div><span>{stat.label}</span><stat.icon size={17} strokeWidth={1.6} /></div><strong className={stat.time ? 'time-value' : ''}>{stat.value}</strong><small>{stat.green && <i />}{stat.text}</small></div>)}</div>

      <div className="capture-workspace"><section className="live-panel"><div className="live-panel-heading"><div className="camera-heading"><Video size={19} /><h2>Live workspace</h2><span className={`tag ${active ? 'green' : ''}`}>{active ? 'LIVE' : 'STANDBY'}</span></div><div className="segmented source-tabs"><button className={mode === 'camera' ? 'selected' : ''} onClick={async () => { if (mode !== 'camera') { await stopCurrent(); setMode('camera'); setAnalysis(null); setEditing(false) } }}><Camera size={13} />Camera</button><button className={mode === 'video' ? 'selected' : ''} onClick={async () => { if (mode !== 'video') { await stopCurrent(); setMode('video'); setAnalysis(null); setEditing(false) } }}><MonitorPlay size={13} />Video replay</button></div></div>
        <div ref={canvasContainer} className={`camera-stage ${sourceReady ? 'has-source' : ''} ${analysis?.capture ? 'just-captured' : ''}`}>
          <div className="camera-visual" style={{ aspectRatio: `${dimensions.width}/${dimensions.height}` }}>
            <video ref={camera.video} muted playsInline className={mode === 'camera' && camera.stream ? '' : 'hidden-video'} />
            {mode === 'video' && replay && <img className="replay-frame" src={`data:image/jpeg;base64,${replay.preview}`} alt="Uploaded lecture video frame" />}
            {sourceReady && <BoardOverlay points={editing ? points : calibrated ? session!.calibration!.points : []} editing={editing} onChange={setPoints} detector={analysis?.detector} />}
          </div>
          {!sourceReady && <div className="camera-placeholder"><div className="placeholder-grid" /><div className="placeholder-board"><span className="board-line" /><span className="board-line short" /><Sparkles size={25} strokeWidth={1.3} /><i /><b /></div><h3>{mode === 'camera' ? 'Big ideas. A little less effort.' : 'A lecture, on your own time.'}</h3><p>{mode === 'camera' ? 'Bring your whiteboard into focus.' : 'Upload a lecture video to capture its meaningful moments.'}<br />{mode === 'camera' ? 'We’ll take it from here.' : 'The same intelligence. No webcam needed.'}</p><button className="button lime" disabled={!session || camera.starting || uploading} onClick={() => mode === 'camera' ? camera.start(device || undefined) : uploadInput.current?.click()}>{camera.starting || uploading ? <LoaderCircle className="spin" size={16} /> : mode === 'camera' ? <Video size={16} /> : <Upload size={16} />}{!session ? 'Create a session to begin' : camera.starting ? 'Opening camera…' : uploading ? 'Uploading…' : mode === 'camera' ? 'Start camera' : 'Choose a video'}<ArrowRight size={15} /></button><span className="placeholder-privacy"><ShieldCheck size={12} />{mode === 'camera' ? 'Camera access only when you choose.' : 'MP4, MOV, AVI · Up to 500 MB · Stays local'}</span></div>}
          {sourceReady && <div className="camera-topline"><span className="camera-live-label"><i />{mode === 'camera' ? camera.paused ? 'ANALYSIS PAUSED' : camera.connection === 'connected' ? 'CAMERA LIVE' : camera.connection.toUpperCase() : `REPLAY · ${replay?.status.toUpperCase()}`}</span><span className="resolution-label">{dimensions.width} × {dimensions.height}</span></div>}
          {editing && <div className="calibration-instruction"><Scan size={15} />Drag the four corners to the edges of your whiteboard.</div>}
          {sourceReady && !editing && <div className="camera-bottomline"><span className={calibrated ? 'boundary-label' : 'uncalibrated-label'}><Scan size={13} />{calibrated ? 'Whiteboard calibrated' : 'Calibrate your whiteboard to begin'}</span><button className="stage-icon" aria-label="Fullscreen camera preview" onClick={() => canvasContainer.current?.requestFullscreen().catch(() => onError('Fullscreen is unavailable in this browser.'))}><Maximize2 size={16} /></button></div>}
        </div>
        {editing && <div className="calibration-actions"><span><Scan size={15} />Corners stay aligned at any preview size.</span><button className="button subtle" onClick={() => setEditing(false)}>Cancel</button><button className="button primary" onClick={saveCalibration}><Check size={15} />Confirm board</button></div>}
        {mode === 'video' && replay && <div className="replay-progress"><input aria-label="Replay position" type="range" min={0} max={replay.duration} step={0.2} value={replay.position} disabled={!busyReplay} onChange={e => replayControl('seek', Number(e.target.value))} /><span>{duration(replay.position)} / {duration(replay.duration)}</span></div>}
        <div className="camera-controls"><div className="button-row">{mode === 'camera' ? <><button className={`button ${camera.stream ? 'secondary' : 'primary'} compact`} disabled={!session || camera.starting} onClick={() => camera.stream ? camera.stop() : camera.start(device || undefined)}>{camera.starting ? <LoaderCircle className="spin" size={15} /> : camera.stream ? <Square size={13} /> : <Play size={14} />}{camera.stream ? 'Stop' : 'Start'}</button><button className="icon-button outlined" aria-label={camera.paused ? 'Resume analysis' : 'Pause analysis'} disabled={!camera.stream} onClick={camera.pause}>{camera.paused ? <Play size={16} /> : <Pause size={16} />}</button></> : <><button className="button primary compact" disabled={!replay || !calibrated || uploading} onClick={async () => { if (!session || !replay) return; if (busyReplay) { await replayControl(replay.status === 'paused' ? 'resume' : 'pause'); return } try { setReplay(await api<Replay>(`/sessions/${session.id}/replays/${replay.id}/start`, 'POST')) } catch (error) { onError(String(error)) } }}>{replay?.status === 'running' ? <Pause size={14} /> : <Play size={14} />}{replay?.status === 'running' ? 'Pause' : replay?.status === 'paused' ? 'Resume' : 'Start replay'}</button><button className="icon-button outlined" aria-label="Stop replay" disabled={!busyReplay} onClick={() => replayControl('cancel')}><Square size={13} /></button><button className="icon-button outlined" aria-label="Upload another video" disabled={busyReplay || uploading || !session} onClick={() => uploadInput.current?.click()}><Upload size={15} /></button></>}
          <span className="control-divider" /><button className="button subtle compact calibrate-button" disabled={!sourceReady || busyReplay} onClick={suggest}><Scan size={15} />{calibrated ? 'Recalibrate' : 'Calibrate board'}</button></div><button className="manual-button" disabled={!calibrated || !sourceReady || editing} onClick={() => mode === 'camera' ? camera.send('manual') : manualReplay()}><Camera size={17} /><span>Capture now</span></button></div>
        <div className="workspace-bottom"><div className="auto-capture-label"><Sparkles size={14} /><span>Auto-capture</span><label className="switch-control"><input aria-label="Automatic capture" type="checkbox" checked={session?.settings.auto_capture ?? true} disabled={!session} onChange={e => updateSettings({ auto_capture: e.target.checked })} /><i /></label><span className="auto-description">A little intelligence. A lot less clicking.</span></div>{mode === 'camera' ? <select aria-label="Select camera" className="camera-select" value={device} onChange={e => { setDevice(e.target.value); if (camera.stream) { setEditing(false); setAnalysis(null); camera.start(e.target.value || undefined) } }}><option value="">Default camera</option>{camera.devices.map((d, i) => <option key={d.deviceId || i} value={d.deviceId}>{d.label || `Camera ${i + 1}`}</option>)}</select> : <span className="source-caption">OpenCV video replay</span>}</div>
      </section><AnalysisPanel analysis={analysis} settings={session?.settings} active={!!active} log={log} /></div>
      </>}

      <section className={`gallery-section ${page === 'notes' ? 'full-gallery' : ''}`}><div className="section-title"><div><h2>{page === 'notes' ? 'Your saved moments' : 'Fresh from the whiteboard'}<span className="count-pill">{captures.length}</span></h2><p>{page === 'notes' ? 'Search titles, your notes, and available recognized text.' : 'Only the changes that matter. Always in order.'}</p></div>{page === 'notes' ? <div className="gallery-tools"><label className="search-box"><Search size={15} /><input aria-label="Search captures" placeholder="Find an idea…" value={query} onChange={e => setQuery(e.target.value)} /></label><label className="filter-select"><ListFilter size={15} /><select aria-label="Filter capture type" value={filter} onChange={e => setFilter(e.target.value)}><option value="all">All captures</option><option value="automatic">Automatic</option><option value="manual">Manual</option></select></label></div> : <button className="button subtle view-all" onClick={() => navigate('notes')}>View all captures<ArrowUpRight size={15} /></button>}</div>
        {shownCaptures.length ? <div className="capture-grid">{shownCaptures.map(capture => <button key={capture.id} className="capture-card" onClick={() => setSelectedCapture(capture.id)}><div className="capture-thumbnail"><img src={imageUrl(session!.id, capture.id, 'thumbnail')} alt={capture.name} loading="lazy" /><span className="capture-number">{String(capture.sequence).padStart(2, '0')}</span><span className="capture-open"><Maximize2 size={17} /></span></div><div className="capture-card-bottom"><strong>{capture.name}</strong><span className={`capture-kind ${capture.capture_type === 'automatic' ? 'auto' : ''}`}>{capture.capture_type === 'automatic' ? <Sparkles size={10} /> : <Camera size={10} />}{capture.capture_type === 'automatic' ? 'Auto' : 'Manual'}</span><span className="capture-timestamp"><Clock3 size={11} />{timeLabel(capture.timestamp)}</span><small>{capture.measurements.change?.change_type.replaceAll('_', ' ') || 'manual capture'}</small></div></button>)}</div> : <div className="gallery-empty"><span><ImagePlus size={24} strokeWidth={1.4} /></span><div><h3>{query || filter !== 'all' ? 'No captures match just yet.' : 'Your first capture is a good idea away.'}</h3><p>{query || filter !== 'all' ? 'Try a different search or capture type.' : 'Once your board is calibrated, meaningful changes will appear here automatically.'}</p></div>{!query && <span className="gallery-empty-doodle">✧</span>}</div>}
      </section>
      {session && <SessionAnalytics stats={stats} events={session.events} />}
      </>}

      <footer className="page-footer"><span><Leaf size={13} />Made for the way ideas happen.</span><span><ShieldCheck size={12} />On your device. In your control.<span className="footer-dot">·</span>AI Whiteboard Smart Capture</span></footer></div>
    </main>
    <input ref={uploadInput} className="sr-only" type="file" accept=".mp4,.mov,.avi" aria-label="Upload lecture video" onChange={async e => {
      const file = e.target.files?.[0]; e.target.value = ''; if (!file || !session) return
      if (file.size > 500 * 1024 * 1024) { onError('Choose a video smaller than 500 MB.'); return }
      setUploading(true)
      try { camera.stop(); const form = new FormData(); form.append('file', file); const value = await api<Replay>(`/sessions/${session.id}/replays`, 'POST', form); setReplay(value); setMode('video'); setAnalysis(null); setPoints(defaultCorners); setEditing(true); notify('Video ready. Position the four board corners, then confirm.') }
      catch (error) { onError(String(error)) }
      finally { setUploading(false) }
    }} />
    {toast && <div className={`toast ${toast.error ? 'error' : ''}`} role={toast.error ? 'alert' : 'status'}>{toast.error ? <CircleHelp size={18} /> : <Check size={18} />}<span>{toast.text}</span><button aria-label="Dismiss notification" onClick={() => setToast(null)}><X size={15} /></button></div>}
    {(newSession || editSession) && <SessionDialog existing={editSession ? session : null} onClose={() => { setNewSession(false); setEditSession(false) }} onSubmit={async values => {
      try {
        if (editSession && session) { setSession(await api<Session>(`/sessions/${session.id}`, 'PATCH', values)); await refreshList() }
        else { await stopCurrent(); const value = await api<Session>('/sessions', 'POST', values); setSession(value); localStorage.setItem('boardly-session', value.id); setAnalysis(null); setLog([]); setReplay(null); setEditing(false); setMode('camera'); setPage('dashboard'); await refreshList() }
        setNewSession(false); setEditSession(false); notify(editSession ? 'Lecture details updated.' : 'A fresh session. Let the ideas begin.')
      } catch (error) { onError(String(error)); throw error }
    }} />}
    {selectedCapture && session && captures.find(c => c.id === selectedCapture) && <CaptureModal capture={captures.find(c => c.id === selectedCapture)!} session={session} onClose={() => setSelectedCapture(null)} onNavigate={setSelectedCapture} onRefresh={refreshSession} onError={onError} />}
    {manualWarning && <div className="modal-backdrop"><section className="small-modal" role="dialog" aria-modal="true" aria-label="Review manual capture"><div className="dialog-icon amber"><Camera size={25} /></div><h2>A quick check before saving.</h2><p>{manualWarning.reason}</p>{manualWarning.board_preview && <img className="warning-preview" src={`data:image/jpeg;base64,${manualWarning.board_preview}`} alt="Manual capture awaiting confirmation" />}<p className="micro-copy">You can save this image anyway. It will be labeled as a manual capture.</p><div className="dialog-actions"><button className="button secondary" onClick={() => { if (mode === 'camera') camera.confirmManual(false); setManualWarning(null) }}>Cancel</button><button className="button primary" onClick={() => { if (mode === 'camera') camera.confirmManual(true); else manualReplay(true); setManualWarning(null) }}>Save anyway</button></div></section></div>}
    {help && <div className="modal-backdrop" onClick={() => setHelp(false)}><section className="help-modal" role="dialog" aria-modal="true" aria-label="How Boardly works" onClick={e => e.stopPropagation()}><button className="icon-button modal-close" aria-label="Close help" onClick={() => setHelp(false)}><X size={20} /></button><div className="dialog-icon"><Sparkles size={26} /></div><span className="eyebrow">A LITTLE HELP WITH THE WHITEBOARD</span><h2>More present.<br />Less preoccupied.</h2><p>Boardly watches your whiteboard for meaningful changes and keeps a clear picture when the writing settles.</p><ol className="help-steps"><li><span>01</span><div><strong>Make a space for your lecture</strong><p>Create a session, then start a camera or upload a video.</p></div></li><li><span>02</span><div><strong>Show us the board</strong><p>Drag the four corners to the board’s edges and confirm. Keep the camera still.</p></div></li><li><span>03</span><div><strong>Let the ideas happen</strong><p>Write, step away, and wait for a stable image. Review your captures and export your notes.</p></div></li></ol><div className="help-note"><ShieldCheck size={20} /><p>Everything stays on this device. Person detection requires the local YOLO11n weights. Without them, motion-only capture cannot reliably identify a still obstruction. OCR is optional and may misread handwriting.</p></div><button className="button primary full" onClick={() => setHelp(false)}>Make room for the ideas<ArrowRight size={16} /></button></section></div>}
  </div>
}

function EmptySession({ onCreate }: { onCreate: () => void }) {
  return <div className="empty-session"><BookOpen size={38} strokeWidth={1.2} /><h2>Every lecture starts somewhere.</h2><p>Create a session to give your captures a home.</p><button className="button primary" onClick={onCreate}><Plus size={16} />Create your first session</button></div>
}

function SessionDialog({ existing, onClose, onSubmit }: { existing: Session | null; onClose: () => void; onSubmit: (values: { title: string; course: string; description: string }) => Promise<void> }) {
  const [title, setTitle] = useState(existing?.title || '')
  const [course, setCourse] = useState(existing?.course || '')
  const [description, setDescription] = useState(existing?.description || '')
  const [saving, setSaving] = useState(false)
  return <div className="modal-backdrop" onClick={onClose}><section className="small-modal" role="dialog" aria-modal="true" aria-label={existing ? 'Edit session' : 'New lecture session'} onClick={e => e.stopPropagation()}><button className="icon-button modal-close" aria-label="Close session dialog" onClick={onClose}><X size={20} /></button><div className="dialog-icon"><BookOpen size={25} /></div><span className="eyebrow">A PLACE FOR YOUR NEXT BIG IDEA</span><h2>{existing ? 'Your lecture, your way.' : 'Something worth keeping.'}</h2><p>{existing ? 'Update the details of your lecture session.' : 'Give your lecture a name. We’ll take care of the whiteboard.'}</p><form onSubmit={async e => { e.preventDefault(); if (!title.trim()) return; setSaving(true); try { await onSubmit({ title: title.trim(), course: course.trim(), description }) } catch { /* The parent displays the request error. */ } finally { setSaving(false) } }}><label className="form-field">Lecture title<input autoFocus required maxLength={200} placeholder="e.g. Introduction to Linear Algebra" value={title} onChange={e => setTitle(e.target.value)} /></label><label className="form-field">Course <span>optional</span><input maxLength={200} placeholder="e.g. Mathematics · Week 04" value={course} onChange={e => setCourse(e.target.value)} /></label><label className="form-field">A little context <span>optional</span><textarea rows={3} maxLength={5000} placeholder="What are we exploring today?" value={description} onChange={e => setDescription(e.target.value)} /></label><div className="dialog-actions"><button type="button" className="button secondary" onClick={onClose}>Cancel</button><button className="button primary" disabled={saving || !title.trim()}>{saving ? <LoaderCircle className="spin" size={16} /> : <ArrowRight size={16} />}{existing ? 'Save details' : 'Create session'}</button></div></form></section></div>
}


function SessionAnalytics({ stats, events }: { stats: Record<string, number>; events: Session['events'] }) {
  return <details className="session-analytics"><summary><Activity size={14} /><span>Behind the captures</span><small>Session statistics & board events</small><ChevronDown size={14} /></summary><div className="analytics-values">{[
    ['Meaningful changes', 'meaningful_changes'], ['Manual captures', 'manual_captures'],
    ['Blur rejected', 'blur_rejected'], ['Other quality rejections', 'quality_rejected'],
    ['Motion delayed', 'motion_delayed'], ['Obstruction delayed', 'obstruction_delayed'],
    ['Insignificant / empty ignored', 'insignificant_ignored'], ['Duplicate states ignored', 'duplicates_ignored'],
  ].map(([label, key]) => <div key={key}><span>{label}</span><strong>{(stats[key] || 0).toLocaleString()}</strong></div>)}</div><p>Delayed frames are still waiting for a better moment. They are counted separately from quality rejections.</p>{events.length > 0 && <div className="board-event-list">{events.slice(-10).reverse().map((event, i) => <span key={i}><Check size={12} />{event.event.replaceAll('_', ' ')}<time>{timeLabel(event.timestamp)}</time></span>)}</div>}</details>
}
