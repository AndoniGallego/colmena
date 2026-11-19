import { ApiError } from './types'
import { normalizeClaudeUso } from '../lib/usoClaude'
import type { UsoPlan } from '../lib/usoPlan'

export type { UsoPlan }

export function normalizarUsoPlan(raw: any): UsoPlan | null {
  if (!raw || typeof raw !== 'object' || raw.sin_datos) return null
  const l = normalizeClaudeUso({ limites: raw }).limites
  if (!l) return null
  const edad = raw.edad_s
  return { fiveHour: l.fiveHour, sevenDay: l.sevenDay, actualizado: l.actualizado, edadS: typeof edad === 'number' && Number.isFinite(edad) && edad >= 0 ? edad : null }
}

export async function getUsoLimites(f: typeof fetch = fetch): Promise<UsoPlan | null> {
  let res: Response
  try {
    res = await f('/api/uso/limites', { credentials: 'same-origin' })
  } catch {
    throw new ApiError(0, 'Se cortó la conexión con el servidor')
  }
  if (!res.ok) throw new ApiError(res.status, res.status === 401 ? 'La sesión venció, volvé a entrar' : 'No pude leer el uso del plan')
  return normalizarUsoPlan(await res.json())
}
