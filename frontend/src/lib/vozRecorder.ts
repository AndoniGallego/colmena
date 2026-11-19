import { ApiError } from '../api/types'
import {
  MAX_SECONDS,
  MIN_BYTES,
  MIN_SECONDS,
  WARN_AT,
  kindFromMediaError,
  kindFromStatus,
  pickMimeType,
  vozError,
  type VozError,
} from './voz'

export type VozPhase = 'idle' | 'requesting' | 'recording' | 'transcribing' | 'error'

export interface VozSnapshot {
  phase: VozPhase
  /** Segundos grabados (mientras graba) o que duró la grabación (al transcribir). */
  elapsed: number
  warn: boolean
  /** El modelo todavía no está en memoria: la primera vez tarda unos segundos más. */
  preparing: boolean
  error: VozError | null
}

export interface LevelMeter {
  analyser: AnalyserNode
  close(): void
}

export interface RecorderLike {
  state: string
  mimeType: string
  ondataavailable: ((e: { data: Blob }) => void) | null
  onstop: (() => void) | null
  onerror: ((e: unknown) => void) | null
  start(timeslice?: number): void
  stop(): void
}

export interface VozDeps {
  getUserMedia(): Promise<MediaStream>
  createRecorder?: (stream: MediaStream, mimeType: string) => RecorderLike
  isTypeSupported(type: string): boolean
  recorderSupported(): boolean
  createMeter?: (stream: MediaStream) => LevelMeter | null
  transcribe(blob: Blob, signal: AbortSignal): Promise<{ texto: string }>
  isModelLoaded(): boolean | null
  onTranscribed?: () => void
  now(): number
  ios?: boolean
  tickMs?: number
}

export interface VozHooks {
  onState(s: VozSnapshot): void
  onText(text: string): void
  onMeter?(m: LevelMeter | null): void
}

/** Máquina de estados del dictado: pedir mic → grabar → transcribir → entregar el texto. Nunca envía nada. */
export function createVozRecorder(deps: VozDeps, hooks: VozHooks) {
  let phase: VozPhase = 'idle'
  let error: VozError | null = null
  let elapsed = 0
  let warn = false
  let preparing = false
  let stream: MediaStream | null = null
  let recorder: RecorderLike | null = null
  let meter: LevelMeter | null = null
  let chunks: Blob[] = []
  let startedAt = 0
  let timer: ReturnType<typeof setInterval> | undefined
  let token = 0
  let abort: AbortController | null = null
  let discard = false

  const emit = () => hooks.onState({ phase, elapsed, warn, preparing, error })

  function set(next: VozPhase, err: VozError | null = null) {
    phase = next
    error = err
    emit()
  }

  function fail(kind: Parameters<typeof vozError>[0]) {
    set('error', vozError(kind, { ios: deps.ios }))
  }

  function release() {
    clearInterval(timer)
    timer = undefined
    stream?.getTracks().forEach((t) => t.stop())
    stream = null
    meter?.close()
    meter = null
    hooks.onMeter?.(null)
  }

  function tick() {
    elapsed = Math.min((deps.now() - startedAt) / 1000, MAX_SECONDS)
    warn = elapsed >= WARN_AT
    emit()
    if (elapsed >= MAX_SECONDS) stop()
  }

  async function start() {
    if (phase !== 'idle' && phase !== 'error') return
    const mine = ++token
    discard = false
    elapsed = 0
    warn = false
    preparing = false
    if (!deps.recorderSupported()) return fail('no-soportado')
    set('requesting')
    let granted: MediaStream
    try {
      granted = await deps.getUserMedia()
    } catch (e) {
      if (mine !== token) return
      return fail(kindFromMediaError((e as { name?: string })?.name ?? ''))
    }
    // Un pedido viejo que llega tarde solo suelta su propio micrófono: no pisa ni corta una grabación nueva.
    if (mine !== token) {
      granted.getTracks().forEach((t) => t.stop())
      return
    }
    stream = granted
    try {
      const mime = pickMimeType(deps.isTypeSupported)
      recorder = deps.createRecorder!(stream, mime)
    } catch {
      release()
      return fail('no-soportado')
    }
    chunks = []
    const rec = recorder
    rec.ondataavailable = (e) => e.data && e.data.size > 0 && chunks.push(e.data)
    rec.onstop = () => void finish(mine, rec)
    rec.onerror = () => {
      if (mine !== token) return
      discard = true
      release()
      fail('server')
    }
    // Si el sistema corta el micrófono (llamada, otra app), lo grabado hasta ahí se transcribe igual.
    stream.getAudioTracks().forEach((t) => t.addEventListener('ended', () => stop()))
    try {
      meter = deps.createMeter?.(stream) ?? null
    } catch {
      meter = null
    }
    hooks.onMeter?.(meter)
    startedAt = deps.now()
    rec.start(250)
    set('recording')
    timer = setInterval(tick, deps.tickMs ?? 200)
  }

  function stop() {
    if (phase !== 'recording' || !recorder) return
    elapsed = Math.min((deps.now() - startedAt) / 1000, MAX_SECONDS)
    clearInterval(timer)
    timer = undefined
    preparing = deps.isModelLoaded() === false
    abort = new AbortController()
    set('transcribing')
    if (recorder.state !== 'inactive') recorder.stop()
    else void finish(token, recorder)
  }

  async function finish(mine: number, rec: RecorderLike) {
    if (mine !== token || discard) return
    const type = rec.mimeType || pickMimeType(deps.isTypeSupported) || 'audio/webm'
    const blob = new Blob(chunks, { type })
    chunks = []
    release()
    if (elapsed < MIN_SECONDS || blob.size < MIN_BYTES) {
      abort = null
      return fail('corto')
    }
    const controller = abort ?? new AbortController()
    try {
      const { texto } = await deps.transcribe(blob, controller.signal)
      if (mine !== token) return
      preparing = false
      deps.onTranscribed?.()
      if (!texto.trim()) return fail('silencio')
      set('idle')
      hooks.onText(texto.trim())
    } catch (e) {
      if (mine !== token || (e instanceof DOMException && e.name === 'AbortError')) return
      preparing = false
      fail(e instanceof ApiError ? kindFromStatus(e.status) : 'red')
    } finally {
      if (mine === token) abort = null
    }
  }

  /** Descarta todo: lo grabado, la transcripción en vuelo y el micrófono. */
  function cancel() {
    token++
    discard = true
    abort?.abort()
    abort = null
    if (recorder && recorder.state !== 'inactive') {
      recorder.onstop = null
      try {
        recorder.stop()
      } catch {
        /* ya estaba parado */
      }
    }
    recorder = null
    chunks = []
    release()
    preparing = false
    elapsed = 0
    warn = false
    if (phase !== 'idle') set('idle')
  }

  function dismiss() {
    if (phase === 'error') set('idle')
  }

  return { start, stop, cancel, dismiss, get phase() { return phase } }
}

export type VozRecorder = ReturnType<typeof createVozRecorder>
