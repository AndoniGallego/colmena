import { toPasos, type DiagramaPasos } from './pasos'

export type NodoTipo = 'caja' | 'persona' | 'app' | 'servicio' | 'datos' | 'externo' | 'nota' | 'decision'
export type ConexionTipo = 'llamada' | 'respuesta' | 'error' | 'datos'
export type Direccion = 'horizontal' | 'vertical'
export type ColorGrupo = 'verde' | 'azul' | 'ambar' | 'rojo' | 'violeta' | 'gris' | 'lima' | 'rosa'

export interface Grupo {
  id: string
  nombre: string
  color: ColorGrupo
}

export interface Nodo {
  id: string
  nombre: string
  icono: string
  detalle: string
  /** index into `grupos`, or -1 */
  grupo: number
  tipo: NodoTipo
}

export interface Conexion {
  /** indexes into `nodos` */
  de: number
  a: number
  texto: string
  tipo: ConexionTipo
}

export interface DiagramaEstructura {
  tipo: 'estructura'
  titulo: string
  resumen: string
  direccion: Direccion | null
  grupos: Grupo[]
  nodos: Nodo[]
  conexiones: Conexion[]
  notas: string[]
}

export const MAX_NODOS = 40
export const MAX_CONEXIONES = 80
export const MAX_GRUPOS = 12
export const MAX_NOTAS = 6
export const LIM = { titulo: 100, resumen: 300, nombre: 60, id: 32, detalle: 400, texto: 80, nota: 200, grupo: 40 }

const TIPOS_NODO: NodoTipo[] = ['persona', 'app', 'servicio', 'datos', 'externo', 'nota', 'decision']
const TIPOS_CONEXION: ConexionTipo[] = ['llamada', 'respuesta', 'error', 'datos']
const PALETA: ColorGrupo[] = ['azul', 'verde', 'violeta', 'ambar', 'rosa', 'lima', 'gris', 'rojo']
const ALIAS: Record<string, ColorGrupo> = {
  verde: 'verde', green: 'verde',
  azul: 'azul', blue: 'azul', celeste: 'azul', cyan: 'azul', cian: 'azul',
  ambar: 'ambar', ámbar: 'ambar', amber: 'ambar', naranja: 'ambar', orange: 'ambar', amarillo: 'ambar', yellow: 'ambar',
  rojo: 'rojo', red: 'rojo',
  violeta: 'violeta', violet: 'violeta', purple: 'violeta', morado: 'violeta', lila: 'violeta',
  gris: 'gris', gray: 'gris', grey: 'gris',
  lima: 'lima', lime: 'lima', acento: 'lima',
  rosa: 'rosa', pink: 'rosa', magenta: 'rosa',
}

const clean = (s: string) => s.replace(/[\u0000-\u0008\u000b-\u001f\u007f‪-‮⁦-⁩]/g, '').replace(/\s+/g, ' ').trim()

export const clip = (v: unknown, max: number) => {
  const t = typeof v === 'string' ? clean(v) : typeof v === 'number' && Number.isFinite(v) ? String(v) : ''
  return t.length > max ? `${t.slice(0, max - 1).trimEnd()}…` : t
}

const obj = (v: unknown): Record<string, unknown> | null => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null)

let seg: Intl.Segmenter | null | undefined
/** First grapheme when it is an emoji (keeps ZWJ sequences and flags whole); anything else is not an icon. */
export function iconoDe(v: unknown): string {
  const t = typeof v === 'string' ? v.trim() : ''
  if (!t) return ''
  if (seg === undefined) seg = typeof Intl !== 'undefined' && 'Segmenter' in Intl ? new Intl.Segmenter(undefined, { granularity: 'grapheme' }) : null
  const first = seg ? (seg.segment(t)[Symbol.iterator]().next().value?.segment ?? '') : Array.from(t)[0] ?? ''
  if (first.length > 16 || !/[\p{Extended_Pictographic}\p{Regional_Indicator}]/u.test(first)) return ''
  return first
}

/** Strict normalization: unknown fields are dropped, every string is clipped, ids must resolve; null when nothing drawable is left. */
export function toEstructura(value: unknown): DiagramaEstructura | null {
  const o = obj(value)
  if (!o || !Array.isArray(o.nodos)) return null

  const grupos: Grupo[] = []
  if (Array.isArray(o.grupos)) {
    for (const raw of o.grupos) {
      const r = obj(raw)
      const id = clip(r?.id, LIM.id)
      if (!r || !id || grupos.some((g) => g.id === id)) continue
      const pedido = typeof r.color === 'string' ? ALIAS[r.color.trim().toLowerCase()] : undefined
      grupos.push({ id, nombre: clip(r.nombre, LIM.grupo) || id, color: pedido ?? PALETA[grupos.length % PALETA.length] })
      if (grupos.length === MAX_GRUPOS) break
    }
  }

  const nodos: Nodo[] = []
  for (const raw of o.nodos) {
    const r = obj(raw)
    const id = clip(r?.id, LIM.id)
    if (!r || !id || nodos.some((n) => n.id === id)) continue
    const nombre = clip(r.nombre, LIM.nombre) || id
    const tipo = TIPOS_NODO.includes(r.tipo as NodoTipo) ? (r.tipo as NodoTipo) : 'caja'
    const g = clip(r.grupo, LIM.id)
    nodos.push({ id, nombre, icono: iconoDe(r.icono), detalle: clip(r.detalle, LIM.detalle), grupo: g ? grupos.findIndex((x) => x.id === g) : -1, tipo })
    if (nodos.length === MAX_NODOS) break
  }
  if (!nodos.length) return null

  const conexiones: Conexion[] = []
  const vistas = new Set<string>()
  for (const raw of Array.isArray(o.conexiones) ? o.conexiones : []) {
    const r = obj(raw)
    if (!r) continue
    const de = nodos.findIndex((n) => n.id === clip(r.de, LIM.id))
    const a = nodos.findIndex((n) => n.id === clip(r.a, LIM.id))
    if (de < 0 || a < 0 || de === a) continue
    const texto = clip(r.texto, LIM.texto)
    const clave = `${de}>${a}>${texto}`
    if (vistas.has(clave)) continue
    vistas.add(clave)
    conexiones.push({ de, a, texto, tipo: TIPOS_CONEXION.includes(r.tipo as ConexionTipo) ? (r.tipo as ConexionTipo) : 'llamada' })
    if (conexiones.length === MAX_CONEXIONES) break
  }

  const direccion = o.direccion === 'horizontal' || o.direccion === 'vertical' ? o.direccion : null
  const notas = (Array.isArray(o.notas) ? o.notas : []).map((n) => clip(n, LIM.nota)).filter(Boolean).slice(0, MAX_NOTAS)
  const usados = new Set(nodos.map((n) => n.grupo).filter((g) => g >= 0))
  // groups nobody belongs to are dropped and the indexes remapped
  const vivos = grupos.map((_, i) => i).filter((i) => usados.has(i))
  const remap = new Map(vivos.map((g, k) => [g, k]))
  for (const n of nodos) n.grupo = n.grupo >= 0 ? (remap.get(n.grupo) ?? -1) : -1
  return {
    tipo: 'estructura',
    titulo: clip(o.titulo, LIM.titulo),
    resumen: clip(o.resumen, LIM.resumen),
    direccion,
    grupos: vivos.map((i) => grupos[i]),
    nodos,
    conexiones,
    notas,
  }
}

export type TipoDiagrama = 'estructura' | 'secuencia' | 'proceso'

/** Boxes and arrows ("estructura", the default), actors exchanging messages ("secuencia") or steps with yes/no decisions ("proceso"). */
export type Diagrama = DiagramaEstructura | DiagramaPasos

export const TIPOS_DIAGRAMA: TipoDiagrama[] = ['estructura', 'secuencia', 'proceso']

/** A ```diagrama body: "tipo" picks the shape; without it (or with "estructura") it is boxes and arrows. */
export function toDiagrama(value: unknown): Diagrama | null {
  const o = obj(value)
  if (!o) return null
  if (o.tipo === 'secuencia' || o.tipo === 'proceso') return toPasos(o)
  if (o.tipo !== undefined && o.tipo !== 'estructura') return null
  return toEstructura(o)
}
