import { shallowRef } from 'vue'
import type { Subagente } from '../api/types'
import { anyWorking } from '../lib/subagentes'
import { getSubagentes } from './app'

export const POLL_MS = 4000

export const subagentes = shallowRef<Subagente[]>([])

let timer: ReturnType<typeof setTimeout> | undefined
let active: string | null = null
let sessionBusy: () => boolean = () => false
let listening = false

const visible = () => typeof document === 'undefined' || document.visibilityState === 'visible'

function schedule() {
  clearTimeout(timer)
  if (!active || !visible()) return
  if (anyWorking(subagentes.value) || sessionBusy()) timer = setTimeout(() => void poll(), POLL_MS)
}

export async function poll(): Promise<void> {
  const sid = active
  if (!sid || !visible()) return
  try {
    const items = await getSubagentes(sid)
    if (active !== sid) return
    subagentes.value = items
  } catch {
    if (active !== sid) return
  }
  schedule()
}

function onVisible() {
  if (!active) return
  if (visible()) void poll()
  else clearTimeout(timer)
}

/** Mira los subagentes de una sesión abierta; `busy` dice si la sesión está trabajando (puede lanzar agentes nuevos). */
export function watchSubagentes(sessionId: string, busy: () => boolean): void {
  if (active !== sessionId) subagentes.value = []
  active = sessionId
  sessionBusy = busy
  if (!listening && typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', onVisible)
    listening = true
  }
  void poll()
}

/** La sesión pasó a trabajando: reanuda el sondeo si estaba detenido. */
export function nudgeSubagentes(): void {
  if (active && visible()) schedule()
}

export function stopSubagentes(): void {
  clearTimeout(timer)
  active = null
  subagentes.value = []
}
