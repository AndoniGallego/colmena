import { isTyping } from '../lib/biblioteca'
import { claimReload, isStale, IDLE_MS, isWorking, reloadDecision, type Trigger } from '../lib/update'

const own = __APP_BUILD__
let remote = ''
const SW_BUILD = 'sw'
let lastActivity = Date.now()
let idleTimer: ReturnType<typeof setTimeout> | undefined
let started = false

async function refreshWorker() {
  try {
    await (await navigator.serviceWorker?.getRegistration())?.update()
  } catch {
    /* sin red o sin worker: el chequeo de build sigue valiendo */
  }
}

async function hardReload() {
  try {
    const keys = await caches.keys()
    await Promise.all(keys.filter((k) => k.startsWith('orq-')).map((k) => caches.delete(k)))
  } catch {
    /* sin Cache Storage */
  }
  location.reload()
}

function evaluate(trigger: Trigger) {
  const decision = reloadDecision({
    own,
    remote,
    trigger,
    typing: isTyping(document.activeElement),
    working: isWorking(),
    visible: document.visibilityState === 'visible',
    idleMs: Date.now() - lastActivity,
  })
  if (decision === 'reload') return claimReload(remote) ? void hardReload() : undefined
  if (decision === 'wait') {
    clearTimeout(idleTimer)
    idleTimer = setTimeout(() => evaluate('idle'), Math.max(1000, IDLE_MS - (Date.now() - lastActivity)))
  }
}

function start() {
  if (started) return
  started = true
  const touch = () => (lastActivity = Date.now())
  for (const ev of ['pointerdown', 'keydown', 'touchstart']) document.addEventListener(ev, touch, { passive: true, capture: true })
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'visible') return
    void refreshWorker()
    if (isStale(own, remote)) evaluate('visible')
  })
  navigator.serviceWorker?.addEventListener('message', (e: MessageEvent) => {
    if (e.data?.type !== 'orq-updated') return
    remote ||= SW_BUILD
    evaluate('notice')
  })
}

/** Called with the build id the server reports on SSE connect and in each ping. */
export function noteBuild(id: string) {
  start()
  if (id === remote) return
  remote = id
  if (!isStale(own, remote)) return
  void refreshWorker()
  evaluate('notice')
}
