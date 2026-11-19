/** Una pantalla vieja no se recarga sola mientras alguien escribe o hay un envío en curso. */
export const IDLE_MS = 20_000

let working = 0
export const isWorking = () => working > 0

export async function tracked<T>(job: Promise<T>): Promise<T> {
  working++
  try {
    return await job
  } finally {
    working = Math.max(0, working - 1)
  }
}

const RELOADED_KEY = 'reloadedFor'

/** Una sola recarga automática por build: si ya se recargó para este id, no se vuelve a intentar. */
export function claimReload(build: string, store?: Pick<Storage, 'getItem' | 'setItem'>): boolean {
  try {
    const s = store ?? sessionStorage
    if (s.getItem(RELOADED_KEY) === build) return false
    s.setItem(RELOADED_KEY, build)
  } catch {
    /* sin sessionStorage: se recarga igual */
  }
  return true
}

export const isStale = (own: string, remote: string) => !!own && !!remote && own !== 'dev' && own !== remote

export type Trigger = 'visible' | 'notice' | 'idle'
export type Decision = 'none' | 'wait' | 'reload'

export interface UpdateContext {
  own: string
  remote: string
  trigger: Trigger
  typing: boolean
  working: boolean
  visible: boolean
  idleMs: number
}

export function reloadDecision(c: UpdateContext): Decision {
  if (!isStale(c.own, c.remote)) return 'none'
  if (c.typing || c.working) return 'wait'
  if (!c.visible || c.trigger === 'visible') return 'reload'
  return c.idleMs >= IDLE_MS ? 'reload' : 'wait'
}
