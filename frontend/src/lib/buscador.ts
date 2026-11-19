import type { Aviso, Board, LibItem } from '../api/types'
import { destinoDeAviso, etiquetaAviso, type AvisoDePieza } from './avisos'
import { estadoEfectivo } from './fondo'

export const ATAJO = typeof navigator !== 'undefined' && /mac|iphone|ipad/i.test(navigator.platform || navigator.userAgent) ? '⌘K' : 'Ctrl K'

export type GrupoId = 'reciente' | 'ir' | 'accion' | 'sesion' | 'tablero' | 'biblioteca' | 'aviso'

export const GRUPOS: Record<GrupoId, string> = {
  reciente: 'Recientes',
  ir: 'Ir a',
  accion: 'Acciones',
  sesion: 'Sesiones y terminales',
  tablero: 'Workspaces y tabs',
  biblioteca: 'Biblioteca',
  aviso: 'Avisos',
}

export type Seccion = 'board' | 'biblioteca' | 'ajustes' | (string & {})
export type AccionId = 'tema' | (string & {})

/** Todo destino es navegar o abrir algo local: ninguno manda mensajes ni cambia estado remoto. */
export type Destino =
  | { t: 'seccion'; s: Seccion }
  | { t: 'accion'; a: AccionId }
  | { t: 'sesion'; id: string }
  | { t: 'terminal'; id: string }
  | { t: 'pane'; id: string }
  | { t: 'biblioteca'; id: string }
  | { t: 'aviso'; id: number }

export type IconoBuscador = 'board' | 'clock' | 'library' | 'chat' | 'grid' | 'sun' | 'sparkle' | 'terminal' | 'pulse' | 'doc' | 'diagrama' | 'image' | 'film' | 'bell' | 'warn' | 'ask' | 'check' | 'calendar'

export interface Entrada {
  id: string
  grupo: GrupoId
  titulo: string
  sub: string
  icono: IconoBuscador
  /** Texto extra que también busca pero no se resalta. */
  claves: string
  destino: Destino
  /** Matiz del ícono (estado de la sesión). */
  tono?: 'working' | 'blocked' | 'done' | 'idle' | 'fondo'
}

export interface Resultado {
  entrada: Entrada
  score: number
  /** Posiciones del título que coincidieron. */
  marcas: number[]
}

/** Una letra por unidad del original (sin tildes ni mayúsculas), así los índices coinciden con el texto mostrado. */
const plegar = (s: string) => s.replace(/[^]/g, (c) => c.normalize('NFD')[0].toLowerCase()[0])

const esSeparador = (c: string) => /[\s\-_./:·()[\]]/.test(c)

export interface Coincidencia {
  score: number
  marcas: number[]
}

/** Subsecuencia difusa, sin tildes ni mayúsculas; premia el inicio, las palabras y las letras seguidas. */
export function fuzzy(consulta: string, texto: string): Coincidencia | null {
  const q = plegar(consulta.trim())
  if (!q) return { score: 0, marcas: [] }
  const t = plegar(texto)
  if (q.length > t.length) return null

  const sub = t.indexOf(q)
  if (sub >= 0) {
    const inicio = sub === 0 || esSeparador(t[sub - 1])
    return { score: 100 + (inicio ? 40 : 0) + (sub === 0 ? 20 : 0) - sub * 0.5 - (t.length - q.length) * 0.1, marcas: Array.from({ length: q.length }, (_, i) => sub + i) }
  }

  // score[i][j]: mejor puntaje con q[i] ubicada en t[j]; `corrida` arrastra el mejor previo con una pequeña pena por salto.
  const n = q.length
  const m = t.length
  const NEG = -1e9
  const score: number[][] = Array.from({ length: n }, () => new Array(m).fill(NEG))
  const prev: number[][] = Array.from({ length: n }, () => new Array(m).fill(-1))
  for (let i = 0; i < n; i++) {
    let valor = NEG
    let desde = -1
    for (let j = 0; j < m; j++) {
      if (i > 0 && j > 0) {
        if (valor > NEG) valor -= 0.6
        if (score[i - 1][j - 1] > valor) ((valor = score[i - 1][j - 1]), (desde = j - 1))
      }
      if (t[j] !== q[i]) continue
      const bono = j === 0 || esSeparador(t[j - 1]) ? 8 : 0
      if (i === 0) score[i][j] = 1 + bono - j * 0.15
      else if (valor > NEG) {
        score[i][j] = valor + 1 + bono + (desde === j - 1 ? 6 : 0)
        prev[i][j] = desde
      }
    }
  }
  let fin = -1
  let top = NEG
  for (let j = 0; j < m; j++) if (score[n - 1][j] > top) ((top = score[n - 1][j]), (fin = j))
  if (fin < 0) return null
  const marcas: number[] = []
  for (let i = n - 1, j = fin; i >= 0; i--) {
    marcas.push(j)
    j = prev[i][j]
  }
  return { score: top, marcas: marcas.reverse() }
}

/** Cada palabra de la consulta tiene que aparecer; el título se resalta y pesa más que las claves. */
export function puntuar(consulta: string, e: Entrada): Resultado | null {
  const palabras = consulta.trim().split(/\s+/).filter(Boolean)
  if (!palabras.length) return { entrada: e, score: 0, marcas: [] }
  let total = 0
  const marcas = new Set<number>()
  for (const p of palabras) {
    const enTitulo = fuzzy(p, e.titulo)
    if (enTitulo) {
      total += enTitulo.score + 10
      enTitulo.marcas.forEach((m) => marcas.add(m))
      continue
    }
    const enResto = fuzzy(p, `${e.sub} ${e.claves}`)
    if (!enResto) return null
    total += enResto.score * 0.5
  }
  return { entrada: e, score: total, marcas: [...marcas].sort((a, b) => a - b) }
}

export interface Seccionado {
  grupo: GrupoId
  titulo: string
  items: Resultado[]
}

export const POR_GRUPO = 6

/** Ordena cada grupo por puntaje y los grupos por su mejor resultado; sin consulta mantiene el orden dado. */
export function buscar(consulta: string, catalogo: Entrada[], porGrupo = POR_GRUPO): Seccionado[] {
  const buscando = consulta.trim().length > 0
  const grupos = new Map<GrupoId, Resultado[]>()
  for (const e of catalogo) {
    const r = puntuar(consulta, e)
    if (!r) continue
    const lista = grupos.get(e.grupo) ?? []
    lista.push(r)
    grupos.set(e.grupo, lista)
  }
  const out: Seccionado[] = []
  for (const [grupo, lista] of grupos) {
    if (buscando) lista.sort((a, b) => b.score - a.score)
    out.push({ grupo, titulo: GRUPOS[grupo], items: lista.slice(0, porGrupo) })
  }
  if (buscando) out.sort((a, b) => b.items[0].score - a.items[0].score)
  return out
}

export const aplanar = (secciones: Seccionado[]): Resultado[] => secciones.flatMap((s) => s.items)

/** Posición del primer elemento del grupo siguiente (o anterior) al de `actual`. */
export function saltoDeGrupo(secciones: Seccionado[], actual: number, dir: 1 | -1): number {
  const inicios: number[] = []
  let n = 0
  for (const s of secciones) {
    inicios.push(n)
    n += s.items.length
  }
  if (!n) return 0
  let g = inicios.length - 1
  while (g > 0 && inicios[g] > actual) g--
  const next = (g + dir + inicios.length) % inicios.length
  return inicios[next]
}

export interface Fuentes {
  board: Board | null
  items: LibItem[]
  avisos: Aviso[]
  tema: 'dark' | 'light'
  piezas?: PiezasCatalogo
}

export interface SeccionCatalogo {
  s: Seccion
  titulo: string
  sub: string
  icono: IconoBuscador
  claves: string
}

/** Lo que suman las piezas montadas al catálogo. */
export interface PiezasCatalogo {
  secciones: SeccionCatalogo[]
  acciones: { id: string; titulo: string; sub: string; icono: IconoBuscador; claves: string }[]
  avisos: (AvisoDePieza & { icono: IconoBuscador })[]
}

const TONO = { working: 'working', blocked: 'blocked', done: 'done', idle: 'idle', fondo: 'fondo' } as const

export const SECCIONES: SeccionCatalogo[] = [
  { s: 'board', titulo: 'Tablero', sub: 'Tus sesiones', icono: 'board', claves: 'inicio sesiones workspaces' },
  { s: 'biblioteca', titulo: 'Biblioteca', sub: 'Lo que publicaron tus sesiones', icono: 'library', claves: 'archivos diagramas secuencias procesos imagenes' },
  { s: 'ajustes', titulo: 'Ajustes', sub: 'Apariencia, avisos, permisos', icono: 'grid', claves: 'configuracion preferencias opciones' },
]

const ICONO_LIB: Record<string, IconoBuscador> = { diagrama: 'diagrama', image: 'image', svg: 'image', gif: 'film', video: 'film', pdf: 'doc', html: 'doc', text: 'doc' }
const KIND_LIB: Record<string, string> = { diagrama: 'Diagrama', image: 'Imagen', svg: 'Imagen', gif: 'Animación', video: 'Video', pdf: 'PDF', html: 'Página', text: 'Texto', remoto: 'Enlace', otro: 'Archivo' }
const ICONO_AVISO: Record<string, IconoBuscador> = { asks: 'ask', blocked: 'warn', done: 'check', terminal: 'terminal', test: 'bell' }

const nombreTab = (label: string) => (/^\d+$/.test(label) ? `Tab ${label}` : label)

export function construirCatalogo(f: Fuentes): Entrada[] {
  const out: Entrada[] = []
  const piezas = f.piezas ?? { secciones: [], acciones: [], avisos: [] }

  const [tablero, ...resto] = SECCIONES
  for (const s of [tablero, ...piezas.secciones, ...resto]) {
    out.push({ id: `sec:${s.s}`, grupo: 'ir', titulo: s.titulo, sub: s.sub, icono: s.icono, claves: s.claves, destino: { t: 'seccion', s: s.s } })
  }
  for (const a of piezas.acciones) {
    out.push({ id: `acc:${a.id}`, grupo: 'accion', titulo: a.titulo, sub: a.sub, icono: a.icono, claves: a.claves, destino: { t: 'accion', a: a.id } })
  }
  out.push(
    { id: 'acc:tema', grupo: 'accion', titulo: 'Cambiar tema', sub: f.tema === 'dark' ? 'Pasar a claro' : 'Pasar a oscuro', icono: 'sun', claves: 'claro oscuro dark light apariencia', destino: { t: 'accion', a: 'tema' } },
  )

  for (const ws of f.board?.workspaces ?? []) {
    const primero = ws.tabs.flatMap((t) => [...t.agents.map((a) => a.pane_id), ...(t.terminales ?? []).map((x) => x.pane_id)])[0]
    out.push({
      id: `ws:${ws.id}`,
      grupo: 'tablero',
      titulo: ws.label,
      sub: `Workspace ${ws.number} · ${ws.tabs.length} ${ws.tabs.length === 1 ? 'tab' : 'tabs'}`,
      icono: 'board',
      claves: '',
      destino: primero ? { t: 'pane', id: primero } : { t: 'seccion', s: 'board' },
      tono: TONO[ws.status as keyof typeof TONO],
    })
    for (const tab of ws.tabs) {
      const agentes = tab.agents.filter((a) => a.pane_id)
      if (tab.label && (ws.tabs.length > 1 || tab.label !== ws.label)) {
        const pane = agentes[0]?.pane_id ?? tab.terminales?.[0]?.pane_id
        if (pane) out.push({ id: `tab:${tab.id}`, grupo: 'tablero', titulo: nombreTab(tab.label), sub: `Tab · ${ws.label}`, icono: 'board', claves: '', destino: { t: 'pane', id: pane } })
      }
      for (const a of agentes) {
        const titulo = a.title || tab.label || 'Sesión'
        out.push({
          id: `ses:${a.session_id ?? a.pane_id}`,
          grupo: 'sesion',
          titulo,
          sub: `${ws.label} · ${nombreTab(tab.label)}`,
          icono: 'pulse',
          claves: `${a.doing} ${a.pending}`.trim(),
          destino: a.session_id ? { t: 'sesion', id: a.session_id } : { t: 'pane', id: a.pane_id },
          tono: TONO[estadoEfectivo(a) as keyof typeof TONO] ?? 'idle',
        })
      }
      for (const x of tab.terminales ?? []) {
        out.push({
          id: `ter:${x.pane_id}`,
          grupo: 'sesion',
          titulo: x.titulo || x.proceso || 'Terminal',
          sub: `Terminal · ${ws.label}`,
          icono: 'terminal',
          claves: `${x.cwd} ${x.proceso}`,
          destino: { t: 'terminal', id: x.pane_id },
        })
      }
    }
  }

  for (const i of f.items) {
    const titulo = i.title || i.nombre || 'Sin título'
    out.push({
      id: `lib:${i.id}`,
      grupo: 'biblioteca',
      titulo,
      sub: `${KIND_LIB[i.kind] ?? 'Archivo'}${i.session_titulo ? ` · ${i.session_titulo}` : ''}`,
      icono: ICONO_LIB[i.kind] ?? 'doc',
      claves: `${i.caption} ${i.description} ${i.project} ${i.nombre}`,
      destino: { t: 'biblioteca', id: i.id },
    })
  }

  const kindsPieza = piezas.avisos.map((p) => p.kind)
  const iconoPieza = Object.fromEntries(piezas.avisos.map((p) => [p.kind, p.icono]))
  for (const a of f.avisos) {
    if (destinoDeAviso(a, kindsPieza).tipo === 'ninguno') continue
    out.push({
      id: `avi:${a.id}`,
      grupo: 'aviso',
      titulo: a.titulo,
      sub: etiquetaAviso(a.kind, piezas.avisos),
      icono: ICONO_AVISO[a.kind] ?? iconoPieza[a.kind] ?? 'bell',
      claves: a.cuerpo,
      destino: { t: 'aviso', id: a.id },
    })
  }
  return out
}

const MAX_RECIENTES = 6

export function sumarReciente(ids: string[], id: string): string[] {
  return [id, ...ids.filter((x) => x !== id)].slice(0, MAX_RECIENTES)
}

/** Recientes que todavía existen en el catálogo, en el orden en que se usaron. */
export function recientesDe(ids: string[], catalogo: Entrada[]): Entrada[] {
  const por = new Map(catalogo.map((e) => [e.id, e]))
  return ids.flatMap((id) => {
    const e = por.get(id)
    return e ? [{ ...e, grupo: 'reciente' as const }] : []
  })
}

/** Sin consulta: recientes arriba y, debajo, las secciones y acciones para arrancar. */
export function inicial(catalogo: Entrada[], recientes: string[]): Seccionado[] {
  const rec = recientesDe(recientes, catalogo)
  const base = buscar('', catalogo.filter((e) => e.grupo === 'ir' || e.grupo === 'accion'))
  const salida: Seccionado[] = []
  if (rec.length) salida.push({ grupo: 'reciente', titulo: GRUPOS.reciente, items: rec.map((entrada) => ({ entrada, score: 0, marcas: [] })) })
  const vistos = new Set(rec.map((e) => e.id))
  for (const s of base) {
    const items = s.items.filter((r) => !vistos.has(r.entrada.id))
    if (items.length) salida.push({ ...s, items })
  }
  return salida
}

/** Parte un título en tramos marcados/no marcados para resaltar las letras que coinciden. */
export function tramos(texto: string, marcas: number[]): { t: string; on: boolean }[] {
  if (!marcas.length) return [{ t: texto, on: false }]
  const on = new Set(marcas)
  const chars = texto.split('')
  const out: { t: string; on: boolean }[] = []
  chars.forEach((c, i) => {
    const m = on.has(i)
    const last = out[out.length - 1]
    if (last && last.on === m) last.t += c
    else out.push({ t: c, on: m })
  })
  return out
}
