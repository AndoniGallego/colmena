import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'

type Handler = (e: any) => void

function loadSw(userAgent = '', winUrl = 'https://orq.example/') {
  const handlers: Record<string, Handler> = {}
  const shown: { title: string; opts: any }[] = []
  const opened: string[] = []
  const nav: string[] = []
  const open: { data: any; tag: string; close: ReturnType<typeof vi.fn> }[] = []
  const win = { url: winUrl, focus: vi.fn(async () => {}), navigate: vi.fn(async (u: string) => void nav.push(u)) }
  const self = {
    addEventListener: (t: string, h: Handler) => (handlers[t] = h),
    navigator: { userAgent },
    registration: {
      showNotification: async (title: string, opts: any) => {
        shown.push({ title, opts })
        const n = { data: opts?.data ?? {}, tag: typeof opts?.tag === 'string' ? opts.tag : '', close: vi.fn() }
        open.push(n)
      },
      getNotifications: async () => open,
    },
    clients: { matchAll: async () => [win], openWindow: async (u: string) => void opened.push(u), claim: async () => {} },
  }
  const src = readFileSync(new URL('../public/sw.js', import.meta.url).pathname, 'utf8')
  new Function('self', 'caches', 'location', 'URL', src)(self, {}, { origin: 'https://orq.example' }, URL)
  const push = async (data: unknown) => {
    let wait: Promise<unknown> = Promise.resolve()
    handlers.push({ data: { json: () => data }, waitUntil: (p: Promise<unknown>) => (wait = p) })
    await wait
    return shown[shown.length - 1]
  }
  const click = async (data: unknown) => {
    let wait: Promise<unknown> = Promise.resolve()
    handlers.notificationclick({ notification: { close() {}, data }, waitUntil: (p: Promise<unknown>) => (wait = p) })
    await wait
  }
  const message = async (data: unknown) => {
    let wait: Promise<unknown> = Promise.resolve()
    handlers.message({ data, waitUntil: (p: Promise<unknown>) => (wait = p) })
    await wait
  }
  const notif = (data: any, tag = '') => {
    const n = { data, tag, close: vi.fn() }
    open.push(n)
    return n
  }
  return { push, click, nav, opened, win, message, notif, shown, notifications: open }
}

describe('service worker: aviso que abre una pieza', () => {
  let sw: ReturnType<typeof loadSw>
  beforeEach(() => (sw = loadSw()))

  it('guarda la pieza y la fecha válida del push', async () => {
    const n = await sw.push({ title: 'Aviso demo', body: 'x', kind: 'demo', abrir: 'demo', fecha: '2026-10-30', tag: 'demo' })
    expect(n.opts.data).toMatchObject({ abrir: 'demo', fecha: '2026-10-30' })
    expect(n.opts.tag).toBe('demo')
  })

  it.each(['2026-02-30', '30/10/2026', '2026-10-30&x=1', '../x', 5, null])('descarta fecha inválida %s', async (fecha) => {
    const n = await sw.push({ kind: 'demo', abrir: 'demo', fecha })
    expect(n.opts.data.fecha).toBe('')
  })

  it('ignora la fecha si el push no abre una pieza', async () => {
    expect((await sw.push({ kind: 'done', fecha: '2026-10-30' })).opts.data).toMatchObject({ abrir: '', fecha: '' })
  })

  it.each(['Demo', 'de mo', '../x', 'a'.repeat(21), 5])('descarta una pieza inválida %s', async (abrir) => {
    const n = await sw.push({ kind: 'demo', abrir, fecha: '2026-10-30' })
    expect(n.opts.data).toMatchObject({ abrir: '', fecha: '' })
    await sw.click({ abrir })
    expect(sw.nav).toEqual(['/?chat=jefe'])
  })

  it('al tocar abre la app en la URL de la pieza con la fecha', async () => {
    await sw.click({ session_id: '', abrir: 'demo', fecha: '2026-10-30' })
    expect(sw.win.focus).toHaveBeenCalled()
    expect(sw.nav).toEqual(['/?abrir=demo&fecha=2026-10-30'])
  })

  it('revalida la fecha al tocar y sin fecha abre igual', async () => {
    await sw.click({ abrir: 'demo', fecha: 'x&y=1' })
    expect(sw.nav).toEqual(['/?abrir=demo'])
  })

  it('el resto de los avisos siguen igual', async () => {
    await sw.click({ session_id: 'abc', dialogo: false })
    await sw.click({})
    expect(sw.nav).toEqual(['/?session=abc', '/?chat=jefe'])
  })

  it('una notificación no reutiliza la ventana del notch', async () => {
    const swNotch = loadSw('', 'https://orq.example/notch')
    await swNotch.click({ session_id: 's1' })
    expect(swNotch.win.navigate).not.toHaveBeenCalled()
    expect(swNotch.opened).toEqual(['/?session=s1'])
  })
})

describe('service worker: cerrar notificaciones al abrir el destino', () => {
  let sw: ReturnType<typeof loadSw>
  beforeEach(() => (sw = loadSw()))

  it('cierra solo las de esa sesión', async () => {
    const a = sw.notif({ session_id: 'abc' })
    const b = sw.notif({ session_id: 'otra' })
    const c = sw.notif({ session_id: '', pane: 'w1:p2' })
    await sw.message({ type: 'orq-cerrar', session_id: 'abc' })
    expect([a.close.mock.calls.length, b.close.mock.calls.length, c.close.mock.calls.length]).toEqual([1, 0, 0])
  })

  it('cierra las de una terminal y las de una pieza', async () => {
    const t = sw.notif({ session_id: '', pane: 'w1:p2' })
    const h = sw.notif({ session_id: '', abrir: 'demo', fecha: '2026-10-30' })
    const s = sw.notif({ session_id: 'abc' })
    await sw.message({ type: 'orq-cerrar', pane_id: 'w1:p2' })
    await sw.message({ type: 'orq-cerrar', kind: 'demo' })
    expect([t.close.mock.calls.length, h.close.mock.calls.length, s.close.mock.calls.length]).toEqual([1, 1, 0])
  })

  it.each([{}, { type: 'otro', session_id: 'abc' }, { type: 'orq-cerrar' }, { type: 'orq-cerrar', session_id: '../x y' },
    { type: 'orq-cerrar', kind: 'done' }, null, 'orq-cerrar'])('ignora mensajes inválidos %j', async (msg) => {
    const a = sw.notif({ session_id: 'abc', pane: 'w1:p2', abrir: 'demo' })
    await sw.message(msg)
    expect(a.close).not.toHaveBeenCalled()
  })
})

describe('service worker: avisos de MRs', () => {
  let sw: ReturnType<typeof loadSw>
  beforeEach(() => (sw = loadSw()))

  it('guarda el MR válido y al tocar abre la sección en ese MR', async () => {
    const n = await sw.push({ title: 'Falló el pipeline', kind: 'mr', mr: '101:412', tag: 'mr-101:412' })
    expect(n.opts.data.mr).toBe('101:412')
    await sw.click(n.opts.data)
    expect(sw.nav).toEqual(['/?mr=101:412'])
  })

  it.each(['101:4&x=1', '../1:2', 'a:1', 7])('descarta un MR inválido %s', async (mr) => {
    const n = await sw.push({ kind: 'mr', mr })
    expect(n.opts.data.mr).toBe('')
    await sw.click({ mr, session_id: '' })
    expect(sw.nav).toEqual(['/?chat=jefe'])
  })

  it('cierra las notificaciones del MR que se abrió en la app', async () => {
    const a = sw.notif({ mr: '1:2' })
    const b = sw.notif({ mr: '1:3' })
    await sw.message({ type: 'orq-cerrar', mr: '1:2' })
    expect(a.close).toHaveBeenCalled()
    expect(b.close).not.toHaveBeenCalled()
  })
})

describe('service worker: pedido de pestaña', () => {
  const uuid = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
  let sw: ReturnType<typeof loadSw>
  beforeEach(() => (sw = loadSw()))

  it('guarda el pedido desde d.pedido y al tocar abre la URL del pedido', async () => {
    const n = await sw.push({ title: 'Pedido', kind: 'pestana', pedido: uuid, url: `/?pedido=${uuid}`, session_id: 'ses-x' })
    expect(n.opts.data.pedido).toBe(uuid)
    await sw.click({ ...n.opts.data, session_id: 'ses-x', mr: '1:2', abrir: 'demo' })
    expect(sw.nav).toEqual([`/?pedido=${uuid}`])
  })

  it('extrae el pedido desde d.url si no viene d.pedido', async () => {
    const n = await sw.push({ kind: 'pestana', url: `/?pedido=${uuid}` })
    expect(n.opts.data.pedido).toBe(uuid)
  })

  it.each(['not-a-uuid', '../x', ''])('deja pedido vacío si es inválido %s', async (pedido) => {
    const n = await sw.push({ kind: 'pestana', pedido, url: `/?pedido=${pedido}` })
    expect(n.opts.data.pedido).toBe('')
  })
})

describe('service worker: renotify por kind', () => {
  let sw: ReturnType<typeof loadSw>
  beforeEach(() => (sw = loadSw()))

  it('progreso con tag no renotifica (se reemplaza en silencio)', async () => {
    const n = await sw.push({ title: 'Viene avanzando', kind: 'progreso', tag: 'progreso-enc-1' })
    expect(n.opts.tag).toBe('progreso-enc-1')
    expect(n.opts.renotify).toBe(false)
  })

  it('done con tag sigue renotificando', async () => {
    const n = await sw.push({ title: 'Terminó', kind: 'done', tag: 'ses-abc', session_id: 'abc' })
    expect(n.opts.tag).toBe('ses-abc')
    expect(n.opts.renotify).toBe(true)
  })
})

describe('service worker: cerrar por tag', () => {
  const chromeUa = 'Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0 Mobile Safari/537.36'
  const iphoneUa = 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'

  it('push cerrar cierra solo tags válidos y en Chrome no muestra nada', async () => {
    const sw = loadSw(chromeUa)
    const a = sw.notif({}, 'tag-a')
    const b = sw.notif({}, 'tag-b')
    const c = sw.notif({}, 'otro')
    await sw.push({ kind: 'cerrar', tags: ['tag-a', 'a b', 9, 'x'.repeat(200)] })
    expect([a.close.mock.calls.length, b.close.mock.calls.length, c.close.mock.calls.length]).toEqual([1, 0, 0])
    expect(sw.shown).toHaveLength(0)
  })

  it('en iPhone muestra una notificación silenciosa con el primer tag y la cierra', async () => {
    const sw = loadSw(iphoneUa)
    sw.notif({}, 'tag-a')
    await sw.push({ kind: 'cerrar', tags: ['tag-a', 'tag-b'] })
    expect(sw.shown).toHaveLength(1)
    expect(sw.shown[0].opts).toMatchObject({ tag: 'tag-a', silent: true })
    expect(sw.notifications[sw.notifications.length - 1]?.close).toHaveBeenCalled()
  })

  it('orq-cerrar con tags cierra por tag', async () => {
    const sw = loadSw()
    const a = sw.notif({}, 'mr-1:2')
    const b = sw.notif({ session_id: 'abc' })
    await sw.message({ type: 'orq-cerrar', tags: ['mr-1:2', 'a b'] })
    expect(a.close).toHaveBeenCalled()
    expect(b.close).not.toHaveBeenCalled()
  })
})
