import type { Agent, Workspace } from '../api/types'
import { enSegundoPlano } from './fondo'

export type AttentionKind = 'blocked' | 'asks' | 'unread' | 'working' | 'fondo'

export interface WsFlags {
  blocked: boolean
  asks: boolean
  unread: boolean
  working: boolean
  fondo: boolean
}

/** Cuándo empezó cada workspace a necesitar al usuario (ms); solo ordena entre ellos. */
export type AttentionSince = Map<string, number>

const agentsOf = (ws: Workspace): Agent[] => ws.tabs.flatMap((t) => t.agents)

export function wsFlags(ws: Workspace): WsFlags {
  const ag = agentsOf(ws)
  return {
    blocked: ws.status === 'blocked' || ag.some((a) => a.status === 'blocked'),
    asks: ag.some((a) => a.asks_user),
    unread: ag.some((a) => a.unread),
    working: ws.status === 'working' || ag.some((a) => a.status === 'working'),
    fondo: ag.some(enSegundoPlano),
  }
}

export function wsNeedsUser(ws: Workspace): boolean {
  const f = wsFlags(ws)
  return f.blocked || f.asks || f.unread
}

export function wsIsActive(ws: Workspace): boolean {
  const f = wsFlags(ws)
  return f.blocked || f.asks || f.unread || f.working
}

/** Orden manual / arrastre: blocked, pregunta y working; sin leer queda en orden manual. */
export function wsEsActivoParaOrden(ws: Workspace): boolean {
  const f = wsFlags(ws)
  return f.blocked || f.asks || f.working
}

export function agentEsActivoParaOrden(a: Agent): boolean {
  return a.status === 'blocked' || a.asks_user || a.status === 'working'
}

export const attentionSince: AttentionSince = new Map()

/** Anota el momento en que un workspace pasa a necesitar atención y olvida los que ya no. */
export function trackAttention(list: Workspace[], since: AttentionSince = attentionSince, now = Date.now()): void {
  const live = new Set<string>()
  for (const ws of list) {
    if (!wsNeedsUser(ws)) continue
    live.add(ws.id)
    if (!since.has(ws.id)) since.set(ws.id, now)
  }
  for (const id of [...since.keys()]) if (!live.has(id)) since.delete(id)
}

const lastUse = (ws: Workspace): number => Math.max(0, ...agentsOf(ws).map((a) => Date.parse(a.last_activity ?? '') || 0))

/** Fijados; luego los que necesitan al usuario (el último en pedir arriba); el resto por uso, el más reciente arriba (la hora que muestra cada tarjeta). */
export function sortWorkspaces(list: Workspace[], since: AttentionSince = attentionSince): Workspace[] {
  return list
    .map((ws) => ({ ws, needs: wsNeedsUser(ws), used: lastUse(ws), at: since.get(ws.id) ?? 0 }))
    .sort(
      (a, b) =>
        Number(b.ws.pinned) - Number(a.ws.pinned) ||
        Number(b.needs) - Number(a.needs) ||
        (a.needs ? b.at - a.at : 0) ||
        (a.needs ? 0 : b.used - a.used) ||
        a.ws.number - b.ws.number,
    )
    .map((x) => x.ws)
}

const matches = (a: Agent, kind: AttentionKind) =>
  kind === 'blocked'
    ? a.status === 'blocked'
    : kind === 'asks'
      ? a.asks_user
      : kind === 'unread'
        ? !!a.unread
        : kind === 'fondo'
          ? enSegundoPlano(a)
          : a.status === 'working'

export function findFirst(list: Workspace[], kind: AttentionKind, since: AttentionSince = attentionSince): { wsId: string; paneId: string } | null {
  for (const ws of sortWorkspaces(list, since))
    for (const t of ws.tabs)
      for (const a of t.agents) if (matches(a, kind)) return { wsId: ws.id, paneId: a.pane_id }
  return null
}

/** Identificador estable mientras el workspace existe en Herdr (workspace_id en el snapshot). */
export function idDeWorkspace(ws: Workspace): string {
  return ws.id
}

export function idDePane(a: Agent): string {
  return a.pane_id
}

/** Clave compartida Colmena: id de tarjeta + id del tab Herdr, unidos por «:». */
export function claveGrupoPestanas(wsId: string, tabId: string): string {
  return `${wsId}:${tabId}`
}

export function agentNeedsUser(a: Agent): boolean {
  return a.status === 'blocked' || a.asks_user || !!a.unread
}

export function agentIsActive(a: Agent): boolean {
  return agentNeedsUser(a) || a.status === 'working'
}

export function sortAgents(list: Agent[], since: AttentionSince = attentionSince): Agent[] {
  return list
    .map((a) => ({
      a,
      needs: agentNeedsUser(a),
      used: Date.parse(a.last_activity ?? '') || 0,
      at: since.get(a.pane_id) ?? 0,
    }))
    .sort(
      (x, y) =>
        Number(y.needs) - Number(x.needs) ||
        (x.needs ? y.at - x.at : 0) ||
        (x.needs ? 0 : y.used - x.used) ||
        x.a.pane_id.localeCompare(y.a.pane_id),
    )
    .map((x) => x.a)
}

/**
 * Solo quietos: sin lista guardada devuelve el orden entrante; tarjetas nuevas arriba en su orden automático;
 * el resto según lo guardado; ids viejos se ignoran.
 */
export function aplicarOrdenManualQuietos<T>(
  items: T[],
  orden: string[],
  idDe: (item: T) => string,
): T[] {
  if (!orden.length) return items
  const guardado = new Set(orden)
  const porId = new Map(items.map((item) => [idDe(item), item]))
  const nuevos = items.filter((item) => !guardado.has(idDe(item)))
  const enOrden = orden.map((id) => porId.get(id)).filter((item): item is T => item !== undefined)
  const usados = new Set([...nuevos, ...enOrden].map(idDe))
  const sueltos = items.filter((item) => !usados.has(idDe(item)))
  return [...nuevos, ...enOrden, ...sueltos]
}

/**
 * Actividades arriba (orden automático); quietos abajo en orden manual guardado.
 * Sin orden guardado, igual que sortWorkspaces / sortAgents.
 */
export function aplicarOrdenManual<T>(
  ordenadosAuto: T[],
  orden: string[],
  idDe: (item: T) => string = idDeWorkspace as (item: T) => string,
  esActivo: (item: T) => boolean = wsEsActivoParaOrden as (item: T) => boolean,
): T[] {
  if (!orden.length) return ordenadosAuto
  const activos: T[] = []
  const quietos: T[] = []
  for (const item of ordenadosAuto) (esActivo(item) ? activos : quietos).push(item)
  return [...activos, ...aplicarOrdenManualQuietos(quietos, orden, idDe)]
}

export function aplicarOrdenPestanas(ordenadosAuto: Agent[], orden: string[]): Agent[] {
  return aplicarOrdenManual(ordenadosAuto, orden, idDePane, agentEsActivoParaOrden)
}

/** Tras arrastrar quietos, actualiza el orden guardado sin mover los activos de su lugar en la lista guardada. */
export function ordenTrasArrastreQuietos(
  visualIds: string[],
  esActivo: (id: string) => boolean,
  ordenPrev: string[],
): string[] {
  const exist = new Set(visualIds)
  const base = (ordenPrev.length ? ordenPrev : visualIds).filter((id) => exist.has(id))
  for (const id of visualIds) if (!base.includes(id)) base.unshift(id)
  const quietEnVisual = visualIds.filter((id) => !esActivo(id))
  let qi = 0
  return base.map((id) => (esActivo(id) ? id : quietEnVisual[qi++] ?? id))
}

/** Índice del quieto vecino en la lista visual (salta activos). */
export function indiceVecinoQuieto(
  index: number,
  delta: -1 | 1,
  length: number,
  esActivoEnIndice: (i: number) => boolean,
): number | null {
  if (delta === -1) {
    for (let i = index - 1; i >= 0; i--) if (!esActivoEnIndice(i)) return i
    return null
  }
  for (let i = index + 1; i < length; i++) if (!esActivoEnIndice(i)) return i
  return null
}

/** Destino al subir/bajar una tarjeta quieta en el tablero (salta activas). */
export function destinoReordenQuieto(index: number, delta: -1 | 1, list: Workspace[]): number | null {
  return indiceVecinoQuieto(index, delta, list.length, (i) => wsEsActivoParaOrden(list[i]!))
}

export function moverEnOrden(ids: string[], desde: number, hasta: number): string[] {
  if (desde === hasta || desde < 0 || hasta < 0 || desde >= ids.length || hasta >= ids.length) return ids
  const next = ids.slice()
  const [item] = next.splice(desde, 1)
  if (item === undefined) return ids
  next.splice(hasta, 0, item)
  return next
}
