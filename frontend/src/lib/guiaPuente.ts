import { normalizarCaptura } from './mostrarPuente'
import type { Invoke } from './nudoPuente'

export type ErrorGuia =
  | 'apagado'
  | 'sin_ventana'
  | 'reunion'
  | 'otra_pc'
  | 'mirando'
  | 'sin_guia'
  | 'sin_pregunta'
  | 'grande'
  | 'invalida'
  | 'sin_conexion'
  | 'fallo'

export const MENSAJE_GUIA: Record<ErrorGuia, string> = {
  apagado: 'Prendé el nudo en la bandeja',
  sin_ventana: 'No hay una ventana para mirar',
  reunion: 'Hay una reunión en curso: usá Mostrame del notch',
  otra_pc: 'La guía está en otra PC',
  mirando: 'Todavía estoy mirando',
  sin_guia: 'No hay una guía en curso',
  sin_pregunta: 'Escribí qué querés hacer',
  grande: 'La captura es muy grande',
  invalida: 'No pude mirar la ventana',
  sin_conexion: 'Sin conexión con la notebook',
  fallo: 'No pude mirar la ventana',
}

export class ErrorHttpGuia extends Error {
  constructor(
    public status: number,
    public codigo: string | null,
  ) {
    super(`guia ${status}${codigo ? ` ${codigo}` : ''}`)
    this.name = 'ErrorHttpGuia'
  }
}

type Post = (url: string, body: unknown) => Promise<unknown>

export type RespuestaGuia = { ok: true; guia: number; estado: 'preparando' | 'mirando' } | { ok: false; error: ErrorGuia }

const obj = (v: unknown): Record<string, unknown> | null => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null)
const CODIGOS_HTTP = new Set<string>(['reunion', 'otra_pc', 'mirando', 'sin_guia', 'sin_pregunta', 'invalida'])

export async function postGuia(url: string, body: unknown): Promise<unknown> {
  const res = await fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    let codigo: string | null = null
    try {
      const c = obj(obj(await res.json())?.detail)?.codigo
      if (typeof c === 'string') codigo = c
    } catch {
      // cuerpo sin JSON: queda sin código
    }
    throw new ErrorHttpGuia(res.status, codigo)
  }
  return res.json()
}

function errorDeInvoke(e: unknown): ErrorGuia {
  const codigo = typeof e === 'string' ? e : e instanceof Error ? e.message : ''
  return codigo === 'apagado' || codigo === 'sin_ventana' ? codigo : 'fallo'
}

function errorDeHttp(e: unknown): ErrorGuia {
  if (e instanceof TypeError) return 'sin_conexion'
  const status = obj(e)?.status
  const codigo = obj(e)?.codigo
  if (typeof codigo === 'string' && CODIGOS_HTTP.has(codigo)) return codigo as ErrorGuia
  if (status === 413) return 'grande'
  if (status === 422) return 'invalida'
  return 'fallo'
}

async function capturarYPostear(deps: { invoke: Invoke; post: Post }, url: string, cuerpo: (c: NonNullable<ReturnType<typeof normalizarCaptura>>) => Record<string, unknown>): Promise<RespuestaGuia> {
  try {
    await deps.invoke('nudo_limpiar')
  } catch {
    // sin dibujo previo que borrar o falló: se mira igual
  }
  let captura: ReturnType<typeof normalizarCaptura>
  try {
    captura = normalizarCaptura(await deps.invoke('nudo_mostrar'))
  } catch (e) {
    return { ok: false, error: errorDeInvoke(e) }
  }
  if (!captura) return { ok: false, error: 'fallo' }
  try {
    const r = obj(await deps.post(url, cuerpo(captura)))
    const estado = r?.estado
    if (typeof r?.guia !== 'number' || !Number.isInteger(r.guia) || (estado !== 'preparando' && estado !== 'mirando')) return { ok: false, error: 'fallo' }
    return { ok: true, guia: r.guia, estado }
  } catch (e) {
    return { ok: false, error: errorDeHttp(e) }
  }
}

const fotoDe = (c: { foto: number; ventana: unknown; controles: unknown }) => ({ foto: c.foto, ventana: c.ventana, controles: c.controles })

export function pedirGuia(deps: { invoke: Invoke; post: Post; device: string; pregunta: string }): Promise<RespuestaGuia> {
  return capturarYPostear(deps, '/api/guia/pedir', (c) => ({ device: deps.device, pregunta: deps.pregunta, foto: fotoDe(c), imagen: c.imagen }))
}

export function siguienteGuia(deps: { invoke: Invoke; post: Post; device: string }): Promise<RespuestaGuia> {
  return capturarYPostear(deps, '/api/guia/siguiente', (c) => ({ device: deps.device, foto: fotoDe(c), imagen: c.imagen }))
}

export async function salirGuia(deps: { post: Post; device: string }): Promise<void> {
  try {
    await deps.post('/api/guia/salir', { device: deps.device })
  } catch (e) {
    console.warn('[guia] no se pudo avisar la salida', e)
  }
}
