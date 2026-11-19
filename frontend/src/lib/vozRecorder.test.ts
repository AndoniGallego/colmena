import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/types'
import { createVozRecorder, type RecorderLike, type VozDeps, type VozSnapshot } from './vozRecorder'

class FakeRecorder implements RecorderLike {
  static last: FakeRecorder
  state = 'inactive'
  mimeType: string
  ondataavailable: ((e: { data: Blob }) => void) | null = null
  onstop: (() => void) | null = null
  onerror: ((e: unknown) => void) | null = null
  constructor(public stream: MediaStream, mime: string) {
    this.mimeType = mime || 'audio/webm'
    FakeRecorder.last = this
  }
  start() {
    this.state = 'recording'
  }
  stop() {
    this.state = 'inactive'
    queueMicrotask(() => {
      this.ondataavailable?.({ data: new Blob([new Uint8Array(4000)]) })
      this.onstop?.()
    })
  }
}

function fakeStream() {
  const track = { stop: vi.fn(), addEventListener: vi.fn() }
  return { track, stream: { getTracks: () => [track], getAudioTracks: () => [track] } as unknown as MediaStream }
}

const flush = async () => {
  for (let i = 0; i < 5; i++) await Promise.resolve()
}

let clock = 0
let streamInfo: ReturnType<typeof fakeStream>
let states: VozSnapshot[]
let texts: string[]
let meterClosed: number
let deps: VozDeps

function build(over: Partial<VozDeps> = {}) {
  deps = {
    getUserMedia: async () => streamInfo.stream,
    createRecorder: (s, m) => new FakeRecorder(s, m) as RecorderLike,
    isTypeSupported: (t) => t === 'audio/webm;codecs=opus',
    recorderSupported: () => true,
    createMeter: () => ({ analyser: {} as AnalyserNode, close: () => meterClosed++ }),
    transcribe: vi.fn(async () => ({ texto: 'hola mundo' })),
    isModelLoaded: () => true,
    now: () => clock,
    ...over,
  }
  return createVozRecorder(deps, { onState: (s) => states.push(s), onText: (t) => texts.push(t) })
}
const last = () => states[states.length - 1]

beforeEach(() => {
  vi.useFakeTimers()
  clock = 0
  streamInfo = fakeStream()
  states = []
  texts = []
  meterClosed = 0
})
afterEach(() => vi.useRealTimers())

describe('máquina de estados del grabador', () => {
  it('camino feliz: pide mic, graba, transcribe y entrega el texto sin enviar', async () => {
    const r = build()
    await r.start()
    expect(last().phase).toBe('recording')
    clock = 3000
    vi.advanceTimersByTime(400)
    expect(last().elapsed).toBeCloseTo(3, 0)
    r.stop()
    expect(last().phase).toBe('transcribing')
    await flush()
    expect(texts).toEqual(['hola mundo'])
    expect(last().phase).toBe('idle')
    expect(streamInfo.track.stop).toHaveBeenCalled()
    expect(meterClosed).toBe(1)
    const blob = (deps.transcribe as any).mock.calls[0][0] as Blob
    expect(blob.type).toBe('audio/webm;codecs=opus')
  })

  it('elige el mimeType soportado y se lo pasa al MediaRecorder', async () => {
    const seen: string[] = []
    const r = build({ createRecorder: (s, m) => (seen.push(m), new FakeRecorder(s, m) as RecorderLike), isTypeSupported: (t) => t === 'audio/mp4' })
    await r.start()
    expect(seen).toEqual(['audio/mp4'])
  })

  it('permiso denegado: error claro y sin mic abierto', async () => {
    const r = build({ getUserMedia: async () => Promise.reject(Object.assign(new Error('x'), { name: 'NotAllowedError' })) })
    await r.start()
    expect(last().phase).toBe('error')
    expect(last().error?.kind).toBe('permiso')
  })

  it('sin micrófono y navegador sin MediaRecorder', async () => {
    await build({ getUserMedia: async () => Promise.reject(Object.assign(new Error('x'), { name: 'NotFoundError' })) }).start()
    expect(last().error?.kind).toBe('sin-microfono')
    states = []
    await build({ recorderSupported: () => false }).start()
    expect(last().error?.kind).toBe('no-soportado')
  })

  it('audio demasiado corto no llega al server', async () => {
    const r = build()
    await r.start()
    clock = 100
    r.stop()
    await flush()
    expect(last().error?.kind).toBe('corto')
    expect(deps.transcribe).not.toHaveBeenCalled()
    expect(streamInfo.track.stop).toHaveBeenCalled()
  })

  it('texto vacío = "No se escuchó nada" y no inserta', async () => {
    const r = build({ transcribe: async () => ({ texto: '  ' }) })
    await r.start()
    clock = 2000
    r.stop()
    await flush()
    expect(last().error?.kind).toBe('silencio')
    expect(texts).toEqual([])
  })

  it('errores del server: 409 ocupada, 500, red y 503', async () => {
    for (const [err, kind] of [
      [new ApiError(409, 'x'), 'ocupada'],
      [new ApiError(500, 'x'), 'server'],
      [new ApiError(503, 'x'), 'modelo'],
      [new TypeError('fetch'), 'red'],
    ] as const) {
      states = []
      const r = build({ transcribe: async () => Promise.reject(err) })
      await r.start()
      clock += 2000
      r.stop()
      await flush()
      expect(last().error?.kind).toBe(kind)
      expect(texts).toEqual([])
    }
  })

  it('primera vez: avisa que prepara el modelo', async () => {
    const r = build({ isModelLoaded: () => false })
    await r.start()
    clock = 2000
    r.stop()
    expect(last()).toMatchObject({ phase: 'transcribing', preparing: true })
    await flush()
    expect(last().preparing).toBe(false)
  })

  it('avisa a los 110 s y corta solo a los 120 s', async () => {
    const r = build()
    await r.start()
    clock = 109_000
    vi.advanceTimersByTime(250)
    expect(last().warn).toBe(false)
    clock = 111_000
    vi.advanceTimersByTime(250)
    expect(last().warn).toBe(true)
    clock = 121_000
    vi.advanceTimersByTime(250)
    expect(last().phase).toBe('transcribing')
    expect(last().elapsed).toBe(120)
    await flush()
    expect(texts).toHaveLength(1)
  })

  it('cancelar mientras graba suelta el mic y no transcribe', async () => {
    const r = build()
    await r.start()
    clock = 3000
    r.cancel()
    await flush()
    expect(last().phase).toBe('idle')
    expect(streamInfo.track.stop).toHaveBeenCalled()
    expect(meterClosed).toBe(1)
    expect(deps.transcribe).not.toHaveBeenCalled()
    expect(texts).toEqual([])
  })

  it('cancelar mientras transcribe aborta y descarta el texto', async () => {
    let signal!: AbortSignal
    let finish!: (v: { texto: string }) => void
    const r = build({
      transcribe: (_b, s) => ((signal = s), new Promise((res) => (finish = res))),
    })
    await r.start()
    clock = 3000
    r.stop()
    await flush()
    r.cancel()
    expect(signal.aborted).toBe(true)
    finish({ texto: 'tarde' })
    await flush()
    expect(texts).toEqual([])
    expect(last().phase).toBe('idle')
  })

  it('cancelar mientras espera el permiso suelta el stream cuando llega', async () => {
    let grant!: (s: MediaStream) => void
    const r = build({ getUserMedia: () => new Promise((res) => (grant = res)) })
    const started = r.start()
    expect(last().phase).toBe('requesting')
    r.cancel()
    grant(streamInfo.stream)
    await started
    expect(streamInfo.track.stop).toHaveBeenCalled()
    expect(last().phase).toBe('idle')
  })

  it('un permiso viejo que llega tarde no corta ni pisa la grabación nueva', async () => {
    const old = fakeStream()
    let grantOld!: (s: MediaStream) => void
    let calls = 0
    const r = build({
      getUserMedia: () => (++calls === 1 ? new Promise((res) => (grantOld = res)) : Promise.resolve(streamInfo.stream)),
    })
    const first = r.start()
    r.cancel()
    await r.start()
    expect(last().phase).toBe('recording')
    grantOld(old.stream)
    await first
    expect(old.track.stop).toHaveBeenCalled()
    expect(streamInfo.track.stop).not.toHaveBeenCalled()
    expect(meterClosed).toBe(0)
    expect(last().phase).toBe('recording')
    r.cancel()
    expect(streamInfo.track.stop).toHaveBeenCalled()
  })

  it('no arranca dos veces y permite reintentar tras un error', async () => {
    const r = build({ transcribe: async () => Promise.reject(new ApiError(409, 'x')) })
    await r.start()
    await r.start()
    expect(states.filter((s) => s.phase === 'recording')).toHaveLength(1)
    clock = 2000
    r.stop()
    await flush()
    expect(last().phase).toBe('error')
    await r.start()
    expect(last().phase).toBe('recording')
    r.cancel()
  })

  it('si el sistema corta el micrófono se transcribe lo grabado', async () => {
    const r = build()
    await r.start()
    const handler = streamInfo.track.addEventListener.mock.calls.find((c: any[]) => c[0] === 'ended')![1]
    clock = 2500
    handler()
    await flush()
    expect(texts).toEqual(['hola mundo'])
  })
})
