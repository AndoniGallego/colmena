import type { LibFilters, LibItem, LibKind } from '../api/types'
import { lenientJson } from './fence'
import { toDiagrama, type Diagrama } from './diagrama'
import { toPruebas, type Pruebas } from './pruebas'
import { toReunion, type ReunionGuardada } from './reunion'

export const ITEM_ID = /^[0-9a-f]{32}$/
/** El token del visor dura 30 minutos: se pide uno nuevo a los 25. */
export const TOKEN_RENEW_MS = 25 * 60_000

export function parseLibLink(search: string): { id: string | null } | null {
  const params = new URLSearchParams(search)
  if (!params.has('biblioteca')) return null
  const value = params.get('biblioteca') ?? ''
  if (!value) return { id: null }
  return ITEM_ID.test(value) ? { id: value } : null
}

export const emptyFilters = (): LibFilters => ({ tipo: [], session: '', desde: '', hasta: '', q: '' })

export const isFiltering = (f: LibFilters) => !!(f.tipo.length || f.session || f.desde || f.hasta || f.q.trim())

export function libQuery(f: LibFilters, cursor?: string | null, limit?: number): string {
  const p = new URLSearchParams()
  if (f.tipo.length) p.set('tipo', f.tipo.join(','))
  if (f.session) p.set('session', f.session)
  if (f.desde) p.set('desde', f.desde)
  if (f.hasta) p.set('hasta', f.hasta)
  if (f.q.trim()) p.set('q', f.q.trim().slice(0, 100))
  if (cursor) p.set('cursor', cursor)
  if (limit) p.set('limit', String(limit))
  return p.toString()
}

const byNewest = (a: LibItem, b: LibItem) => (a.ts === b.ts ? (a.id < b.id ? 1 : -1) : a.ts < b.ts ? 1 : -1)

/** Appends a page without repeating what the list already has. */
export function mergePage(current: LibItem[], page: LibItem[]): LibItem[] {
  const seen = new Set(current.map((i) => i.id))
  return [...current, ...page.filter((i) => !seen.has(i.id))]
}

/** SSE `nuevos`: the fresh ones replace stale copies and land in date order. */
export function insertNuevos(current: LibItem[], fresh: LibItem[]): LibItem[] {
  const ids = new Set(fresh.map((i) => i.id))
  return [...fresh, ...current.filter((i) => !ids.has(i.id))].sort(byNewest)
}

const fold = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

export function matchesFilters(item: LibItem, f: LibFilters): boolean {
  if (f.tipo.length && !f.tipo.includes(item.kind)) return false
  if (f.session && item.session_id !== f.session) return false
  const day = item.ts.slice(0, 10)
  if (f.desde && day < f.desde) return false
  if (f.hasta && day > f.hasta) return false
  const q = fold(f.q.trim())
  if (q && !fold([item.title, item.description, item.caption, item.nombre, item.session_titulo].join(' ')).includes(q)) return false
  return true
}

export const needsRenewal = (fetchedAt: number, now: number) => now - fetchedAt >= TOKEN_RENEW_MS

export interface TypeGroup {
  key: string
  label: string
  tipo: LibKind[]
}

export const TYPE_GROUPS: TypeGroup[] = [
  { key: '1', label: 'Todo', tipo: [] },
  { key: '2', label: 'Páginas', tipo: ['html'] },
  { key: '3', label: 'Imágenes', tipo: ['image', 'svg', 'gif'] },
  { key: '4', label: 'PDF', tipo: ['pdf'] },
  { key: '5', label: 'Diagramas', tipo: ['diagrama'] },
  { key: '6', label: 'Otros', tipo: ['text', 'video', 'remoto', 'otro'] },
  { key: '7', label: 'Pruebas', tipo: ['pruebas'] },
  { key: '8', label: 'Reuniones', tipo: ['reunion'] },
]

export const groupIndex = (tipo: LibKind[]) =>
  Math.max(0, TYPE_GROUPS.findIndex((g) => g.tipo.length === tipo.length && g.tipo.every((t) => tipo.includes(t))))

export type ShortcutAction =
  | 'search' | 'left' | 'right' | 'up' | 'down' | 'enter' | 'quick' | 'prev' | 'next' | 'fullscreen'
  | 'escape' | 'quitar' | 'claude' | 'session' | 'copy' | 'reload' | 'toggleView' | 'help'
  | `type${1 | 2 | 3 | 4 | 5 | 6 | 7 | 8}`

const KEYS: Record<string, ShortcutAction> = {
  '/': 'search',
  ArrowLeft: 'left', h: 'left',
  ArrowRight: 'right', l: 'right',
  ArrowUp: 'up', k: 'up',
  ArrowDown: 'down', j: 'down',
  Enter: 'enter',
  ' ': 'quick',
  '[': 'prev',
  ']': 'next',
  f: 'fullscreen',
  Escape: 'escape',
  Delete: 'quitar',
  o: 'claude',
  s: 'session',
  c: 'copy',
  r: 'reload',
  g: 'toggleView',
  '?': 'help',
  '1': 'type1', '2': 'type2', '3': 'type3', '4': 'type4', '5': 'type5', '6': 'type6', '7': 'type7', '8': 'type8',
}

export interface KeyInfo {
  key: string
  ctrlKey?: boolean
  metaKey?: boolean
  altKey?: boolean
}

/** Keys act only outside fields and without modifiers; Esc also works from the search box. */
export function shortcutFor(e: KeyInfo, typing: boolean): ShortcutAction | null {
  if (e.ctrlKey || e.metaKey || e.altKey) return null
  const action = KEYS[e.key.length === 1 ? e.key.toLowerCase() : e.key] ?? null
  if (typing) return action === 'escape' ? action : null
  return action
}

export const isTyping = (el: Element | null) =>
  !!el && (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement || el instanceof HTMLSelectElement || (el as HTMLElement).isContentEditable)

export type CardVariant = 'cover' | 'image' | 'video' | 'diagrama' | 'pruebas' | 'reunion' | 'doc' | 'remoto' | 'gone'

export function cardVariant(item: LibItem): CardVariant {
  if (item.kind === 'remoto') return 'remoto'
  if (item.kind === 'diagrama') return 'diagrama'
  if (item.kind === 'pruebas') return 'pruebas'
  if (item.kind === 'reunion') return 'reunion'
  if (!item.exists && !item.copia) return 'gone'
  if (item.kind === 'html') return item.servible ? 'cover' : 'doc'
  if (item.kind === 'image' || item.kind === 'gif' || item.kind === 'svg') return item.servible ? 'image' : 'doc'
  if (item.kind === 'video') return item.servible ? 'video' : 'doc'
  return 'doc'
}

/** The diagram behind a library item; the parser may reject a block the indexer accepted, so the caller shows a fallback on `null`. */
export function diagramaOf(item: LibItem, convert: (raw: unknown) => Diagrama | null = toDiagrama): Diagrama | null {
  return item.kind === 'diagrama' && item.diagrama_raw ? convert(lenientJson(item.diagrama_raw)) : null
}

/** The test report behind a library item; null when it is missing or unreadable, so the caller shows a fallback. */
export function pruebasOf(item: LibItem): Pruebas | null {
  if (item.kind !== 'pruebas' || !item.pruebas_raw) return null
  try {
    return toPruebas(JSON.parse(item.pruebas_raw))
  } catch {
    return null
  }
}

/** The saved meeting behind a library item; null when it is missing or unreadable, so the caller shows a fallback. */
export function reunionOf(item: LibItem): ReunionGuardada | null {
  if (item.kind !== 'reunion' || !item.reunion_raw) return null
  return toReunion(item.reunion_raw)
}

export const KIND_LABEL: Record<LibKind, string> = {
  html: 'Página',
  image: 'Imagen',
  svg: 'SVG',
  gif: 'GIF',
  pdf: 'PDF',
  video: 'Video',
  text: 'Texto',
  diagrama: 'Diagrama',
  pruebas: 'Pruebas',
  reunion: 'Reunión',
  remoto: 'Solo en claude.ai',
  otro: 'Archivo',
}

export function dayKey(ts: string): string {
  const t = Date.parse(ts)
  if (Number.isNaN(t)) return 'sin-fecha'
  const d = new Date(t)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function dayLabel(key: string, now: number): string {
  if (key === 'sin-fecha') return 'Sin fecha'
  const today = dayKey(new Date(now).toISOString())
  const yesterday = dayKey(new Date(now - 86_400_000).toISOString())
  if (key === today) return 'Hoy'
  if (key === yesterday) return 'Ayer'
  const [y, m, d] = key.split('-').map(Number)
  const label = new Intl.DateTimeFormat('es-AR', { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date(y, m - 1, d))
  return label.charAt(0).toUpperCase() + label.slice(1)
}

export interface DayGroup {
  key: string
  label: string
  items: LibItem[]
}

export function groupByDay(items: LibItem[], now: number): DayGroup[] {
  const out: DayGroup[] = []
  for (const item of items) {
    const key = dayKey(item.ts)
    const last = out[out.length - 1]
    if (last?.key === key) last.items.push(item)
    else out.push({ key, label: dayLabel(key, now), items: [item] })
  }
  return out
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/** Gradient seed from the id, so a cover looks the same every time. */
export function coverHues(id: string): [number, number] {
  let h = 0
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0
  return [h % 360, (h >>> 9) % 360]
}

export type ViewerKind = 'frame' | 'image' | 'video' | 'pdf' | 'text' | 'diagrama' | 'pruebas' | 'reunion' | 'remote' | 'gone'

export function viewerKind(item: LibItem): ViewerKind {
  if (item.kind === 'remoto') return 'remote'
  if (item.kind === 'diagrama') return 'diagrama'
  if (item.kind === 'pruebas') return 'pruebas'
  if (item.kind === 'reunion') return 'reunion'
  if (!item.servible) return 'gone'
  if (item.kind === 'html' || item.kind === 'svg') return 'frame'
  if (item.kind === 'image' || item.kind === 'gif') return 'image'
  if (item.kind === 'video') return 'video'
  if (item.kind === 'pdf') return 'pdf'
  return item.kind === 'text' ? 'text' : 'gone'
}

/** Neighbours in the loaded list, so the viewer can step without asking the server. */
export function neighbours(items: LibItem[], id: string): { prev: LibItem | null; next: LibItem | null } {
  const i = items.findIndex((x) => x.id === id)
  if (i < 0) return { prev: null, next: null }
  return { prev: items[i - 1] ?? null, next: items[i + 1] ?? null }
}

const CLAUDE_URL = /^https:\/\/claude\.ai\/(artifact|code\/artifact)\/[A-Za-z0-9-]{8,64}$/

/** Only a well-formed claude.ai artifact link becomes clickable. */
export const safeClaudeUrl = (url: string): string => (CLAUDE_URL.test(url) ? url : '')

export const pathLabel = (item: LibItem): string =>
  item.donde.startsWith('~') ? item.donde : item.donde ? `${item.donde}/${item.nombre}` : item.nombre

/** Library item of each diagram block in a message, by matching title and then by order; null when there is none. */
export function libIdsPorDiagrama(titulos: string[], items: Pick<LibItem, 'id' | 'kind' | 'title'>[]): (string | null)[] {
  const libres = items.filter((i) => i.kind === 'diagrama')
  const out: (string | null)[] = titulos.map((t) => {
    const at = libres.findIndex((i) => i.title === t)
    return at >= 0 ? libres.splice(at, 1)[0].id : null
  })
  return out.map((id) => id ?? libres.shift()?.id ?? null)
}

export const MAX_QUITAR = 500

/** The server takes at most 500 ids per call. */
export function chunkIds(ids: string[], size = MAX_QUITAR): string[][] {
  const out: string[][] = []
  for (let i = 0; i < ids.length; i += size) out.push(ids.slice(i, i + size))
  return out
}

export function removeIds(items: LibItem[], ids: string[]): LibItem[] {
  const gone = new Set(ids)
  return items.filter((i) => !gone.has(i.id))
}

/** Click on a card in select mode: with Shift, everything between the last pick and this one. */
export function pickIds(current: string[], order: string[], id: string, last: string | null, range: boolean): string[] {
  const set = new Set(current)
  const a = last ? order.indexOf(last) : -1
  const b = order.indexOf(id)
  if (range && a >= 0 && b >= 0) {
    const [from, to] = a < b ? [a, b] : [b, a]
    const on = !set.has(id)
    for (const x of order.slice(from, to + 1)) on ? set.add(x) : set.delete(x)
  } else if (set.has(id)) set.delete(id)
  else set.add(id)
  return order.filter((x) => set.has(x))
}

export const quitarLabel = (n: number) => `Quitar ${n}`
export const quitadoToast = (n: number) => (n === 1 ? 'Quitado de la Biblioteca' : `${n} quitados de la Biblioteca`)
