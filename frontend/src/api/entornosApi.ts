import { ApiError } from './types'

export const NOMBRE_RE = /^[a-z0-9_-]{1,64}$/

export interface PuertoEntorno {
  puerto: number
  servicio: string
  puerto_contenedor: number | null
  abrible: boolean
}

export type SaludEntorno = 'verde' | 'amarillo' | 'rojo' | null

export type EstadoServicio = 'corriendo' | 'arrancando' | 'enfermo' | 'reiniciando' | 'pausado' | 'caido' | 'terminado'

export interface ServicioEntorno {
  servicio: string
  estado: EstadoServicio
  codigo: number | null
  hace_s: number | null
}

const ESTADOS_SERVICIO = new Set<EstadoServicio>([
  'corriendo',
  'arrancando',
  'enfermo',
  'reiniciando',
  'pausado',
  'caido',
  'terminado',
])
const SALUD_OK = new Set(['verde', 'amarillo', 'rojo'])

export interface Entorno {
  nombre: string
  carpeta: string
  principal: number | null
  puertos: PuertoEntorno[]
  salud: SaludEntorno
  apagado: boolean
  servicios: ServicioEntorno[]
}

export interface ListadoEntornos {
  entornos: Entorno[]
  error: string | null
}

const str = (v: unknown, max: number) => (typeof v === 'string' ? v.slice(0, max) : '')

function enteroNoNegativo(v: unknown): number | null {
  if (v === null || v === undefined) return null
  if (typeof v !== 'number' || !Number.isInteger(v) || v < 0) return null
  return v
}

function normalizarServicio(raw: unknown): ServicioEntorno | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const o = raw as Record<string, unknown>
  const estado = o.estado
  if (typeof estado !== 'string' || !ESTADOS_SERVICIO.has(estado as EstadoServicio)) return null
  const servicio = str(o.servicio, 80)
  if (!servicio) return null
  return {
    servicio,
    estado: estado as EstadoServicio,
    codigo: enteroNoNegativo(o.codigo),
    hace_s: enteroNoNegativo(o.hace_s),
  }
}

function normalizarPuerto(raw: unknown): PuertoEntorno | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const o = raw as Record<string, unknown>
  const puerto = o.puerto
  if (typeof puerto !== 'number' || !Number.isInteger(puerto) || puerto < 1 || puerto > 65535) return null
  let puerto_contenedor: number | null = null
  if (o.puerto_contenedor === null || o.puerto_contenedor === undefined) {
    puerto_contenedor = null
  } else if (typeof o.puerto_contenedor === 'number' && Number.isInteger(o.puerto_contenedor)) {
    if (o.puerto_contenedor < 1 || o.puerto_contenedor > 65535) {
      puerto_contenedor = null
    } else {
      puerto_contenedor = o.puerto_contenedor
    }
  }
  return {
    puerto,
    servicio: str(o.servicio, 80),
    puerto_contenedor,
    abrible: o.abrible === true,
  }
}

function normalizarEntorno(raw: unknown): Entorno | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const o = raw as Record<string, unknown>
  const nombre = str(o.nombre, 64)
  if (!NOMBRE_RE.test(nombre)) return null
  const carpeta = str(o.carpeta, 300)
  const puertos = (Array.isArray(o.puertos) ? o.puertos : []).map(normalizarPuerto).filter((p): p is PuertoEntorno => !!p)
  const pr = o.principal
  let principal: number | null = null
  if (typeof pr === 'number' && Number.isInteger(pr)) {
    const enc = puertos.find((p) => p.puerto === pr && p.abrible)
    if (enc) principal = pr
  }
  let salud: SaludEntorno = null
  if (typeof o.salud === 'string' && SALUD_OK.has(o.salud)) salud = o.salud as SaludEntorno
  const apagado = o.apagado === true
  const servicios = (Array.isArray(o.servicios) ? o.servicios : [])
    .map(normalizarServicio)
    .filter((s): s is ServicioEntorno => !!s)
  return { nombre, carpeta, principal, puertos, salud, apagado, servicios }
}

export function normalizarEntornos(raw: unknown): ListadoEntornos {
  if (raw == null || typeof raw !== 'object' || Array.isArray(raw)) return { entornos: [], error: null }
  const o = raw as Record<string, unknown>
  let error: string | null = null
  if (o.error != null) error = typeof o.error === 'string' ? o.error : null
  const lista = Array.isArray(o.entornos) ? o.entornos : []
  const entornos = lista.map(normalizarEntorno).filter((e): e is Entorno => !!e)
  return { entornos, error }
}

export type MetodoPrueba = 'GET' | 'HEAD' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export interface PedidoPrueba {
  nombre: string
  puerto: number
  metodo: MetodoPrueba
  ruta: string
  encabezados: { nombre: string; valor: string }[]
  cuerpo: string | null
  confirmado: boolean
}

export interface ResultadoPrueba {
  codigo: number
  ms: number
  tipo: string
  encabezados: [string, string][]
  cuerpo: string | null
  bytes: number
  truncado: boolean
}

function parEncabezado(raw: unknown): [string, string] | null {
  if (!Array.isArray(raw) || raw.length < 2) return null
  if (typeof raw[0] !== 'string' || typeof raw[1] !== 'string') return null
  return [raw[0], raw[1]]
}

export function normalizarResultadoPrueba(raw: unknown): ResultadoPrueba {
  if (raw == null || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new ApiError(0, 'Respuesta inválida del servidor')
  }
  const o = raw as Record<string, unknown>
  const codigo = enteroNoNegativo(o.codigo)
  const ms = enteroNoNegativo(o.ms)
  const bytes = enteroNoNegativo(o.bytes)
  if (codigo === null || ms === null || bytes === null) {
    throw new ApiError(0, 'Respuesta inválida del servidor')
  }
  const tipo = typeof o.tipo === 'string' ? o.tipo : ''
  let cuerpo: string | null
  if (o.cuerpo === null || o.cuerpo === undefined) cuerpo = null
  else if (typeof o.cuerpo === 'string') cuerpo = o.cuerpo
  else throw new ApiError(0, 'Respuesta inválida del servidor')
  if (typeof o.truncado !== 'boolean') throw new ApiError(0, 'Respuesta inválida del servidor')
  const encabezados = (Array.isArray(o.encabezados) ? o.encabezados : [])
    .map(parEncabezado)
    .filter((x): x is [string, string] => !!x)
  return { codigo, ms, tipo, encabezados, cuerpo, bytes, truncado: o.truncado }
}

export async function probarEntorno(p: PedidoPrueba, f?: typeof fetch): Promise<ResultadoPrueba> {
  const fetchFn = f ?? fetch
  let res: Response
  try {
    res = await fetchFn('/api/entornos/probar', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(p),
    })
  } catch {
    throw new ApiError(0, 'Se cortó la conexión con el servidor')
  }
  if (!res.ok) {
    let detail = res.statusText || `HTTP ${res.status}`
    try {
      const d = (await res.json()) as { error?: unknown; detail?: unknown }
      if (typeof d?.error === 'string') detail = d.error
      else if (typeof d?.detail === 'string') detail = d.detail
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, detail)
  }
  return normalizarResultadoPrueba(await res.json())
}

export async function listarEntornos(f?: typeof fetch): Promise<ListadoEntornos> {
  const fetchFn = f ?? fetch
  let res: Response
  try {
    res = await fetchFn('/api/entornos', { credentials: 'same-origin' })
  } catch {
    throw new ApiError(0, 'Se cortó la conexión con el servidor')
  }
  if (!res.ok) {
    let detail = res.statusText || `HTTP ${res.status}`
    try {
      const d = (await res.json()) as { detail?: unknown }
      if (typeof d?.detail === 'string') detail = d.detail
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, detail)
  }
  return normalizarEntornos(await res.json())
}
