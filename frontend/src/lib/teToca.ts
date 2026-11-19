import type { AgentStatus, Board, PedidoPermiso } from '../api/types'
import { hueDe } from './hue'

export type TeTocaMotivo = 'permiso' | 'pedido' | 'pregunta' | 'terminada'

export interface TeTocaAgente {
  pane_id: string
  session_id: string
  status: AgentStatus
  asks_user: boolean
  unread?: boolean
  last_activity: string | null
  nombre: string
  hue: number
}

export interface TeTocaInput {
  agentes: TeTocaAgente[]
  pedidos: PedidoPermiso[]
  pedidosPestana?: readonly { ts: number; vence?: number; origen: { session_id: string } }[]
  now: number
}

export interface TeTocaItem {
  sid: string
  pane: string
  nombre: string
  motivo: TeTocaMotivo
  desdeMs: number
  vencido: boolean
  hue: number
}

const VENCE_MS = 3 * 60 * 60 * 1000
const ORDEN: Record<TeTocaMotivo, number> = { permiso: 0, pedido: 1, pregunta: 2, terminada: 3 }
const ABIERTO = new Set(['abierto', 'enviando'])

const tabLabel = (label: string, i: number) => (label && !/^\d+$/.test(label) ? label : `tab ${label || i + 1}`)

function ms(iso: string | null | undefined, fallback: number): number {
  if (!iso) return fallback
  const t = Date.parse(iso)
  return Number.isNaN(t) ? fallback : t
}

function motivoDe(ag: TeTocaAgente, conPedido: boolean): TeTocaMotivo | null {
  if (ag.status === 'blocked') return 'permiso'
  if (conPedido) return 'pedido'
  if (ag.asks_user) return 'pregunta'
  if (ag.unread) return 'terminada'
  return null
}

function desdeMsDe(
  motivo: TeTocaMotivo,
  ag: TeTocaAgente,
  pedido: PedidoPermiso | undefined,
  now: number,
  tsPedido?: number,
): number {
  if (motivo === 'pedido' && tsPedido !== undefined) return tsPedido * 1000
  if (motivo === 'permiso') return ms(pedido?.creado ?? null, ms(ag.last_activity, now))
    return ms(ag.last_activity, now)
}

/** Sesiones que te necesitan, ordenadas para la franja. */
export function teTocaItems(input: TeTocaInput): TeTocaItem[] {
  const { agentes, pedidos, now } = input
  const tsPorSid = new Map<string, number>()
  for (const p of input.pedidosPestana ?? []) {
    const sid = p.origen.session_id
    if (!sid || (p.vence !== undefined && p.vence * 1000 <= now)) continue
    const cur = tsPorSid.get(sid)
    if (cur === undefined || p.ts < cur) tsPorSid.set(sid, p.ts)
  }
  const pedidoPorSid = new Map<string, PedidoPermiso>()
  for (const p of pedidos) {
    if (ABIERTO.has(p.estado)) pedidoPorSid.set(p.session_id, p)
  }

  const items: TeTocaItem[] = []
  for (const ag of agentes) {
    const motivo = motivoDe(ag, tsPorSid.has(ag.session_id))
    if (!motivo) continue
    const pedido = pedidoPorSid.get(ag.session_id)
    const desdeMs = desdeMsDe(motivo, ag, pedido, now, tsPorSid.get(ag.session_id))
    items.push({
      sid: ag.session_id,
      pane: ag.pane_id,
      nombre: ag.nombre,
      motivo,
      desdeMs,
      vencido: now - desdeMs >= VENCE_MS,
      hue: ag.hue,
    })
  }

  items.sort((a, b) => {
    const g = ORDEN[a.motivo] - ORDEN[b.motivo]
    if (g) return g
    return a.desdeMs - b.desdeMs
  })
  return items
}

/** Agentes del tablero con nombre corto workspace · tab. */
export function agentesTeToca(board: Board | null | undefined): TeTocaAgente[] {
  if (!board) return []
  const out: TeTocaAgente[] = []
  for (const ws of board.workspaces) {
    const wsLabel = ws.label || `Workspace ${ws.number}`
    ws.tabs.forEach((tab, i) => {
      const nombre = `${wsLabel} · ${tabLabel(tab.label, i)}`
      const hue = hueDe(wsLabel)
      for (const ag of tab.agents) {
        if (!ag.session_id) continue
        out.push({
          pane_id: ag.pane_id,
          session_id: ag.session_id,
          status: ag.status,
          asks_user: ag.asks_user,
          unread: ag.unread,
          last_activity: ag.last_activity,
          nombre,
          hue,
        })
      }
    })
  }
  return out
}
