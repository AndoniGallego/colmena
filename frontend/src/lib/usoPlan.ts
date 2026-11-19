import type { UsoLimite } from './usoClaude'

export interface UsoPlan {
  fiveHour: UsoLimite | null
  sevenDay: UsoLimite | null
  actualizado: string | null
  edadS: number | null
}
export type NivelPlan = 'ok' | 'atento' | 'alto'

const VIEJO_S = 30 * 60

export const nivel = (pct: number): NivelPlan => (pct >= 90 ? 'alto' : pct >= 70 ? 'atento' : 'ok')

/** «2 h 10 min», «3 d 4 h»; vacío si ya pasó o la fecha no sirve. */
export function faltaPara(resetsAt: string | null, ahora: number): string {
  const t = resetsAt ? Date.parse(resetsAt) : NaN
  if (Number.isNaN(t) || t <= ahora) return ''
  const min = Math.floor((t - ahora) / 60_000)
  if (min < 1) return 'menos de 1 min'
  const d = Math.floor(min / 1440)
  const h = Math.floor((min % 1440) / 60)
  const m = min % 60
  if (d > 0) return h ? `${d} d ${h} h` : `${d} d`
  if (h > 0) return m ? `${h} h ${m} min` : `${h} h`
  return `${m} min`
}

export interface VentanaPlan {
  key: '5h' | '7d'
  corto: string
  titulo: string
  lim: UsoLimite
}

export function ventanas(plan: UsoPlan): VentanaPlan[] {
  return [
    plan.fiveHour && { key: '5h' as const, corto: '5h', titulo: 'Últimas 5 horas', lim: plan.fiveHour },
    plan.sevenDay && { key: '7d' as const, corto: 'sem', titulo: 'Semana', lim: plan.sevenDay },
  ].filter((v): v is VentanaPlan => !!v)
}

export function textoCorto(plan: UsoPlan): string {
  return ventanas(plan)
    .map((v) => `${v.corto} ${v.lim.vencido ? 'renovado' : `${Math.round(v.lim.pct)}%`}`)
    .join(' · ')
}

export function viejo(plan: UsoPlan, ahora: number): boolean {
  const t = plan.actualizado ? Date.parse(plan.actualizado) : NaN
  if (!Number.isNaN(t)) return (ahora - t) / 1000 > VIEJO_S
  return plan.edadS !== null && plan.edadS > VIEJO_S
}

export function ariaPlan(plan: UsoPlan): string {
  const partes = ventanas(plan).map((v) => {
    const pct = v.lim.vencido ? 'renovado' : `${Math.round(v.lim.pct)}%`
    return v.key === '5h' ? `${pct} de 5 horas` : `${pct} semanal`
  })
  return `Plan de Claude: ${partes.join(', ')}`
}

/** Hora local corta de un instante ISO («lun 14:05»); vacío si no sirve. */
export function horaLocal(iso: string | null): string {
  const t = iso ? new Date(iso) : null
  if (!t || Number.isNaN(t.getTime())) return ''
  const dias = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb']
  return `${dias[t.getDay()]} ${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')}`
}
