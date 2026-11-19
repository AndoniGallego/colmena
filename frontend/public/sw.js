const VERSION = '__BUILD_ID__'
const PAGE_CACHE = `orq-page-${VERSION}`
const ASSETS_CACHE = 'orq-assets'
const ASSETS_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000

function htmlValid(html) {
  const t = html.trim()
  if (!t) return false
  return /<!DOCTYPE\s+html/i.test(t) || /<\s*html[\s>]/i.test(t)
}

function extractReferencedAssets(html) {
  const out = new Set()
  const re = /\/assets\/[^"'\s>)]+/g
  let m
  while ((m = re.exec(html))) out.add(m[0])
  return [...out]
}

// copia de swCache.ts
function assetsToEvict(html, cached, nowMs, maxAgeMs = ASSETS_MAX_AGE_MS) {
  if (!htmlValid(html)) return []
  const ref = new Set(extractReferencedAssets(html))
  const drop = []
  for (const { url, cachedAt } of cached) {
    if (!url.startsWith('/assets/')) continue
    if (ref.has(url)) continue
    if (nowMs - cachedAt > maxAgeMs) drop.push(url)
  }
  return drop
}

async function listCachedAssets(cache) {
  const cached = []
  for (const req of await cache.keys()) {
    const path = new URL(req.url).pathname
    if (!path.startsWith('/assets/')) continue
    const res = await cache.match(req)
    if (!res) continue
    const at = res.headers.get('x-orq-cached-at')
    cached.push({ url: path, cachedAt: at ? +at : 0 })
  }
  return cached
}

async function putCachedAsset(cache, req, res) {
  const headers = new Headers(res.headers)
  if (!headers.get('x-orq-cached-at')) headers.set('x-orq-cached-at', String(Date.now()))
  await cache.put(req, new Response(res.body, { status: res.status, statusText: res.statusText, headers }))
}

const SESSION_RE = /^[A-Za-z0-9_.:-]{1,80}$/
const MR_RE = /^\d{1,12}:\d{1,9}$/
const PANE_RE = /^[A-Za-z0-9][A-Za-z0-9_:.-]{0,63}$/
const TAG_RE = /^[A-Za-z0-9_.:-]{1,120}$/
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

const UA = (self.navigator && self.navigator.userAgent) || ''
const WEBKIT = /iPhone|iPad|iPod/.test(UA) || (/AppleWebKit/.test(UA) && !/Chrome|Chromium|Edg|OPR|Firefox/.test(UA))

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(PAGE_CACHE).then((c) => c.add('/')).then(() => self.skipWaiting()))
})

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    const allKeys = await caches.keys()
    const stale = allKeys.filter((k) => k !== ASSETS_CACHE && k !== PAGE_CACHE && k.startsWith('orq-'))
    let html = ''
    try {
      const res = await fetch('/', { cache: 'no-store' })
      if (!res.ok) throw new Error('fetch /')
      html = await res.text()
    } catch {
      await self.clients.claim()
      return
    }
    await Promise.all(stale.map((k) => caches.delete(k)))
    const assets = await caches.open(ASSETS_CACHE)
    const evict = assetsToEvict(html, await listCachedAssets(assets), Date.now())
    for (const path of evict) await assets.delete(path)
    const page = await caches.open(PAGE_CACHE)
    const shell = await fetch('/', { cache: 'no-store' })
    if (shell.ok) await page.put('/', shell.clone())
    await self.clients.claim()
    // iOS relanza la PWA sin pedir `/` y sigue con el bundle viejo: si cambió la versión, cada ventana decide cuándo recargar.
    if (!stale.length) return
    const wins = await self.clients.matchAll({ type: 'window' })
    wins.forEach((w) => w.postMessage({ type: 'orq-updated' }))
  })())
})

self.addEventListener('fetch', (e) => {
  const req = e.request
  const url = new URL(req.url)
  if (req.method !== 'GET' || url.origin !== location.origin) return
  if (url.pathname.startsWith('/api/') || url.pathname === '/sw.js') return

  if (req.mode === 'navigate') {
    e.respondWith(
      fetch(req, { cache: 'no-store' }).then((res) => {
        if (res.ok) caches.open(PAGE_CACHE).then((c) => c.put('/', res.clone()))
        return res
      }).catch(() => caches.match('/', { cacheName: PAGE_CACHE })),
    )
    return
  }

  if (url.pathname.startsWith('/assets/')) {
    e.respondWith(
      caches.open(ASSETS_CACHE).then((cache) =>
        cache.match(req).then((hit) => hit || fetch(req).then((res) => {
          if (res.ok) putCachedAsset(cache, req, res.clone())
          return res
        })),
      ),
    )
  }
})

// Pieza que abre la notificación al tocarla (`/?abrir=<pieza>`), con una fecha opcional.
const ABRIR_RE = /^[a-z]{1,20}$/

function fechaOk(v) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v)
  if (!m) return false
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]))
  return d.getUTCFullYear() === +m[1] && d.getUTCMonth() === +m[2] - 1 && d.getUTCDate() === +m[3]
}

function tagsValidos(raw) {
  return (Array.isArray(raw) ? raw : [])
    .filter((t) => typeof t === 'string' && TAG_RE.test(t))
    .slice(0, 50)
}

async function cerrarNotificaciones({ sid, pane, abrir, mr, tags }) {
  const tagSet = new Set(tags)
  let n = 0
  for (const notif of await self.registration.getNotifications()) {
    const d = notif.data || {}
    if (
      (sid && d.session_id === sid) ||
      (pane && d.pane === pane) ||
      (abrir && d.abrir === abrir) ||
      (mr && d.mr === mr) ||
      (tags.length && typeof notif.tag === 'string' && tagSet.has(notif.tag))
    ) {
      notif.close()
      n++
    }
  }
  return n
}

self.addEventListener('push', (e) => {
  let d = {}
  try { d = e.data ? e.data.json() : {} } catch { /* texto plano o vacío */ }
  if (d.kind === 'cerrar') {
    const tags = tagsValidos(d.tags)
    e.waitUntil((async () => {
      await cerrarNotificaciones({ sid: '', pane: '', abrir: '', mr: '', tags })
      if (!WEBKIT) return
      // Safari revoca la suscripción si un push no muestra nada.
      const tag = tags[0] || 'cerrar'
      await self.registration.showNotification('Colmena', {
        body: 'Ya lo viste en otro dispositivo.',
        tag,
        silent: true,
        icon: '/icons/icon-192.png',
        badge: '/icons/icon-192.png',
        data: {},
      })
      for (const notif of await self.registration.getNotifications({ tag })) {
        if (notif.tag === tag) notif.close()
      }
    })())
    return
  }
  const pane = d.kind === 'terminal' && typeof d.pane_id === 'string' && PANE_RE.test(d.pane_id) ? d.pane_id : ''
  const abrir = typeof d.abrir === 'string' && ABRIR_RE.test(d.abrir) ? d.abrir : ''
  const fecha = abrir && typeof d.fecha === 'string' && fechaOk(d.fecha) ? d.fecha : ''
  const mr = d.kind === 'mr' && typeof d.mr === 'string' && MR_RE.test(d.mr) ? d.mr : ''
  let pedido = ''
  if (d.kind === 'pestana') {
    if (typeof d.pedido === 'string' && UUID_RE.test(d.pedido)) pedido = d.pedido
    else if (typeof d.url === 'string') {
      try {
        const p = new URL(d.url, 'https://x').searchParams.get('pedido')
        if (p && UUID_RE.test(p)) pedido = p
      } catch { /* url malformada */ }
    }
  }
  const opts = { body: d.body || '', icon: '/icons/icon-192.png', badge: '/icons/icon-192.png', data: { session_id: d.session_id || '', dialogo: d.dialogo === true, pane, abrir, fecha, mr, pedido } }
  if (d.tag) {
    opts.tag = d.tag
    // progreso reemplaza la misma tag: sin sonido ni vibración de nuevo
    opts.renotify = d.kind !== 'progreso'
  }
  e.waitUntil(self.registration.showNotification(d.title || 'Colmena', opts))
})

// La app avisa que ya mira un destino: sus notificaciones del sistema sobran.
self.addEventListener('message', (e) => {
  const m = e.data
  if (!m || m.type !== 'orq-cerrar') return
  const sid = typeof m.session_id === 'string' && SESSION_RE.test(m.session_id) ? m.session_id : ''
  const pane = typeof m.pane_id === 'string' && PANE_RE.test(m.pane_id) ? m.pane_id : ''
  const abrir = typeof m.kind === 'string' && ABRIR_RE.test(m.kind) ? m.kind : ''
  const mr = typeof m.mr === 'string' && MR_RE.test(m.mr) ? m.mr : ''
  const tags = tagsValidos(m.tags)
  if (!sid && !pane && !abrir && !mr && !tags.length) return
  e.waitUntil(cerrarNotificaciones({ sid, pane, abrir, mr, tags }))
})

self.addEventListener('notificationclick', (e) => {
  e.notification.close()
  const id = e.notification.data && e.notification.data.session_id
  const dialogo = e.notification.data && e.notification.data.dialogo === true
  const pane = e.notification.data && e.notification.data.pane
  const abrir = e.notification.data && typeof e.notification.data.abrir === 'string' && ABRIR_RE.test(e.notification.data.abrir) ? e.notification.data.abrir : ''
  const fecha = e.notification.data && typeof e.notification.data.fecha === 'string' && fechaOk(e.notification.data.fecha) ? e.notification.data.fecha : ''
  const mr = e.notification.data && typeof e.notification.data.mr === 'string' && MR_RE.test(e.notification.data.mr) ? e.notification.data.mr : ''
  const pedido = e.notification.data && typeof e.notification.data.pedido === 'string' && UUID_RE.test(e.notification.data.pedido) ? e.notification.data.pedido : ''
  const url = pedido ? `/?pedido=${pedido}` : mr ? `/?mr=${mr}` : abrir ? `/?abrir=${abrir}${fecha ? `&fecha=${fecha}` : ''}` : pane ? `/?terminal=${encodeURIComponent(pane)}` : id ? `/?session=${encodeURIComponent(id)}${dialogo ? '&dialogo=1' : ''}` : '/?chat=jefe'
  e.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    const win = wins.find((c) => {
      const p = new URL(c.url).pathname
      return new URL(c.url).origin === location.origin && p !== '/notch' && p !== '/notch/'
    })
    if (win) {
      try {
        await win.focus()
        await win.navigate(url)
        return
      } catch { /* sin permiso para navegar: abro una ventana */ }
    }
    await self.clients.openWindow(url)
  })())
})
