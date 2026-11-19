import { lenientJson } from './fence'
import { toDiagrama, type Diagrama } from './diagrama'
import { diagramaLegado, fenceCanonico, LEGACY_FENCE } from './legado'
import { toOpciones, type Opciones } from './opciones'
import { toAvisoRef, type AvisoRef } from './avisoCard'
import { toPreguntaRef, type PreguntaRef } from './preguntaCard'
import { toEstado, type Estado } from './estado'
import { toPruebas, type Pruebas } from './pruebas'
import { toComando, type Comando } from './comando'

export type Segment =
  | { type: 'md'; text: string }
  | { type: 'opciones'; data: Opciones }
  | { type: 'diagrama'; data: Diagrama }
  | { type: 'pregunta'; data: PreguntaRef }
  | { type: 'aviso'; data: AvisoRef }
  | { type: 'estado'; data: Estado }
  | { type: 'pruebas'; data: Pruebas }
  | { type: 'comando'; data: Comando }
  | { type: 'pending'; kind: string }

type Valor = Opciones | Diagrama | PreguntaRef | AvisoRef | Estado | Pruebas | Comando
const CONVERT: Record<string, (v: unknown) => Valor | null> = {
  opciones: toOpciones,
  diagrama: toDiagrama,
  pregunta: toPreguntaRef,
  aviso: toAvisoRef,
  estado: toEstado,
  pruebas: toPruebas,
  comando: toComando,
  [LEGACY_FENCE]: diagramaLegado,
}

const TIPOS = new RegExp(`^(opciones|diagrama|pregunta|aviso|estado|pruebas|comando|${LEGACY_FENCE})\\b`, 'i')

/** Tramos [inicio, fin) de los bloques de código comunes (```, ````, ~~~ sin tipo de tarjeta); igual que
 * comando_sesion.zonas_codigo en el backend. Los bloques de tarjeta se saltean enteros. */
export function zonasCodigo(text: string): [number, number][] {
  const zonas: [number, number][] = []
  let abierto: { ch: string; n: number; inicio: number; comun: boolean } | null = null
  let pos = 0
  for (const linea of text.split('\n')) {
    const inicio = pos
    pos += linea.length + 1
    if (!abierto) {
      const m = /^( {0,3})(`{3,}|~{3,})[ \t]*(.*)$/.exec(linea)
      if (m && !(m[2][0] === '`' && m[3].includes('`'))) abierto = { ch: m[2][0], n: m[2].length, inicio, comun: !TIPOS.test(m[3]) }
      continue
    }
    const m = /^[ \t]*(`{3,}|~{3,})[ \t]*$/.exec(linea)
    if (m && m[1][0] === abierto.ch && m[1].length >= abierto.n) {
      if (abierto.comun) zonas.push([abierto.inicio, pos])
      abierto = null
    }
  }
  if (abierto?.comun) zonas.push([abierto.inicio, text.length])
  return zonas
}

const sangria = (s: string) => s.replace(/\t/g, '    ').length

/** Splits a message into markdown and card segments, in order, for any number of ```opciones / ```diagrama blocks. */
export function parseSegments(text: string, streaming = false): Segment[] {
  const out: Segment[] = []
  const md = (s: string) => {
    const t = s.trim()
    if (t) out.push({ type: 'md', text: t })
  }
  const open = new RegExp(`(^|\\n)[ \\t]*(\`{3,}|~{3,})[ \\t]*(opciones|diagrama|pregunta|aviso|estado|pruebas|comando|${LEGACY_FENCE})\\b[^\\n]*\\n`, 'gi')
  let mdStart = 0
  let pos = 0
  let zonas: [number, number][] | null = null
  for (;;) {
    open.lastIndex = pos
    const m = open.exec(text)
    if (!m) break
    const fuente = m[3].toLowerCase()
    if (fuente === 'comando') {
      // Citado dentro de otro bloque de código o con sangría de código: no es un pedido (como en el backend).
      const inicio = m.index + m[1].length
      zonas ??= zonasCodigo(text)
      const fenceAt = m.index + m[0].indexOf(m[2], m[1].length)
      if (sangria(text.slice(inicio, fenceAt)) >= 4 || zonas.some(([a, b]) => a <= inicio && inicio < b)) {
        pos = m.index + m[0].length - 1
        continue
      }
    }
    const kind = fenceCanonico(fuente)
    const fence = m[2]
    const start = m.index + m[1].length
    const bodyStart = m.index + m[0].length
    const close = new RegExp(`\\n[ \\t]*${fence[0] === '`' ? '`' : '~'}{${fence.length},}[ \\t]*(?=\\n|$)`, 'g')
    close.lastIndex = bodyStart - 1
    const c = close.exec(text)
    const push = (value: Valor | null) => {
      if (!value) return false
      md(text.slice(mdStart, start))
      out.push({ type: kind, data: value } as Segment)
      return true
    }
    if (!c) {
      if (streaming) {
        md(text.slice(mdStart, start))
        out.push({ type: 'pending', kind })
        return out
      }
      if (push(CONVERT[fuente](lenientJson(text.slice(bodyStart))))) return out
      break
    }
    const end = c.index + c[0].length
    if (push(CONVERT[fuente](lenientJson(text.slice(bodyStart, Math.max(bodyStart, c.index)))))) mdStart = end
    pos = end
  }
  md(text.slice(mdStart))
  return out
}

export const cardCount = (segs: Segment[]) => segs.filter((s) => s.type === 'opciones').length
