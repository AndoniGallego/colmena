import { computed, nextTick, onBeforeUnmount, ref, shallowRef, watch, type Ref } from 'vue'
import type { VozEstado } from '../api/types'
import { createVozRecorder, type LevelMeter, type VozSnapshot } from '../lib/vozRecorder'
import { insertAtCursor, isIOS, isVozShortcut } from '../lib/voz'
import { getVozEstado, transcribirVoz } from './app'

export const vozEstado = ref<VozEstado | null>(null)

const canRecord = () =>
  typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined'

let pending: Promise<void> | null = null
export function loadVozEstado(force = false): Promise<void> {
  if (pending && !force) return pending
  pending = getVozEstado()
    .then((e) => {
      vozEstado.value = e
    })
    .catch(() => {
      // Backend viejo o sin la ruta: el botón no aparece y se reintenta en el próximo montaje.
      vozEstado.value = null
      pending = null
    })
  return pending
}

function createMeter(stream: MediaStream): LevelMeter | null {
  const Ctx: typeof AudioContext | undefined = window.AudioContext ?? (window as any).webkitAudioContext
  if (!Ctx) return null
  const ctx = new Ctx()
  const analyser = ctx.createAnalyser()
  analyser.fftSize = 512
  analyser.smoothingTimeConstant = 0.55
  ctx.createMediaStreamSource(stream).connect(analyser)
  void ctx.resume().catch(() => undefined)
  return { analyser, close: () => void ctx.close().catch(() => undefined) }
}

const idleSnap = (): VozSnapshot => ({ phase: 'idle', elapsed: 0, warn: false, preparing: false, error: null })

export function useVoz(onText: (text: string) => void) {
  const snap = ref<VozSnapshot>(idleSnap())
  const meter = shallowRef<LevelMeter | null>(null)
  const rec = createVozRecorder(
    {
      getUserMedia: () => navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } }),
      createRecorder: (stream, mime) => new MediaRecorder(stream, mime ? { mimeType: mime } : undefined) as any,
      isTypeSupported: (t) => typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(t),
      recorderSupported: canRecord,
      createMeter,
      transcribe: (blob, signal) => transcribirVoz(blob, signal),
      isModelLoaded: () => (vozEstado.value ? vozEstado.value.cargado : null),
      onTranscribed: () => {
        if (vozEstado.value) vozEstado.value = { ...vozEstado.value, cargado: true }
      },
      now: () => performance.now(),
      ios: typeof navigator !== 'undefined' && isIOS(navigator.userAgent, navigator.platform, navigator.maxTouchPoints),
    },
    { onState: (s) => (snap.value = s), onText, onMeter: (m) => (meter.value = m) },
  )

  const stopOnHide = () => rec.cancel()
  window.addEventListener('pagehide', stopOnHide)
  onBeforeUnmount(() => {
    window.removeEventListener('pagehide', stopOnHide)
    rec.cancel()
  })
  void loadVozEstado()

  const available = computed(() => canRecord() && vozEstado.value?.habilitada === true)
  const busy = computed(() => snap.value.phase === 'requesting' || snap.value.phase === 'recording' || snap.value.phase === 'transcribing')

  function start() {
    void loadVozEstado(true)
    return rec.start()
  }
  function toggle() {
    const p = snap.value.phase
    if (p === 'recording') rec.stop()
    else if (p === 'idle' || p === 'error') void start()
  }

  return { snap, meter, available, busy, start, stop: rec.stop, toggle, cancel: rec.cancel, dismiss: rec.dismiss }
}

export type Voz = ReturnType<typeof useVoz>

/** Conecta el dictado a un composer: el texto entra en el cursor, queda editable y enfocado; nunca se envía. */
export function useVozInput(ta: Ref<HTMLTextAreaElement | null>, text: Ref<string>, afterInsert: () => void) {
  const voz = useVoz((dictated) => {
    const el = ta.value
    const r = insertAtCursor(text.value, el?.selectionStart, el?.selectionEnd, dictated)
    text.value = r.text
    nextTick(() => {
      afterInsert()
      el?.focus({ preventScroll: true })
      el?.setSelectionRange(r.cursor, r.cursor)
    })
  })

  const onEsc = (e: KeyboardEvent) => {
    if (e.key !== 'Escape') return
    e.preventDefault()
    e.stopPropagation()
    voz.cancel()
  }
  watch(voz.busy, (on) => {
    if (on) document.addEventListener('keydown', onEsc, true)
    else document.removeEventListener('keydown', onEsc, true)
  })
  onBeforeUnmount(() => document.removeEventListener('keydown', onEsc, true))

  function onKeydown(e: KeyboardEvent) {
    if (!isVozShortcut(e) || e.isComposing || !voz.available.value) return
    e.preventDefault()
    voz.toggle()
  }

  return { voz, onKeydown }
}
