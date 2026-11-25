import type { Agent, AgentDisplayStatus, FondoTarea } from '../api/types'

const ROTULO: Record<FondoTarea['tipo'], string> = {
  cursor: 'Cursor',
  agente: 'Un agente',
  comando: 'Un comando',
  workflow: 'Workflow',
}

export function enSegundoPlano(agent: Pick<Agent, 'status' | 'fondo'>): boolean {
  return (agent.status === 'idle' || agent.status === 'done') && (agent.fondo?.length ?? 0) > 0
}

export function estadoEfectivo(agent: Pick<Agent, 'status' | 'fondo'>): AgentDisplayStatus {
  return enSegundoPlano(agent) ? 'fondo' : agent.status
}

export function rotuloTarea(t: FondoTarea): string {
  return `${ROTULO[t.tipo] ?? 'Tarea'} · ${t.texto}`
}

export function masFondo(cantidad: number): string {
  return cantidad > 1 ? `+${cantidad - 1}` : ''
}

export interface MetaCtx { unread: boolean; pide: boolean; pill: boolean; doing: boolean; mr: boolean; otroKind: boolean; fondo: boolean; traba?: boolean }

export function mostrarMeta(c: MetaCtx): boolean {
  return c.unread || c.pide || c.pill || c.doing || c.mr || c.otroKind || c.fondo || !!c.traba
}
