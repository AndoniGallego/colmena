import type { Pieza } from './tipos'

export type { Pieza } from './tipos'

const mods = import.meta.glob<{ default: Pieza }>('./*/pieza.ts', { eager: true })

const NOMBRE = /^[a-z]{1,20}$/
/** Ids y kinds del núcleo: una pieza no los puede pisar. */
const VISTAS_BASE = new Set(['board', 'mrs', 'notas', 'biblioteca', 'ajustes'])
const KINDS_BASE = new Set(['asks', 'blocked', 'done', 'terminal', 'cierre', 'encadenar', 'vigia', 'mr', 'entorno', 'test', 'progreso', 'pestana', 'cerrar'])
const PREFS_BASE = new Set(['asks', 'blocked', 'done', 'texto', 'cierre', 'mrs', 'entornos', 'progreso', 'pestana'])

const esObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object'
const esFn = (v: unknown) => typeof v === 'function'
const esTexto = (v: unknown) => typeof v === 'string' && v.length > 0

function problema(p: Record<string, unknown>): string {
  if (!esTexto(p.id) || !NOMBRE.test(p.id as string) || VISTAS_BASE.has(p.id as string)) return 'id inválido'
  const s = p.seccion
  if (s !== undefined && (!esObj(s) || !esTexto(s.titulo) || !esTexto(s.icono) || !s.vista || !esObj(s.visible) || !('value' in s.visible))) return 'sección inválida'
  const a = p.avisos
  if (a !== undefined && (!esObj(a) || !esTexto(a.kind) || !NOMBRE.test(a.kind as string) || KINDS_BASE.has(a.kind as string) || !esTexto(a.etiqueta) || !esFn(a.abierto) || !esFn(a.ir))) return 'avisos inválidos'
  const n = p.notificaciones
  if (n !== undefined) {
    if (!esObj(n) || !esObj(n.pref) || !esTexto(n.pref.key) || !NOMBRE.test(n.pref.key as string) || PREFS_BASE.has(n.pref.key as string) || !esFn(n.probar) || !esObj(n.filaPrueba)) return 'notificaciones inválidas'
  }
  for (const k of ['init', 'alEntrar', 'mock'] as const) if (p[k] !== undefined && !esFn(p[k])) return `${k} no es una función`
  return ''
}

/** Valida y ordena las piezas encontradas; descarta (y avisa) las que no cumplen el contrato. */
export function validarPiezas(encontradas: Record<string, { default?: unknown }>, avisar: (msg: string) => void = console.warn): Pieza[] {
  const out: Pieza[] = []
  const usados = new Set<string>()
  for (const ruta of Object.keys(encontradas).sort()) {
    const p = encontradas[ruta]?.default
    const mal = esObj(p) ? problema(p) : 'sin export default'
    if (mal) {
      avisar(`Pieza ${ruta} descartada: ${mal}`)
      continue
    }
    const pieza = p as unknown as Pieza
    const claves = [`id:${pieza.id}`, ...(pieza.avisos ? [`kind:${pieza.avisos.kind}`] : []), ...(pieza.notificaciones ? [`pref:${pieza.notificaciones.pref.key}`] : [])]
    const repetida = claves.find((c) => usados.has(c))
    if (repetida) {
      avisar(`Pieza ${ruta} descartada: ${repetida} repetido`)
      continue
    }
    for (const c of claves) usados.add(c)
    out.push(pieza)
  }
  return out
}

let cache: Pieza[] | null = null

/** Se calcula en la primera llamada: una pieza puede importar módulos que a su vez leen el registro. */
export function piezas(): Pieza[] {
  return (cache ??= validarPiezas(mods))
}

/** Corre un gancho de la pieza; si tira (o rechaza), lo reporta con el id de la pieza y deja seguir al núcleo. */
export async function correrGancho(
  pieza: { id: string } & Partial<Record<'init' | 'alEntrar' | 'mock', () => unknown>>,
  gancho: 'init' | 'alEntrar' | 'mock',
  reportar: (msg: string, err: unknown) => void = (m, e) => console.error(m, e),
): Promise<void> {
  try {
    await pieza[gancho]?.()
  } catch (e) {
    reportar(`Pieza ${pieza.id}: falló ${gancho}`, e)
  }
}
