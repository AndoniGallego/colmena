import { ApiError } from './types'
import type { SubscribeRequest } from '../lib/push'

export type AvisoPruebaDestino = 'notch' | 'celu'

export interface PushApi {
  key(): Promise<string>
  subscribe(body: SubscribeRequest): Promise<void>
  unsubscribe(endpoint: string): Promise<void>
  test(endpoint: string): Promise<void>
  testCierre(endpoint: string): Promise<void>
  probarAviso(kind: string, destino: AvisoPruebaDestino): Promise<void>
}

export async function call(path: string, body?: unknown): Promise<any> {
  const res = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = res.statusText || `HTTP ${res.status}`
    let sinCuerpo = true
    try {
      const d = await res.json()
      if (typeof d?.detail === 'string') {
        detail = d.detail
        sinCuerpo = false
      }
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, detail, null, [], sinCuerpo)
  }
  return res.json()
}

export const httpPushApi: PushApi = {
  key: async () => String((await call('/api/push/key')).key ?? ''),
  subscribe: async (body) => void (await call('/api/push/subscribe', body)),
  unsubscribe: async (endpoint) => void (await call('/api/push/unsubscribe', { endpoint })),
  test: async (endpoint) => void (await call('/api/push/test', { endpoint })),
  testCierre: async (endpoint) => void (await call('/api/push/cierre/test', { endpoint })),
  probarAviso: async (kind, destino) => void (await call('/api/avisos/prueba', { kind, destino })),
}
