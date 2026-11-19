import { parseDeepLink } from './transcript'

export const cargarSessionChatView = () => import('../components/SessionChatView.vue')
export const cargarSessionPreview = () => import('../components/SessionPreview.vue')

type Idle = (cb: () => void) => unknown

function enIdle(cb: () => void): unknown {
  const ric = (globalThis as { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number }).requestIdleCallback
  return ric ? ric(cb, { timeout: 3000 }) : setTimeout(cb, 1200)
}

export function precargarChat(idle: Idle = enIdle, search: string = globalThis.location?.search ?? '', cargar: () => Promise<unknown> = cargarSessionChatView): void {
  if (parseDeepLink(search)) void Promise.resolve(cargar()).catch(() => {})
  idle(() => {
    void cargarSessionChatView().catch(() => {})
    void cargarSessionPreview().catch(() => {})
  })
}
