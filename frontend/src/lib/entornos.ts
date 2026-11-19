import type { Entorno, EstadoServicio, PuertoEntorno, SaludEntorno, ServicioEntorno } from '../api/entornosApi'
import type { EstadoTunel } from './entornosPuente'

export type FaseTunel = 'cerrado' | 'abriendo' | 'abierto' | 'error'

export interface VistaTunel {
  fase: FaseTunel
  error: string | null
}

export interface EstadoVista {
  tuneles: Record<string, EstadoTunel>
  abriendo: readonly string[]
  errores: Record<string, string>
}

export function faseDe(nombre: string, s: EstadoVista): VistaTunel {
  if (s.abriendo.includes(nombre)) return { fase: 'abriendo', error: null }
  const errGlobal = s.errores[nombre]
  if (errGlobal !== undefined) return { fase: 'error', error: errGlobal }
  const t = s.tuneles[nombre]
  if (t?.estado === 'abierto') return { fase: 'abierto', error: null }
  if (t?.estado === 'error') return { fase: 'error', error: t.error }
  return { fase: 'cerrado', error: null }
}

export const NO_LLEGO = 'No llego a la notebook. ¿Estás en la red de casa y la dirección es la correcta?'

export { mensajeErrorRed } from './errores'

export function explicarError(error: string): { texto: string; original: string | null } {
  if (
    error.includes('Permission denied') ||
    error.includes('Connection timed out') ||
    error.includes('No route to host') ||
    error.includes('Connection refused') ||
    error.includes('Could not resolve hostname')
  ) {
    return { texto: NO_LLEGO, original: error }
  }
  return { texto: error, original: null }
}

export function puertosTunel(e: Entorno): number[] {
  return e.puertos
    .filter((p) => p.abrible)
    .map((p) => p.puerto)
    .sort((a, b) => a - b)
}

export function conEnlace(p: PuertoEntorno, v: VistaTunel, t?: EstadoTunel): boolean {
  if (v.fase !== 'abierto' || !p.abrible || !t) return false
  return t.puertos.includes(p.puerto)
}

export function haceTexto(s: number | null): string {
  if (s === null) return ''
  if (s < 60) return 'hace segundos'
  if (s < 3600) return `hace ${Math.floor(s / 60)} min`
  if (s < 86400) return `hace ${Math.floor(s / 3600)} h`
  const d = Math.floor(s / 86400)
  return d === 1 ? 'hace 1 día' : `hace ${d} días`
}

const ETIQUETA_ESTADO: Record<EstadoServicio, string> = {
  corriendo: 'Corriendo',
  arrancando: 'Arrancando',
  enfermo: 'Con problemas',
  reiniciando: 'Reiniciándose',
  pausado: 'En pausa',
  caido: 'Caído',
  terminado: 'Terminó',
}

export function etiquetaEstado(estado: EstadoServicio): string {
  return ETIQUETA_ESTADO[estado]
}

export function ariaSalud(salud: SaludEntorno): string | null {
  if (salud === 'verde') return 'Salud: todo bien'
  if (salud === 'amarillo') return 'Salud: con problemas'
  if (salud === 'rojo') return 'Salud: caído'
  return null
}

export function serviciosConProblema(servicios: ServicioEntorno[]): ServicioEntorno[] {
  return servicios.filter((s) => s.estado !== 'corriendo' && s.estado !== 'terminado')
}

export function lineaServicioProblema(s: ServicioEntorno): string {
  let t = `${s.servicio} · ${etiquetaEstado(s.estado)}`
  const hace = haceTexto(s.hace_s)
  if (hace) t += ` · ${hace}`
  if (s.codigo !== null && s.codigo !== 0) t += ` · código ${s.codigo}`
  return t
}

export function esMetodoQueCambia(m: string): boolean {
  return m === 'POST' || m === 'PUT' || m === 'PATCH' || m === 'DELETE'
}

export function cuerpoLegible(cuerpo: string | null): string {
  if (cuerpo === null) return ''
  try {
    return JSON.stringify(JSON.parse(cuerpo), null, 2)
  } catch {
    return cuerpo
  }
}

export function claseCodigo(n: number): 'ok' | 'aviso' | 'mal' {
  if (n >= 200 && n < 300) return 'ok'
  if (n >= 300 && n < 400) return 'aviso'
  return 'mal'
}

export function resumenEntornos(
  nombres: string[],
  s: EstadoVista,
): { total: number; abiertos: number; texto: string } {
  const total = nombres.length
  const abiertos = nombres.filter((n) => faseDe(n, s).fase === 'abierto').length
  if (total === 0) return { total: 0, abiertos: 0, texto: '' }
  const tEnt =
    total === 1 ? '1 entorno' : `${total} entornos`
  const tAbi = abiertos === 1 ? '1 abierto' : `${abiertos} abiertos`
  return { total, abiertos, texto: `${tEnt} · ${tAbi}` }
}
