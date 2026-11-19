import type { ColorGrupo, Direccion, NodoTipo } from './diagrama'

/** Everything a diagram view draws, already positioned; the renderer only paints it. */

export type Forma = NodoTipo | 'terminal' | 'actor'
export type Trazo = 'llamada' | 'respuesta' | 'error' | 'datos' | 'si' | 'no' | 'evento'
export type Tono = 'acento' | 'cian' | 'verde' | 'ambar' | 'violeta' | 'rojo' | 'gris' | 'neutro' | 'amarillo'

export interface Caja {
  x: number
  y: number
  w: number
  h: number
}

export interface Etiqueta extends Caja {
  lineas: string[]
}

export interface ENodo extends Caja {
  key: string
  forma: Forma
  tono: Tono
  lineas: string[]
  icono: string
  sub: string
  /** small badge, e.g. the step number */
  num: string
  nombre: string
  detalle: string
  datos: string
  /** what kind of thing this is, in words ("Servicio", "Decisión"…) */
  tipoTexto: string
  grupo: number
  rank: number
}

export interface EArista {
  key: string
  de: string
  a: string
  d: string
  trazo: Trazo
  /** arrowhead polygon; empty when the line has none */
  punta: string
  etiqueta: Etiqueta | null
  num: string
  numPos: { x: number; y: number } | null
  titulo: string
  detalle: string
  datos: string
  /** can be tapped by itself (sequence steps); otherwise it belongs to its nodes */
  propia: boolean
  rank: number
}

export interface EGrupo extends Caja {
  key: string
  nombre: string
  color: ColorGrupo
}

export interface ELinea {
  key: string
  x: number
  y1: number
  y2: number
}

export interface Escena {
  tipo: 'diagrama' | 'secuencia' | 'proceso'
  direccion: Direccion
  w: number
  h: number
  nodos: ENodo[]
  aristas: EArista[]
  grupos: EGrupo[]
  lineas: ELinea[]
  /** for the guided walk: the keys lit at each step */
  pasos: string[][]
}

export type Medir = (texto: string, px: number, peso?: number) => number

const ANCHO: Record<string, number> = {}
for (const c of 'il.,:;|!\'`ı') ANCHO[c] = 0.27
for (const c of 'fjrt()[]{}/\\-') ANCHO[c] = 0.36
for (const c of 'mwMW@%') ANCHO[c] = 0.86
for (const c of '0123456789') ANCHO[c] = 0.56
ANCHO[' '] = 0.27

/** Width estimate that errs a little on the wide side, for tests and before fonts load. */
export const medirAprox: Medir = (texto, px, peso = 400) => {
  let w = 0
  for (const ch of texto) {
    const cp = ch.codePointAt(0) ?? 0
    w += ANCHO[ch] ?? (cp > 0x2000 ? 1.15 : ch !== ch.toLowerCase() ? 0.66 : 0.54)
  }
  return w * px * (peso >= 600 ? 1.05 : 1)
}

/** Greedy word wrap; the last allowed line gets an ellipsis when text is left over. Long words are cut. */
export function envolver(texto: string, maxW: number, px: number, peso: number, medir: Medir, maxLineas = 3): string[] {
  const palabras = texto.split(/\s+/).filter(Boolean)
  const out: string[] = []
  let linea = ''
  const corta = (w: string) => {
    let s = ''
    for (const ch of w) {
      if (medir(s + ch, px, peso) > maxW && s) break
      s += ch
    }
    return s
  }
  for (let i = 0; i < palabras.length; i++) {
    let p = palabras[i]
    const prueba = linea ? `${linea} ${p}` : p
    if (medir(prueba, px, peso) <= maxW) {
      linea = prueba
      continue
    }
    if (linea) {
      out.push(linea)
      linea = ''
    }
    while (medir(p, px, peso) > maxW) {
      const pedazo = corta(p)
      out.push(pedazo)
      p = p.slice(pedazo.length)
      if (out.length >= maxLineas) break
    }
    linea = p
    if (out.length >= maxLineas) break
  }
  if (linea && out.length < maxLineas) out.push(linea)
  const usadas = out.join(' ').replace(/\s+/g, ' ').length
  const total = palabras.join(' ').length
  if (out.length > maxLineas || usadas < total) {
    out.length = Math.min(out.length, maxLineas)
    let ult = out[out.length - 1] ?? ''
    while (ult && medir(`${ult}…`, px, peso) > maxW) ult = ult.slice(0, -1).trimEnd()
    out[out.length - 1] = `${ult}…`
  }
  return out
}

export const anchoLineas = (lineas: string[], px: number, peso: number, medir: Medir) => Math.max(0, ...lineas.map((l) => medir(l, px, peso)))

export const r1 = (n: number) => Math.round(n * 10) / 10

/** Arrowhead triangle with its tip at (x, y) pointing along (dx, dy). */
export function punta(x: number, y: number, dx: number, dy: number, largo = 8, ancho = 4.6): string {
  const n = Math.hypot(dx, dy) || 1
  const ux = dx / n
  const uy = dy / n
  const bx = x - ux * largo
  const by = y - uy * largo
  return `M${r1(x)},${r1(y)}L${r1(bx - uy * ancho)},${r1(by + ux * ancho)}L${r1(bx + uy * ancho)},${r1(by - ux * ancho)}Z`
}

export const solapan = (a: Caja, b: Caja, m = 0) => a.x < b.x + b.w + m && b.x < a.x + a.w + m && a.y < b.y + b.h + m && b.y < a.y + a.h + m
