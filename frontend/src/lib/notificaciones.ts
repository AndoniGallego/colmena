import type { FiltroCierre } from '../api/types'

export type OrdenCerrar = { type: 'orq-cerrar' } & Partial<Record<'session_id' | 'pane_id' | 'kind' | 'mr', string>> & { tags?: string[] }

export function ordenDeCierre(f: FiltroCierre): OrdenCerrar {
  if ('tags' in f) return { type: 'orq-cerrar', tags: f.tags }
  return { type: 'orq-cerrar', ...f }
}

/** Cierra en el sistema las notificaciones ya mostradas de ese destino. */
export async function cerrarNotificaciones(f: FiltroCierre): Promise<void> {
  try {
    if (!('serviceWorker' in navigator)) return
    const reg = await navigator.serviceWorker.getRegistration()
    reg?.active?.postMessage(ordenDeCierre(f))
  } catch {
    /* sin service worker: no hay nada que cerrar */
  }
}

/** Número en el ícono de la app instalada; no existe en todos los navegadores. */
export async function actualizarBadge(n: number): Promise<void> {
  const nav = navigator as Navigator & { setAppBadge?: (n: number) => Promise<void>; clearAppBadge?: () => Promise<void> }
  try {
    if (n > 0) await nav.setAppBadge?.(n)
    else await nav.clearAppBadge?.()
  } catch {
    /* sin permiso o sin soporte */
  }
}
