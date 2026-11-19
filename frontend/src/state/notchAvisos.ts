import { reactive, ref, watch } from 'vue'
import {
  debeReemplazarAvisoActual,
  esPedidoPestanaNotch,
  esTeTocaAviso,
  maxId,
  nuevosParaNotch,
  siguienteAviso,
  type AvisoNotch,
} from '../lib/notchAvisos'
import { pedidoPestanaPendiente } from './pedidosPestana'
import { sonarTeToca } from '../lib/notchSonido'
import { isSoft } from '../motion'
import { auth, avisoEvent, boardState, getAvisos, pedidoPestanaEvent } from './app'
import { modo, puente, sesiones } from './notch'
import { alSoltarRetencionAviso, filas, retenerRespuestaAviso } from './notchRespuesta'

export { marcarRetenerRespuestaAviso, retenerRespuestaAviso } from './notchRespuesta'

export const avisoActual = ref<AvisoNotch | null>(null)
export const cola = reactive<AvisoNotch[]>([])

function puedeCerrarAvisoAuto(): boolean {
  return !retenerRespuestaAviso.value
}

const GRACIA_MS = 5000

type MetaAviso = { llegada: number; vistoTeToca: boolean }
const metaPorId = new Map<number, MetaAviso>()

let ultimo = 0
let baseLista = false
let basePromise: Promise<void> = Promise.resolve()
let hooks = false
let sonarFn: () => void = () => {
  sonarTeToca()
}

function limpiarMeta(ids: Iterable<number>): void {
  for (const id of ids) metaPorId.delete(id)
}

export function _resetIniciar(): void {
  ultimo = 0
  baseLista = false
  basePromise = Promise.resolve()
  avisoActual.value = null
  cola.splice(0, cola.length)
  metaPorId.clear()
  retenerRespuestaAviso.value = false
  clearTimeout(cerrarTimer)
  clearTimeout(recogerAvisoTimer)
  clearTimeout(graciaVisibleTimer)
}

function teTocaSids(): Set<string> {
  const s = new Set<string>()
  for (const x of sesiones.value) {
    if (x.estado === 'te-toca') s.add(x.session_id)
  }
  return s
}

function esResuelto(a: AvisoNotch): boolean {
  if (esPedidoPestanaNotch(a)) return !pedidoPestanaPendiente(a.pedido)
  if (!esTeTocaAviso(a)) return false
  const meta = metaPorId.get(a.id)
  if (!meta) return false
  const teTocaAhora = teTocaSids()
  const sid = a.session_id
  if (meta.vistoTeToca && !teTocaAhora.has(sid)) {
    metaPorId.delete(a.id)
    return true
  }
  if (Date.now() - meta.llegada > GRACIA_MS && !teTocaAhora.has(sid)) {
    metaPorId.delete(a.id)
    return true
  }
  return false
}

function registrarMeta(nuevos: AvisoNotch[]): void {
  const t = Date.now()
  for (const a of nuevos) {
    if (!metaPorId.has(a.id)) metaPorId.set(a.id, { llegada: t, vistoTeToca: false })
  }
}

function marcarVistoTeToca(): void {
  const teTocaAhora = teTocaSids()
  const ids = new Set<number>()
  const cur = avisoActual.value
  if (cur) ids.add(cur.id)
  for (const a of cola) ids.add(a.id)
  for (const id of ids) {
    const meta = metaPorId.get(id)
    if (!meta) continue
    const aviso = cur?.id === id ? cur : cola.find((x) => x.id === id)
    if (aviso && esTeTocaAviso(aviso) && teTocaAhora.has(aviso.session_id)) {
      meta.vistoTeToca = true
    }
  }
}

let graciaVisibleTimer: ReturnType<typeof setTimeout> | undefined

function programarGraciaVisible(a: AvisoNotch): void {
  clearTimeout(graciaVisibleTimer)
  if (!esTeTocaAviso(a) || esPedidoPestanaNotch(a)) return
  const id = a.id
  const meta = metaPorId.get(id)
  const llegada = meta?.llegada ?? Date.now()
  const restante = GRACIA_MS - (Date.now() - llegada)
  graciaVisibleTimer = setTimeout(() => {
    if (!puedeCerrarAvisoAuto()) return
    if (avisoActual.value?.id !== id) return
    if (teTocaSids().has(a.session_id)) return
    const m = metaPorId.get(id)
    if (m?.vistoTeToca) return
    cerrarAviso()
  }, Math.max(0, restante))
}

function intentarCierreAutomaticoTeToca(): void {
  if (!puedeCerrarAvisoAuto()) return
  const cur = avisoActual.value
  if (!cur || !esTeTocaAviso(cur)) return
  const meta = metaPorId.get(cur.id)
  if (!meta) return

  const teTocaAhora = teTocaSids()
  if (!meta.vistoTeToca) {
    if (Date.now() - meta.llegada > GRACIA_MS && !teTocaAhora.has(cur.session_id)) {
      cerrarAviso()
    }
    return
  }

  const sigue = sesiones.value.some((s) => s.session_id === cur.session_id && s.estado === 'te-toca')
  if (sigue) return

  clearTimeout(recogerAvisoTimer)
  const id = cur.id
  const delay = filas[cur.session_id]?.fase === 'enviado' ? (isSoft() ? 0 : 1200) : 0
  if (delay === 0) {
    cerrarAviso()
    return
  }
  recogerAvisoTimer = setTimeout(() => {
    if (!puedeCerrarAvisoAuto()) return
    if (avisoActual.value?.id !== id) return
    cerrarAviso()
  }, delay)
}

function mostrarAviso(aviso: AvisoNotch): void {
  avisoActual.value = aviso
  // Con la captura de notas abierta el aviso queda en pausa; sale al cerrarla (watch de modo).
  if (modo.value === 'notas') return
  modo.value = 'aviso'
  puente().aviso(aviso.kind === 'done' ? 'termino' : 'te-toca')
  programarGraciaVisible(aviso)
}

function mostrarSiguiente(): void {
  if (modo.value === 'notas') return
  const mostrando = avisoActual.value
  const { aviso, resto, descartados } = siguienteAviso(cola, teTocaSids(), esResuelto, {
    ahora: Date.now(),
    llegada: (a) => metaPorId.get(a.id)?.llegada,
    mostrando,
  })
  limpiarMeta(descartados.map((a) => a.id))
  cola.splice(0, cola.length, ...resto)
  if (aviso) {
    mostrarAviso(aviso)
  } else {
    clearTimeout(graciaVisibleTimer)
    avisoActual.value = null
    if (modo.value === 'aviso') modo.value = 'cerrado'
  }
}

function encolar(nuevos: AvisoNotch[]): void {
  registrarMeta(nuevos)
  cola.push(...nuevos)
  marcarVistoTeToca()
  // Mientras se escribe una nota, los avisos esperan en la cola y salen al cerrar la captura.
  if (modo.value === 'notas') return

  const reemplazo = debeReemplazarAvisoActual(avisoActual.value, nuevos, teTocaSids(), esResuelto)
  if (reemplazo) {
    const actual = avisoActual.value
    if (actual) metaPorId.delete(actual.id)
    clearTimeout(cerrarTimer)
    clearTimeout(recogerAvisoTimer)
    clearTimeout(graciaVisibleTimer)
    const idx = cola.findIndex((a) => a.id === reemplazo.id)
    if (idx >= 0) cola.splice(idx, 1)
    mostrarAviso(reemplazo)
    return
  }

  if (!avisoActual.value) mostrarSiguiente()
}

async function leerBase(): Promise<void> {
  try {
    const page = await getAvisos(20, 0, true)
    ultimo = Math.max(ultimo, maxId(page.items))
    baseLista = true
  } catch {
    baseLista = false
  }
}

function arrancarBase(): void {
  baseLista = false
  basePromise = leerBase()
}

async function asegurarBase(): Promise<boolean> {
  if (baseLista) return true
  await basePromise
  if (baseLista) return true
  await leerBase()
  return baseLista
}

export function limpiarColaAvisoVisible(): void {
  limpiarMeta(cola.map((a) => a.id))
  if (avisoActual.value) metaPorId.delete(avisoActual.value.id)
  cola.splice(0, cola.length)
  avisoActual.value = null
}

let cerrarTimer: ReturnType<typeof setTimeout> | undefined
let recogerAvisoTimer: ReturnType<typeof setTimeout> | undefined

export function cerrarAviso(): void {
  clearTimeout(cerrarTimer)
  clearTimeout(recogerAvisoTimer)
  clearTimeout(graciaVisibleTimer)
  if (avisoActual.value) metaPorId.delete(avisoActual.value.id)
  retenerRespuestaAviso.value = false
  avisoActual.value = null
  if (modo.value !== 'notas') modo.value = 'cerrado'
  const delay = isSoft() ? 0 : 750
  cerrarTimer = setTimeout(() => {
    if (modo.value === 'cerrado') mostrarSiguiente()
  }, delay)
}

async function onAvisoEvent(): Promise<void> {
  try {
    if (!(await asegurarBase())) return
    const page = await getAvisos(20, 0, true)
    const nuevos = nuevosParaNotch(page.items, ultimo)
    ultimo = Math.max(ultimo, maxId(page.items))
    if (!nuevos.length) return

    if (nuevos.some(esTeTocaAviso)) sonarFn()

    if (modo.value === 'panel') return

    encolar(nuevos)
  } catch {
    /* getAvisos falló; el próximo evento reintenta */
  }
}

export function iniciarAvisosNotch(deps?: { sonar?: () => void }): void {
  if (deps?.sonar) sonarFn = deps.sonar
  if (hooks) return
  hooks = true

  watch(
    () => auth.value,
    (v) => {
      if (v === 'ready') arrancarBase()
    },
    { immediate: true },
  )

  watch(
    () => boardState.value.connection,
    (v, prev) => {
      if (v === 'live' && prev !== undefined && prev !== 'live') arrancarBase()
    },
  )

  watch(avisoEvent, () => {
    void onAvisoEvent()
  })

  // Al cerrar la captura de notas vuelve el aviso que tapó o sale el siguiente de la cola.
  watch(modo, (m, prev) => {
    if (prev !== 'notas' || m !== 'cerrado') return
    if (!avisoActual.value && !cola.length) return
    clearTimeout(cerrarTimer)
    cerrarTimer = setTimeout(() => {
      if (modo.value !== 'cerrado') return
      if (avisoActual.value) mostrarAviso(avisoActual.value)
      else mostrarSiguiente()
    }, isSoft() ? 0 : 750)
  })

  watch(pedidoPestanaEvent, () => {
    const cur = avisoActual.value
    if (!cur || !esPedidoPestanaNotch(cur)) return
    if (esResuelto(cur)) cerrarAviso()
    else mostrarSiguiente()
  })

  watch(sesiones, (list) => {
    marcarVistoTeToca()

    const cur = avisoActual.value
    if (!cur || !esTeTocaAviso(cur)) return
    const meta = metaPorId.get(cur.id)
    if (!meta) return

    const teTocaAhora = teTocaSids()
    if (!puedeCerrarAvisoAuto()) return

    if (!meta.vistoTeToca) {
      if (Date.now() - meta.llegada > GRACIA_MS && !teTocaAhora.has(cur.session_id)) {
        cerrarAviso()
        return
      }
      return
    }

    const sigue = list.some((s) => s.session_id === cur.session_id && s.estado === 'te-toca')
    if (sigue) return
    clearTimeout(recogerAvisoTimer)
    const id = cur.id
    const delay = filas[cur.session_id]?.fase === 'enviado' ? (isSoft() ? 0 : 1200) : 0
    if (delay === 0) {
      cerrarAviso()
      return
    }
    recogerAvisoTimer = setTimeout(() => {
      if (!puedeCerrarAvisoAuto()) return
      if (avisoActual.value?.id !== id) return
      cerrarAviso()
    }, delay)
  })

  alSoltarRetencionAviso(intentarCierreAutomaticoTeToca)
}
