import { clipPalabras } from './estado'

export type ResultadoPrueba = 'ok' | 'falla' | 'omitida'

export interface CasoPrueba {
  nombre: string
  resultado: ResultadoPrueba
  detalle?: string
  /** Ruta absoluta de la captura que respalda el caso. */
  evidencia?: string
}

export interface Pruebas {
  titulo: string
  resumen?: string
  casos: CasoPrueba[]
}

export const ID_CAPTURA = /^ss_[a-z0-9]{4,40}$/
export const PRUEBAS_LIMITES = { titulo: 100, resumen: 300, nombre: 120, detalle: 400, evidencia: 500, casos: 60 } as const

const RESULTADOS: readonly string[] = ['ok', 'falla', 'omitida']

const texto = (v: unknown, limit: number): string | undefined => (typeof v === 'string' && v.trim() ? clipPalabras(v, limit) : undefined)

function toCaso(v: unknown): CasoPrueba | null {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return null
  const o = v as Record<string, unknown>
  const nombre = texto(o.nombre, PRUEBAS_LIMITES.nombre)
  const resultado = typeof o.resultado === 'string' ? o.resultado.trim().toLowerCase() : ''
  if (!nombre || !RESULTADOS.includes(resultado)) return null
  const caso: CasoPrueba = { nombre, resultado: resultado as ResultadoPrueba }
  const detalle = texto(o.detalle, PRUEBAS_LIMITES.detalle)
  if (detalle) caso.detalle = detalle
  if (typeof o.evidencia === 'string') {
    const ruta = o.evidencia.trim()
    if ((ruta.startsWith('/') && ruta.length <= PRUEBAS_LIMITES.evidencia) || ID_CAPTURA.test(ruta)) caso.evidencia = ruta
  }
  return caso
}

export function toPruebas(value: unknown): Pruebas | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const o = value as Record<string, unknown>
  const titulo = texto(o.titulo, PRUEBAS_LIMITES.titulo)
  if (!titulo || !Array.isArray(o.casos)) return null
  const casos = o.casos.slice(0, PRUEBAS_LIMITES.casos).map(toCaso).filter((c): c is CasoPrueba => !!c)
  if (!casos.length) return null
  const out: Pruebas = { titulo, casos }
  const resumen = texto(o.resumen, PRUEBAS_LIMITES.resumen)
  if (resumen) out.resumen = resumen
  return out
}

export function conteo(p: Pruebas): Record<ResultadoPrueba, number> {
  const c = { ok: 0, falla: 0, omitida: 0 }
  for (const caso of p.casos) c[caso.resultado]++
  return c
}
