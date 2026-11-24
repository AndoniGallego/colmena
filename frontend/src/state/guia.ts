import { ref } from 'vue'
import { MENSAJE_GUIA, pedirGuia, postGuia, salirGuia, siguienteGuia, type ErrorGuia, type RespuestaGuia } from '../lib/guiaPuente'
import type { Invoke } from '../lib/nudoPuente'
import { modo } from './notch'
import { enCurso, reunion } from './reunion'

export type EstadoCajita = 'vacia' | 'preparando' | 'mirando' | 'paso' | 'fin' | 'no_encontrado' | 'error' | 'terminado' | 'reunion'

export interface EstadoGuiaFront {
  estado: EstadoCajita
  guia: number | null
  paso: number
  total: number
  texto: string
  /** En `error`: el backend todavía tiene la guía (solo el 90 s sin respuesta; el resto la terminó). */
  sigue: boolean
}

const ESTADOS_SERVIDOR = new Set<string>(['preparando', 'mirando', 'paso', 'fin', 'no_encontrado', 'error'])

export function inicialGuia(): EstadoGuiaFront {
  return { estado: 'vacia', guia: null, paso: 0, total: 0, texto: '', sigue: false }
}

export const guia = ref<EstadoGuiaFront>(inicialGuia())

let device = ''

export function fijarDevice(d: string): void {
  device = d
}

const obj = (v: unknown): Record<string, unknown> | null => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null)
const numero = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0)

/** Pura: una forma rota o una guía anterior devuelven el mismo `e`. */
export function aplicarEventoGuia(e: EstadoGuiaFront, data: unknown): EstadoGuiaFront {
  const d = obj(data)
  if (!d || typeof d.guia !== 'number' || !Number.isInteger(d.guia) || typeof d.estado !== 'string' || !ESTADOS_SERVIDOR.has(d.estado)) return e
  if (e.guia !== null && d.guia < e.guia) return e
  return {
    estado: d.estado as EstadoCajita,
    guia: d.guia,
    paso: numero(d.paso),
    total: numero(d.total),
    texto: typeof d.texto === 'string' ? d.texto : '',
    sigue: d.estado === 'error' && d.sigue === true,
  }
}

export function textoCajita(e: EstadoGuiaFront): string {
  switch (e.estado) {
    case 'preparando':
      return 'Preparando…'
    case 'mirando':
      return 'Mirando la ventana…'
    case 'paso':
    case 'fin':
      return `Paso ${e.paso} de ${e.total}: ${e.texto}`
    case 'no_encontrado':
    case 'error':
      return e.texto
    case 'terminado':
      return 'Terminado'
    case 'reunion':
      return MENSAJE_GUIA.reunion
    default:
      return ''
  }
}

export function guiaActiva(e: EstadoGuiaFront): boolean {
  return e.estado === 'preparando' || e.estado === 'mirando' || e.estado === 'paso' || e.estado === 'fin' || e.estado === 'no_encontrado'
}

export function puedeSiguiente(e: EstadoGuiaFront): boolean {
  return e.estado === 'paso' || e.estado === 'no_encontrado' || (e.estado === 'error' && e.sigue && e.guia !== null)
}

/** El backend puede seguir teniendo la guía: se ofrece Salir. */
export function seguirViva(e: EstadoGuiaFront): boolean {
  return guiaActiva(e) || (e.estado === 'error' && e.sigue && e.guia !== null)
}

const ocupada = (e: EstadoGuiaFront) => e.estado === 'preparando' || e.estado === 'mirando'

/** "Hecho, siguiente" del globo tocado mientras el ayudante todavía no mandó el bloque: se dispara al llegar el paso. */
let pendiente: { guia: number | null } | null = null

function invocar(): Invoke | null {
  const invoke = window.__TAURI__?.core?.invoke
  return typeof invoke === 'function' ? (invoke as Invoke) : null
}

export async function aplicarServidorGuia(data: unknown): Promise<void> {
  const nuevo = aplicarEventoGuia(guia.value, data)
  if (nuevo === guia.value) return
  guia.value = nuevo
  const quedo = pendiente
  if (nuevo.estado !== 'paso') {
    pendiente = null
  } else if (quedo && quedo.guia !== null && nuevo.guia !== quedo.guia) {
    pendiente = null
  }
  if (nuevo.estado === 'error' && !nuevo.sigue) {
    try {
      await invocar()?.('nudo_limpiar')
    } catch {
      // no había dibujo
    }
  }
  if (nuevo.estado !== 'paso' && nuevo.estado !== 'fin') return
  try {
    await invocar()?.('nudo_guia_paso', { paso: nuevo.paso, total: nuevo.total, fin: nuevo.estado === 'fin' })
  } catch {
    // sin globo que actualizar: la cajita ya muestra el paso
  }
  if (nuevo.estado === 'paso' && pendiente && guia.value.estado === 'paso' && guia.value.guia === nuevo.guia) {
    pendiente = null
    await siguiente()
  }
}

export function abrirCajita(): void {
  if (enCurso(reunion.value)) guia.value = { ...inicialGuia(), estado: 'reunion' }
  else if (guia.value.estado === 'reunion') guia.value = inicialGuia()
  modo.value = 'guia'
}

export async function alAtajo(): Promise<void> {
  if (puedeSiguiente(guia.value) && !enCurso(reunion.value)) {
    // Sin abrir la cajita: abrirla pide el foco y Windows cierra el menú que Ando tenga abierto.
    await siguiente()
    return
  }
  abrirCajita()
}

function fallo(error: ErrorGuia, sigue = false): void {
  guia.value = { ...guia.value, estado: 'error', paso: 0, total: 0, texto: MENSAJE_GUIA[error], sigue }
}

/** Errores de `siguiente` tras los que el backend ya no tiene la guía. */
const TERMINAN_LA_GUIA = new Set<ErrorGuia>(['sin_guia', 'otra_pc', 'reunion'])

/** El SSE puede llegar antes del 202: si ya hay una guía igual o más nueva, el 202 no la pisa. */
function aplicarRespuesta(r: RespuestaGuia, deSiguiente = false): void {
  if (!r.ok) return fallo(r.error, deSiguiente && !TERMINAN_LA_GUIA.has(r.error))
  const actual = guia.value
  if (actual.guia !== null && actual.guia >= r.guia) return
  guia.value = { ...inicialGuia(), estado: r.estado, guia: r.guia }
}

export async function pedir(pregunta: string): Promise<void> {
  const limpia = pregunta.trim()
  if (!limpia || ocupada(guia.value)) return
  pendiente = null
  const invoke = invocar()
  if (!invoke) return fallo('fallo')
  guia.value = { ...guia.value, estado: 'mirando', paso: 0, total: 0, texto: '' }
  aplicarRespuesta(await pedirGuia({ invoke, post: postGuia, device, pregunta: limpia }))
}

export async function siguiente(): Promise<void> {
  if (!puedeSiguiente(guia.value)) return
  const invoke = invocar()
  if (!invoke) return fallo('fallo')
  guia.value = { ...guia.value, estado: 'mirando', paso: 0, total: 0, texto: '' }
  const r = await siguienteGuia({ invoke, post: postGuia, device })
  aplicarRespuesta(r, true)
  if (!r.ok && r.error === 'sin_guia') await limpiarDibujo()
}

async function limpiarDibujo(): Promise<void> {
  try {
    await invocar()?.('nudo_limpiar')
  } catch {
    // no había dibujo
  }
}

export async function siguienteDelGlobo(): Promise<void> {
  if (ocupada(guia.value)) {
    pendiente = { guia: guia.value.guia }
    return
  }
  await siguiente()
}

export async function terminar(): Promise<void> {
  const e = guia.value
  if (e.estado === 'vacia' || e.estado === 'terminado' || (e.estado === 'error' && !e.sigue)) return
  pendiente = null
  await salirGuia({ post: postGuia, device })
  try {
    await invocar()?.('nudo_limpiar')
  } catch {
    // no había dibujo
  }
  guia.value = { ...inicialGuia(), estado: 'terminado' }
}
