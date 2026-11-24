import type { Invoke } from './nudoPuente'

export interface CapturaPc {
  foto: number
  ventana: { titulo: string; proceso: string }
  controles: { n: number; tipo: string; nombre: string }[]
  imagen: { tipo: 'png' | 'jpeg'; ancho: number; alto: number; b64: string }
}

export type ErrorMostrar = 'apagado' | 'sin_ventana' | 'ocupado' | 'grande' | 'sin_pregunta' | 'fallo'

export const MENSAJE_MOSTRAR: Record<ErrorMostrar, string> = {
  apagado: 'Prendé el nudo en la bandeja',
  sin_ventana: 'No hay una ventana para mirar',
  ocupado: 'El Copiloto está ocupado: probá en un rato',
  grande: 'La captura es muy grande',
  sin_pregunta: 'Escribí qué querés que te muestre',
  fallo: 'No pude mirar la ventana',
}

const LADO_MAX = 1568
const obj = (v: unknown): Record<string, unknown> | null => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null)
const lado = (v: unknown): v is number => typeof v === 'number' && Number.isInteger(v) && v >= 1 && v <= LADO_MAX

export function normalizarCaptura(raw: unknown): CapturaPc | null {
  const c = obj(raw)
  const v = obj(c?.ventana)
  const im = obj(c?.imagen)
  if (!c || !v || !im) return null
  if (typeof c.foto !== 'number' || !Number.isFinite(c.foto)) return null
  if (typeof v.titulo !== 'string' || typeof v.proceso !== 'string') return null
  if (im.tipo !== 'png' && im.tipo !== 'jpeg') return null
  if (!lado(im.ancho) || !lado(im.alto) || typeof im.b64 !== 'string' || !im.b64) return null
  if (!Array.isArray(c.controles)) return null
  const controles: CapturaPc['controles'] = []
  for (const x of c.controles) {
    const o = obj(x)
    if (!o || typeof o.n !== 'number' || typeof o.tipo !== 'string' || typeof o.nombre !== 'string') return null
    controles.push({ n: o.n, tipo: o.tipo, nombre: o.nombre })
  }
  return {
    foto: c.foto,
    ventana: { titulo: v.titulo, proceso: v.proceso },
    controles,
    imagen: { tipo: im.tipo, ancho: im.ancho, alto: im.alto, b64: im.b64 },
  }
}

function errorDeInvoke(e: unknown): ErrorMostrar {
  const codigo = typeof e === 'string' ? e : e instanceof Error ? e.message : ''
  return codigo === 'apagado' || codigo === 'sin_ventana' ? codigo : 'fallo'
}

function errorDeHttp(e: unknown, pregunta: string): ErrorMostrar {
  const status = typeof e === 'object' && e !== null ? (e as { status?: unknown }).status : undefined
  if (status === 409) return 'ocupado'
  if (status === 413) return 'grande'
  if (status === 422 && !pregunta.trim()) return 'sin_pregunta'
  return 'fallo'
}

export async function mostrar(deps: {
  invoke: Invoke
  post: (url: string, body: unknown) => Promise<unknown>
  reunion: string
  device: string
  pregunta: string
}): Promise<{ ok: true; linea: string } | { ok: false; error: ErrorMostrar }> {
  let captura: CapturaPc | null
  try {
    captura = normalizarCaptura(await deps.invoke('nudo_mostrar'))
  } catch (e) {
    return { ok: false, error: errorDeInvoke(e) }
  }
  if (!captura) return { ok: false, error: 'fallo' }
  try {
    const r = await deps.post('/api/reunion/mostrar', {
      reunion: deps.reunion,
      device: deps.device,
      pregunta: deps.pregunta,
      foto: { foto: captura.foto, ventana: captura.ventana, controles: captura.controles },
      imagen: captura.imagen,
    })
    const linea = obj(r)?.linea
    if (typeof linea !== 'string' || !linea) return { ok: false, error: 'fallo' }
    return { ok: true, linea }
  } catch (e) {
    return { ok: false, error: errorDeHttp(e, deps.pregunta) }
  }
}
