import { reactive } from 'vue'
import { httpPushApi, type AvisoPruebaDestino } from '../api/pushApi'
import { enAppWindows } from '../lib/appWindows'
import { detalleTecnico, ErrorUsuario, mensajeError } from '../lib/errores'
import { detectEnv, deviceName, normalizePrefs, resolveSupport, subscribeRequest, urlBase64ToBytes, type PushPrefs } from '../lib/push'
import { piezas } from '../piezas'
import { DEMO } from '../lib/demoActual'
import { usarMock } from '../lib/modoDemo'

export type PushStatus = 'checking' | 'unsupported' | 'install' | 'denied' | 'off' | 'on' | 'programa'

let sessionStore: Pick<Storage, 'getItem' | 'setItem'> | null = null
try {
  sessionStore = sessionStorage
} catch {
  sessionStore = null
}
const PROGRAMA = enAppWindows(location.search, sessionStore)

const PREFS_KEY = 'orq.push.prefs'
const MOCK = usarMock({ demo: DEMO, dev: import.meta.env.DEV, search: location.search })
const scenario = DEMO ? 'unsupported' : MOCK ?(new URLSearchParams(location.search).get('push') ?? 'off') : ''

function loadPrefs(): PushPrefs {
  const extras = piezas().flatMap((p) => (p.notificaciones ? [p.notificaciones.pref.key] : []))
  try {
    return normalizePrefs(JSON.parse(localStorage.getItem(PREFS_KEY) ?? 'null'), extras)
  } catch {
    return normalizePrefs(null, extras)
  }
}

function savePrefs(p: PushPrefs) {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(p))
  } catch {
    /* storage unavailable: prefs live only in memory */
  }
}

export const pushState = reactive({
  status: 'checking' as PushStatus,
  prefs: loadPrefs(),
  busy: false,
  error: '',
  errorDetalle: null as string | null,
  device: MOCK ? 'iPhone' : deviceName(navigator.userAgent),
  endpoint: '',
})

async function registration(): Promise<ServiceWorkerRegistration> {
  const timeout = new Promise<never>((_, rej) => setTimeout(() => rej(new ErrorUsuario('El service worker no está activo')), 4000))
  return Promise.race([navigator.serviceWorker.ready, timeout])
}

async function currentSubscription(): Promise<PushSubscription | null> {
  const reg = await navigator.serviceWorker.getRegistration()
  return reg ? reg.pushManager.getSubscription() : null
}

async function sync(sub: PushSubscription) {
  const body = subscribeRequest(sub.toJSON(), pushState.device, pushState.prefs)
  if (!body) throw new ErrorUsuario('El navegador no devolvió las claves de la suscripción')
  await httpPushApi.subscribe(body)
}

function limpiarErrorPush() {
  pushState.error = ''
  pushState.errorDetalle = null
}

function asignarErrorPush(e: unknown, fallback: string) {
  pushState.error = mensajeError(e, fallback)
  pushState.errorDetalle = detalleTecnico(e)
}

export async function refreshPush() {
  limpiarErrorPush()
  if (PROGRAMA) {
    pushState.endpoint = ''
    pushState.status = 'programa'
    return
  }
  if (MOCK) {
    pushState.endpoint = ''
    pushState.status = (['unsupported', 'install', 'denied', 'on'].includes(scenario) ? scenario : 'off') as PushStatus
    return
  }
  const support = resolveSupport(detectEnv())
  if (support !== 'available') {
    pushState.status = support
    return
  }
  try {
    const sub = await currentSubscription()
    pushState.endpoint = sub?.endpoint ?? ''
    pushState.status = sub ? 'on' : 'off'
    if (sub) await sync(sub)
  } catch {
    pushState.status = pushState.status === 'checking' ? 'off' : pushState.status
  }
}

export async function enablePush(): Promise<boolean> {
  if (PROGRAMA) return false
  if (pushState.busy) return false
  pushState.busy = true
  limpiarErrorPush()
  try {
    if (MOCK) {
      await new Promise((r) => setTimeout(r, 700))
      pushState.status = 'on'
      return true
    }
    const permission = await Notification.requestPermission()
    if (permission !== 'granted') {
      pushState.status = permission === 'denied' ? 'denied' : 'off'
      return false
    }
    const reg = await registration()
    const key = await httpPushApi.key()
    const sub = (await reg.pushManager.getSubscription()) ??
      (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToBytes(key) }))
    await sync(sub)
    pushState.endpoint = sub.endpoint
    pushState.status = 'on'
    return true
  } catch (e) {
    asignarErrorPush(e, 'No se pudo activar')
    return false
  } finally {
    pushState.busy = false
  }
}

export async function disablePush(): Promise<boolean> {
  if (pushState.busy) return false
  pushState.busy = true
  limpiarErrorPush()
  try {
    if (!MOCK) {
      const sub = await currentSubscription()
      if (sub) {
        await httpPushApi.unsubscribe(sub.endpoint)
        await sub.unsubscribe()
      }
    }
    pushState.endpoint = ''
    pushState.status = 'off'
    return true
  } catch (e) {
    asignarErrorPush(e, 'No se pudo desactivar')
    return false
  } finally {
    pushState.busy = false
  }
}

export async function setPushPref(key: keyof PushPrefs, value: boolean) {
  const before = pushState.prefs
  pushState.prefs = { ...before, [key]: value }
  savePrefs(pushState.prefs)
  limpiarErrorPush()
  if (MOCK) return
  try {
    const sub = await currentSubscription()
    if (sub) await sync(sub)
  } catch (e) {
    pushState.prefs = before
    savePrefs(before)
    asignarErrorPush(e, 'No se pudo guardar')
  }
}

export const testPush = () => probarEnvio((endpoint) => httpPushApi.test(endpoint))

/** Manda una prueba a este dispositivo con `send`; las piezas lo usan para las suyas. */
export async function probarEnvio(send: (endpoint: string) => Promise<void>): Promise<boolean> {
  if (pushState.busy) return false
  pushState.busy = true
  limpiarErrorPush()
  try {
    if (MOCK) {
      await new Promise((r) => setTimeout(r, 600))
      return true
    }
    const sub = await currentSubscription()
    if (!sub) throw new ErrorUsuario('Este dispositivo no está suscripto')
    await send(sub.endpoint)
    return true
  } catch (e) {
    asignarErrorPush(e, 'No se pudo enviar')
    return false
  } finally {
    pushState.busy = false
  }
}

export async function testCierre(): Promise<boolean> {
  return probarEnvio((endpoint) => httpPushApi.testCierre(endpoint))
}

export type ProbarAvisoResult = { ok: true } | { ok: false; message: string }

export async function runProbarAviso(kind: string, destino: AvisoPruebaDestino): Promise<ProbarAvisoResult> {
  try {
    await httpPushApi.probarAviso(kind, destino)
    return { ok: true }
  } catch (e) {
    const raw = e instanceof Error ? e.message : String(e)
    const low = raw.toLowerCase()
    if (low.includes('no hay dispositivos suscriptos') || low.includes('404') || low.includes('not found')) {
      return { ok: false, message: 'No hay celus suscriptos' }
    }
    const short = raw.length > 72 ? `${raw.slice(0, 69)}…` : raw
    return { ok: false, message: mensajeError(e, short) }
  }
}
