import { computed, reactive, shallowRef } from 'vue'
import { ApiError } from '../api/types'
import { addHistorial } from '../lib/terminales'
import { abrirVentana, cerrarVentana } from './app'

const HISTORIAL_KEY = 'orq.terminales.historial'

/** El token vive solo en memoria: nunca en localStorage, URL ni cookie. */
export const ventana = reactive({ token: '', venceAt: 0, idleAt: 0, inactividad: 0, now: Date.now() })
export const ventanaAbierta = computed(() => !!ventana.token && secondsLeft() > 0)
export const countdown = computed(() => secondsLeft())

function secondsLeft(): number {
  if (!ventana.token) return 0
  return Math.max(0, Math.ceil((Math.min(ventana.venceAt, ventana.idleAt) - ventana.now) / 1000))
}

let ticker: ReturnType<typeof setInterval> | undefined

function startTicker() {
  stopTicker()
  ticker = setInterval(() => {
    ventana.now = Date.now()
    if (secondsLeft() <= 0) clearVentana()
  }, 1000)
}

function stopTicker() {
  clearInterval(ticker)
  ticker = undefined
}

function clearVentana() {
  stopTicker()
  ventana.token = ''
  ventana.venceAt = 0
  ventana.idleAt = 0
}

export async function openVentana(pin: string): Promise<void> {
  const out = await abrirVentana(pin)
  const now = Date.now()
  ventana.token = out.token
  ventana.now = now
  ventana.venceAt = now + out.vence_en * 1000
  ventana.inactividad = out.inactividad
  ventana.idleAt = now + out.inactividad * 1000
  startTicker()
}

/** Cada comando que sale bien renueva la inactividad, nunca el tope absoluto. */
export function touchVentana(): void {
  if (!ventana.token) return
  ventana.now = Date.now()
  ventana.idleAt = ventana.now + ventana.inactividad * 1000
}

export function closeVentana(keepalive = false): void {
  const token = ventana.token
  clearVentana()
  if (token) void cerrarVentana(token, keepalive).catch(() => {})
}

/** El servidor dijo 401: la ventana ya no existe allá, solo se borra acá. */
export function forgetVentana(): void {
  clearVentana()
}

let guarded = false
export function guardVentana(): void {
  if (guarded || typeof document === 'undefined') return
  guarded = true
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') closeVentana(true)
  })
  window.addEventListener('pagehide', () => closeVentana(true))
}

export function pinProblem(e: unknown): { message: string; retryAfter: number | null } {
  if (e instanceof ApiError && e.status === 429) return { message: 'Demasiados intentos.', retryAfter: e.retryAfter ?? 600 }
  if (e instanceof ApiError && e.status === 401) return { message: 'PIN incorrecto', retryAfter: null }
  if (e instanceof ApiError && e.status === 403) return { message: 'La escritura está apagada en la configuración', retryAfter: null }
  return { message: 'No pude conectar con el servidor', retryAfter: null }
}

// ---------- historial local de comandos que salieron bien ----------

export const historial = shallowRef<string[]>(loadHistorial())

function loadHistorial(): string[] {
  try {
    const raw = JSON.parse(localStorage.getItem(HISTORIAL_KEY) ?? '[]')
    return Array.isArray(raw) ? raw.filter((c): c is string => typeof c === 'string').slice(0, 30) : []
  } catch {
    return []
  }
}

function saveHistorial(list: string[]) {
  historial.value = list
  try {
    localStorage.setItem(HISTORIAL_KEY, JSON.stringify(list))
  } catch {
    /* sin almacenamiento: queda en memoria */
  }
}

export const rememberCommand = (cmd: string) => saveHistorial(addHistorial(historial.value, cmd))

export function clearHistorial() {
  saveHistorial([])
  try {
    localStorage.removeItem(HISTORIAL_KEY)
  } catch {
    /* nada que borrar */
  }
}
