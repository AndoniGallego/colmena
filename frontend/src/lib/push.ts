export interface PrefsBase {
  asks: boolean
  blocked: boolean
  done: boolean
  texto: boolean
  cierre: boolean
  mrs: boolean
  entornos: boolean
  progreso: boolean
  pestana: boolean
}

/** Las del núcleo más las que suman las piezas montadas. */
export type PushPrefs = PrefsBase & Record<string, boolean>

export const DEFAULT_PREFS: PrefsBase = {
  asks: true,
  blocked: true,
  done: true,
  texto: true,
  cierre: true,
  mrs: true,
  entornos: true,
  progreso: true,
  pestana: true,
}
export const PREF_KEYS = Object.keys(DEFAULT_PREFS) as (keyof PrefsBase)[]

/** `extras`: claves de las piezas montadas; arrancan prendidas como las del núcleo. */
export function normalizePrefs(raw: unknown, extras: readonly string[] = []): PushPrefs {
  const src = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
  const out: PushPrefs = { ...DEFAULT_PREFS }
  for (const k of [...PREF_KEYS, ...extras]) out[k] = typeof src[k] === 'boolean' ? (src[k] as boolean) : true
  return out
}

export interface PushEnv {
  ios: boolean
  standalone: boolean
  secure: boolean
  hasWorker: boolean
  hasPush: boolean
  hasNotification: boolean
  permission: NotificationPermission | 'default'
}

export type Support = 'unsupported' | 'install' | 'denied' | 'available'

export function resolveSupport(env: PushEnv): Support {
  if (env.ios && !env.standalone) return 'install'
  if (!env.secure || !env.hasWorker || !env.hasPush || !env.hasNotification) return 'unsupported'
  return env.permission === 'denied' ? 'denied' : 'available'
}

export function detectEnv(): PushEnv {
  const ua = navigator.userAgent
  const nav = navigator as Navigator & { standalone?: boolean }
  return {
    ios: /iPad|iPhone|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1),
    standalone: matchMedia('(display-mode: standalone)').matches || nav.standalone === true,
    secure: window.isSecureContext,
    hasWorker: 'serviceWorker' in navigator,
    hasPush: 'PushManager' in window,
    hasNotification: 'Notification' in window,
    permission: 'Notification' in window ? Notification.permission : 'default',
  }
}

export function deviceName(ua: string): string {
  if (/iPhone/.test(ua)) return 'iPhone'
  if (/iPad/.test(ua)) return 'iPad'
  const browser = /Edg\//.test(ua) ? 'Edge' : /OPR\//.test(ua) ? 'Opera' : /Firefox\//.test(ua) ? 'Firefox'
    : /Chrome\/|CriOS/.test(ua) ? 'Chrome' : /Safari\//.test(ua) ? 'Safari' : ''
  const os = /Android/.test(ua) ? 'Android' : /Windows/.test(ua) ? 'Windows' : /Mac OS X/.test(ua) ? 'Mac'
    : /Linux|X11/.test(ua) ? 'Linux' : ''
  return [os, browser].filter(Boolean).join(' · ') || 'Navegador'
}

export function urlBase64ToBytes(b64: string): Uint8Array<ArrayBuffer> {
  const pad = '='.repeat((4 - (b64.length % 4)) % 4)
  const raw = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/'))
  const out = new Uint8Array(new ArrayBuffer(raw.length))
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i)
  return out
}

export interface SubscribeRequest {
  subscription: { endpoint: string; keys: { p256dh: string; auth: string } }
  device: string
  prefs: PushPrefs
}

/** Null when the browser gave back a subscription without the encryption keys. */
export function subscribeRequest(json: PushSubscriptionJSON, device: string, prefs: PushPrefs): SubscribeRequest | null {
  const { endpoint, keys } = json
  if (!endpoint || !keys?.p256dh || !keys?.auth) return null
  return { subscription: { endpoint, keys: { p256dh: keys.p256dh, auth: keys.auth } }, device, prefs }
}
