import { reactive, ref } from 'vue'
import {
  borrarPrograma,
  correrAhora,
  crearPrograma,
  editarPrograma,
  getHistorial,
  getProgramadas,
  habilitarProgramadas,
  pausarPrograma,
  type Corrida,
  type Programa,
  type Programadas,
} from '../api/programadasApi'
import { ApiError } from '../api/types'
import { mensajeError } from '../lib/errores'
import { EVENTO_PROGRAMADAS, type CuerpoPrograma } from '../lib/tareas'

export interface ApiTareas {
  get: () => Promise<Programadas>
  historial: (programa?: string, limite?: number) => Promise<Corrida[]>
  crear: (b: CuerpoPrograma) => Promise<Programa | null>
  editar: (id: string, b: CuerpoPrograma) => Promise<Programa | null>
  borrar: (id: string) => Promise<void>
  pausar: (id: string, pausada: boolean) => Promise<Programa | null>
  correr: (id: string, opId: string) => Promise<void>
  habilitar: (habilitado: boolean, pin?: string) => Promise<boolean>
}

let api: ApiTareas = {
  get: () => getProgramadas(),
  historial: (p, l) => getHistorial(p, l),
  crear: (b) => crearPrograma(b),
  editar: (id, b) => editarPrograma(id, b),
  borrar: (id) => borrarPrograma(id),
  pausar: (id, p) => pausarPrograma(id, p),
  correr: (id, op) => correrAhora(id, op),
  habilitar: (h, pin) => habilitarProgramadas(h, pin),
}

export function setTareasApi(a: ApiTareas): void {
  api = a
}

export const tareasOpen = ref(false)
let pushed = false

export const tareas = reactive({
  data: null as Programadas | null,
  historial: [] as Corrida[],
  cargando: false,
  error: '',
  errorAccion: '',
  errorForm: '',
  guardando: false,
  /** Ids con una acción en vuelo. */
  ocupados: {} as Record<string, boolean>,
  pinBusy: false,
  pinError: '',
  pinBloqueadoHasta: 0,
})

export async function cargarTareas(): Promise<void> {
  tareas.cargando = true
  tareas.error = ''
  try {
    const [d, h] = await Promise.all([api.get(), api.historial('', 50)])
    tareas.data = d
    tareas.historial = h
  } catch (e) {
    tareas.error = mensajeError(e, 'No pude leer las tareas programadas.')
  } finally {
    tareas.cargando = false
  }
}

async function accion(id: string, fn: () => Promise<unknown>, fallo: string): Promise<boolean> {
  if (tareas.ocupados[id]) return false
  tareas.ocupados[id] = true
  tareas.errorAccion = ''
  try {
    await fn()
    return true
  } catch (e) {
    tareas.errorAccion = e instanceof ApiError && e.detail ? e.detail : mensajeError(e, fallo)
    return false
  } finally {
    delete tareas.ocupados[id]
    await cargarTareas()
  }
}

export const alternarPausa = (p: Programa) => accion(p.id, () => api.pausar(p.id, !p.pausada), 'No pude cambiar la tarea.')
export const borrar = (p: Programa) => accion(p.id, () => api.borrar(p.id), 'No pude borrar la tarea.')

function idCorrida(): string {
  return `c${crypto.randomUUID().replace(/-/g, '')}`.slice(0, 32)
}
export const correr = (p: Programa) => accion(p.id, () => api.correr(p.id, idCorrida()), 'No pude correr la tarea.')

export async function guardar(cuerpo: CuerpoPrograma, id?: string): Promise<boolean> {
  if (tareas.guardando) return false
  tareas.guardando = true
  tareas.errorForm = ''
  try {
    if (id) await api.editar(id, cuerpo)
    else await api.crear(cuerpo)
  } catch (e) {
    tareas.errorForm = e instanceof ApiError && e.detail ? e.detail : mensajeError(e, 'No pude guardar la tarea.')
    tareas.guardando = false
    return false
  }
  tareas.guardando = false
  await cargarTareas()
  return true
}

/** Apagar no pide PIN; prender sí. Devuelve true si quedó como se pidió. */
export async function interruptor(valor: boolean, pin?: string): Promise<boolean> {
  tareas.pinBusy = true
  tareas.pinError = ''
  tareas.errorAccion = ''
  try {
    const r = await api.habilitar(valor, valor ? pin : undefined)
    await cargarTareas()
    return r === valor
  } catch (e) {
    if (e instanceof ApiError && e.status === 429) {
      tareas.pinBloqueadoHasta = Date.now() + (e.retryAfter ?? 30) * 1000
      tareas.pinError = e.detail
    } else if (valor) tareas.pinError = e instanceof ApiError && e.detail ? e.detail : mensajeError(e, 'No pude prender las tareas.')
    else tareas.errorAccion = mensajeError(e, 'No pude apagar las tareas.')
    return false
  } finally {
    tareas.pinBusy = false
  }
}

export function openTareas(): void {
  if (tareasOpen.value) return
  history.pushState({ ...(history.state ?? {}), orqTareas: true }, '')
  pushed = true
  tareasOpen.value = true
}

export function closeTareas(): void {
  if (!tareasOpen.value) return
  if (pushed && history.state?.orqTareas) history.back()
  else {
    pushed = false
    tareasOpen.value = false
  }
}

/** Al perder la sesión: cierra sin tocar el historial. */
export function resetTareas(): void {
  tareasOpen.value = false
  pushed = false
  tareas.data = null
  tareas.historial = []
  tareas.error = ''
  tareas.errorAccion = ''
  tareas.errorForm = ''
  tareas.guardando = false
  tareas.ocupados = {}
  tareas.pinBusy = false
  tareas.pinError = ''
  tareas.pinBloqueadoHasta = 0
}

if (typeof window !== 'undefined') {
  window.addEventListener(EVENTO_PROGRAMADAS, () => {
    if (tareasOpen.value && !tareas.cargando) void cargarTareas()
  })
  window.addEventListener('popstate', () => {
    if (tareasOpen.value && !history.state?.orqTareas) {
      tareasOpen.value = false
      pushed = false
    }
  })
}

/** Cierra la vista sin tocar el historial: la usa quien navega a otra pantalla enseguida. */
export function soltarTareas(): void {
  tareasOpen.value = false
  pushed = false
}
