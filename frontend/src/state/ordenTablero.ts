import { computed, ref, watch } from 'vue'
import { ApiError } from '../api/types'
import {
  auth,
  ordenPestanasEvent,
  ordenTableroEvent,
  plegadasEvent,
  silenciadasEvent,
  setOrdenPestanas as putOrdenPestanas,
  setOrdenTablero as putOrden,
  setPlegadas as putPlegadas,
  setSilencio as putSilencio,
  getOrdenTablero,
} from './app'

export const ordenError = ref('')
export const plegadasError = ref('')
export const ordenGuardado = ref<string[]>([])
export const ordenPestanasGuardado = ref<Record<string, string[]>>({})
export const plegadasGuardado = ref<string[]>([])
export const silenciadasGuardado = ref<string[]>([])
export const silencioError = ref<{ sid: string; texto: string } | null>(null)

export const hayOrdenManual = computed(
  () => ordenGuardado.value.length > 0 || Object.keys(ordenPestanasGuardado.value).length > 0,
)

export function plegadasIguales(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((id, i) => id === b[i])
}

let started = false

export async function cargarOrdenTablero(): Promise<void> {
  if (auth.value !== 'ready') return
  try {
    const data = await getOrdenTablero()
    ordenGuardado.value = data.orden
    ordenPestanasGuardado.value = { ...data.pestanas }
    plegadasGuardado.value = [...data.plegadas]
    silenciadasGuardado.value = [...(data.silenciadas ?? [])]
  } catch {
    /* se reintenta al reconectar */
  }
}

export async function guardarOrden(orden: string[]): Promise<void> {
  const prev = ordenGuardado.value
  ordenGuardado.value = orden
  ordenError.value = ''
  try {
    await putOrden(orden)
  } catch (e) {
    ordenGuardado.value = prev
    if (!(e instanceof ApiError && e.status === 401)) ordenError.value = 'No pude guardar el orden'
  }
}

export async function guardarOrdenPestanas(grupo: string, orden: string[]): Promise<void> {
  const prev = { ...ordenPestanasGuardado.value }
  const next = { ...prev }
  if (orden.length) next[grupo] = orden
  else delete next[grupo]
  ordenPestanasGuardado.value = next
  try {
    await putOrdenPestanas(grupo, orden)
  } catch (e) {
    ordenPestanasGuardado.value = prev
    if (!(e instanceof ApiError && e.status === 401)) ordenError.value = 'No pude guardar el orden'
  }
}

export async function guardarPlegadas(plegadas: string[]): Promise<void> {
  const prev = plegadasGuardado.value
  plegadasGuardado.value = [...plegadas]
  plegadasError.value = ''
  try {
    await putPlegadas(plegadas)
  } catch (e) {
    plegadasGuardado.value = prev
    if (!(e instanceof ApiError && e.status === 401)) plegadasError.value = 'No pude guardar si está plegada'
  }
}

export async function silenciarSesion(sid: string, on: boolean): Promise<void> {
  const prev = silenciadasGuardado.value
  silenciadasGuardado.value = on ? (prev.includes(sid) ? prev : [...prev, sid]) : prev.filter((x) => x !== sid)
  silencioError.value = null
  try {
    await putSilencio(sid, on)
  } catch (e) {
    silenciadasGuardado.value = prev
    if (!(e instanceof ApiError && e.status === 401)) silencioError.value = { sid, texto: 'No pude cambiar el silencio' }
  }
}

export async function volverOrdenAutomatico(): Promise<void> {
  const prevCards = ordenGuardado.value
  const prevPest = { ...ordenPestanasGuardado.value }
  ordenGuardado.value = []
  ordenPestanasGuardado.value = {}
  try {
    await putOrden([])
  } catch (e) {
    ordenGuardado.value = prevCards
    ordenPestanasGuardado.value = prevPest
    if (!(e instanceof ApiError && e.status === 401)) ordenError.value = 'No pude guardar el orden'
  }
}

export function initOrdenTablero(): void {
  if (started) return
  started = true
  watch(() => auth.value, (a) => a === 'ready' && void cargarOrdenTablero(), { immediate: true })
  watch(ordenTableroEvent, (e) => {
    if (e) ordenGuardado.value = [...e.orden]
  })
  watch(ordenPestanasEvent, (e) => {
    if (!e) return
    if (!e.grupo) {
      ordenPestanasGuardado.value = {}
      return
    }
    const next = { ...ordenPestanasGuardado.value }
    if (e.orden.length) next[e.grupo] = [...e.orden]
    else delete next[e.grupo]
    ordenPestanasGuardado.value = next
  })
  watch(silenciadasEvent, (e) => {
    if (e) silenciadasGuardado.value = [...e.silenciadas]
  })
  watch(plegadasEvent, (e) => {
    if (!e) return
    const next = [...e.plegadas]
    if (plegadasIguales(plegadasGuardado.value, next)) return
    plegadasGuardado.value = next
  })
}
