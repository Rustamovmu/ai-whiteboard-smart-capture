import { useCallback, useEffect, useRef, useState } from 'react'
import type { Analysis } from './types'

type Packet = { type: string; frame_id: string; source_id: string; width: number; height: number; jpeg: string; force?: boolean }

export function useCamera(sessionId: string | undefined, fps: number, onAnalysis: (value: Analysis) => void, onError: (message: string) => void, suspended = false) {
  const video = useRef<HTMLVideoElement>(null)
  const media = useRef<MediaStream | null>(null)
  const socket = useRef<WebSocket | null>(null)
  const generation = useRef(0)
  const busy = useRef(false)
  const busySince = useRef(0)
  const resetNext = useRef(false)
  const queuedCommand = useRef<'manual' | 'suggest' | null>(null)
  const sendRef = useRef<(type: 'frame' | 'manual' | 'suggest') => void>(() => {})
  const pausedRef = useRef(false)
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pending = useRef<Packet | null>(null)
  const sent = useRef<Packet | null>(null)
  const source = useRef('')
  const callbacks = useRef({ onAnalysis, onError, sessionId, fps, suspended })
  callbacks.current = { onAnalysis, onError, sessionId, fps, suspended }
  const [stream, setStream] = useState<MediaStream | null>(null)
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([])
  const [connection, setConnection] = useState('offline')
  const [starting, setStarting] = useState(false)
  const [paused, setPaused] = useState(false)
  const [dimensions, setDimensions] = useState({ width: 1280, height: 720 })
  const [sourceId, setSourceId] = useState('')
  useEffect(() => { resetNext.current = true }, [suspended])

  const stop = useCallback(() => {
    generation.current++
    if (retryTimer.current) clearTimeout(retryTimer.current)
    if (socket.current) { socket.current.onclose = null; socket.current.close(); socket.current = null }
    media.current?.getTracks().forEach(track => { track.onended = null; track.stop() })
    media.current = null
    if (video.current) video.current.srcObject = null
    busy.current = false
    queuedCommand.current = null
    pending.current = null
    pausedRef.current = false
    setStream(null)
    setConnection('offline')
    setStarting(false)
    setPaused(false)
  }, [])

  const refreshDevices = useCallback(async () => {
    if (!navigator.mediaDevices) return
    try { setDevices((await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === 'videoinput')) }
    catch { /* Device labels remain unavailable until permission is granted. */ }
  }, [])

  useEffect(() => {
    refreshDevices()
    navigator.mediaDevices?.addEventListener('devicechange', refreshDevices)
    return () => navigator.mediaDevices?.removeEventListener('devicechange', refreshDevices)
  }, [refreshDevices])

  useEffect(() => { return stop }, [sessionId, stop])

  useEffect(() => {
    const element = video.current
    if (!element || !stream) return
    element.srcObject = stream
    element.onloadedmetadata = () => {
      setDimensions({ width: element.videoWidth, height: element.videoHeight })
      element.play().catch(() => callbacks.current.onError('The camera preview could not start. Try starting the camera again.'))
    }
    return () => { element.onloadedmetadata = null }
  }, [stream])

  const start = useCallback(async (deviceId?: string) => {
    if (!callbacks.current.sessionId) { callbacks.current.onError('Create or open a lecture session first.'); return }
    if (!navigator.mediaDevices?.getUserMedia) { callbacks.current.onError('Camera access requires localhost and a supported browser.'); return }
    stop()
    const token = generation.current
    setStarting(true)
    try {
      const local = await navigator.mediaDevices.getUserMedia({ audio: false, video: {
        width: { ideal: 1280 }, height: { ideal: 720 }, ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
      } })
      if (generation.current !== token) { local.getTracks().forEach(t => t.stop()); return }
      media.current = local
      local.getVideoTracks().forEach(track => { track.onended = () => { stop(); callbacks.current.onError('Camera disconnected. Reconnect it and start again.') } })
      const track = local.getVideoTracks()[0]
      const id = `camera:${track.getSettings().deviceId || track.label}`
      source.current = id
      setSourceId(id)
      setStream(local)
      setStarting(false)
      refreshDevices()
      let retries = 0
      const connect = () => {
        if (generation.current !== token) return
        setConnection(retries ? 'reconnecting' : 'connecting')
        const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/sessions/${callbacks.current.sessionId}`)
        socket.current = ws
        ws.onmessage = event => {
          if (generation.current !== token) return
          try {
            const value = JSON.parse(event.data)
            busy.current = false
            if (value.type === 'connected') { setConnection('connected'); retries = 0; return }
            if (value.type === 'reset') {
              if (queuedCommand.current && !pending.current) {
                const command = queuedCommand.current
                queuedCommand.current = null
                sendRef.current(command)
              }
              return
            }
            if (value.type === 'error') { callbacks.current.onError(value.message); return }
            if (value.decision === 'confirm') pending.current = sent.current
            callbacks.current.onAnalysis(value)
            if (queuedCommand.current && !pending.current) {
              const command = queuedCommand.current
              queuedCommand.current = null
              sendRef.current(command)
            }
          } catch { busy.current = false; callbacks.current.onError('Received an invalid analysis response.') }
        }
        ws.onerror = () => setConnection('reconnecting')
        ws.onclose = () => {
          busy.current = false
          if (generation.current !== token) return
          if (++retries > 6) { setConnection('disconnected'); callbacks.current.onError('Backend connection lost. Check the server, then restart the camera.'); return }
          setConnection('reconnecting')
          retryTimer.current = setTimeout(connect, Math.min(8000, 500 * 2 ** retries))
        }
      }
      connect()
    } catch (error) {
      if (generation.current !== token) return
      setStarting(false)
      const name = error instanceof DOMException ? error.name : ''
      callbacks.current.onError(name === 'NotAllowedError' ? 'Camera permission was denied. Allow camera access in your browser and macOS Privacy & Security settings.' :
        name === 'NotFoundError' ? 'No camera found. Connect a webcam or use Video replay.' :
        name === 'NotReadableError' ? 'The camera is busy. Close other camera apps and try again.' : String(error))
    }
  }, [stop, refreshDevices])

  const send = useCallback((type: 'frame' | 'manual' | 'suggest' = 'frame') => {
    const element = video.current
    if (!element || !element.videoWidth || socket.current?.readyState !== WebSocket.OPEN) {
      if (type !== 'frame') callbacks.current.onError('Start the camera and connect to the backend first.')
      return
    }
    if (busy.current) {
      if (Date.now() - busySince.current > 20000) {
        busy.current = false
        socket.current.close()
        callbacks.current.onError('Analysis timed out. Reconnecting to the backend.')
        return
      }
      if (type !== 'frame') queuedCommand.current = type
      return
    }
    if (pending.current) { if (type !== 'frame') callbacks.current.onError('Review the pending manual capture first.'); return }
    if (type === 'frame' && (pausedRef.current || callbacks.current.suspended)) return
    busy.current = true
    busySince.current = Date.now()
    if (resetNext.current) {
      resetNext.current = false
      if (type !== 'frame') queuedCommand.current = type
      socket.current.send(JSON.stringify({ type: 'reset' }))
      return
    }
    const token = generation.current
    const transport = socket.current
    const canvas = document.createElement('canvas')
    const scale = Math.min(1, 1280 / element.videoWidth)
    canvas.width = Math.round(element.videoWidth * scale)
    canvas.height = Math.round(element.videoHeight * scale)
    canvas.getContext('2d')!.drawImage(element, 0, 0, canvas.width, canvas.height)
    canvas.toBlob(async blob => {
      try {
        if (!blob || generation.current !== token || socket.current !== transport || socket.current?.readyState !== WebSocket.OPEN) { busy.current = false; return }
        const data = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader()
          reader.onload = () => resolve((reader.result as string).split(',')[1])
          reader.onerror = reject
          reader.readAsDataURL(blob)
        })
        if (generation.current !== token || socket.current !== transport || socket.current?.readyState !== WebSocket.OPEN) { busy.current = false; return }
        const packet = { type, frame_id: crypto.randomUUID(), source_id: source.current, width: canvas.width, height: canvas.height, jpeg: data }
        sent.current = packet
        socket.current.send(JSON.stringify(packet))
      } catch { busy.current = false; callbacks.current.onError('Unable to send the camera frame.') }
    }, 'image/jpeg', 0.82)
  }, [])
  sendRef.current = send

  useEffect(() => {
    if (!stream || connection !== 'connected') return
    const timer = setInterval(() => send(), 1000 / fps)
    return () => clearInterval(timer)
  }, [stream, connection, fps, send])

  const pause = useCallback(() => {
    pausedRef.current = !pausedRef.current
    setPaused(pausedRef.current)
    resetNext.current = true
    if (socket.current?.readyState === WebSocket.OPEN && !busy.current) {
      busy.current = true
      busySince.current = Date.now()
      resetNext.current = false
      socket.current.send(JSON.stringify({ type: 'reset' }))
    }
  }, [])

  const confirmManual = useCallback((save: boolean) => {
    const request = pending.current
    pending.current = null
    if (save && request && socket.current?.readyState === WebSocket.OPEN) {
      busy.current = true
      busySince.current = Date.now()
      socket.current.send(JSON.stringify({ ...request, force: true }))
    } else if (save) callbacks.current.onError('The connection changed before saving. Reconnect and take a new manual capture.')
  }, [])

  return { video, stream, devices, dimensions, sourceId, connection, starting, paused, start, stop, pause, send, confirmManual }
}
