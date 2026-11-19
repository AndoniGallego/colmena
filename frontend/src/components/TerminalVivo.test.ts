import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const termMock = vi.hoisted(() => {
  const instances: {
    open: ReturnType<typeof vi.fn>
    write: ReturnType<typeof vi.fn>
    reset: ReturnType<typeof vi.fn>
    resize: ReturnType<typeof vi.fn>
    dispose: ReturnType<typeof vi.fn>
    options: { fontSize: number; theme: Record<string, string> }
    element: { querySelector: () => null }
  }[] = []
  class Terminal {
    open = vi.fn()
    write = vi.fn()
    reset = vi.fn()
    resize = vi.fn()
    dispose = vi.fn()
    options = { fontSize: 13, theme: {} as Record<string, string> }
    element = { querySelector: () => null }
    constructor() {
      instances.push(this)
    }
  }
  return { Terminal, instances }
})

let onFoto: ((f: { columnas: number; filas: number; texto: string }) => void) | null = null
let onEstado: ((e: string, msg?: string, extra?: { codigo?: number | null; reintentar?: boolean }) => void) | null = null
let alAbrir: (() => void) | null = null

vi.mock('@xterm/xterm', () => ({ Terminal: termMock.Terminal }))
vi.mock('@xterm/xterm/css/xterm.css', () => ({}))

vi.mock('../lib/vivo', async (importOriginal) => {
  const orig = await importOriginal<typeof import('../lib/vivo')>()
  class ConexionVivoMock {
    abrir = vi.fn()
    cerrar = vi.fn()
    reintentar = vi.fn()
    despertar = vi.fn()
    constructor(opts: { onFoto: typeof onFoto; onEstado: typeof onEstado }) {
      onFoto = opts.onFoto
      onEstado = opts.onEstado
      this.abrir.mockImplementation(() => {
        onEstado?.('conectando')
        alAbrir?.()
      })
    }
  }
  return { ...orig, ConexionVivo: ConexionVivoMock }
})

vi.mock('../motion', () => ({
  finePointer: () => false,
  haptic: () => {},
  isSoft: () => true,
  soft: { value: true },
  ring: () => {},
  burst: () => {},
  cascadeDelay: () => 0,
  brandHop: { value: 0 },
  gsap: { set() {}, to() {}, from() {}, killTweensOf() {}, utils: { selector: () => () => [] } },
  useGsap: () => ({ run: (fn: () => void) => fn() }),
}))

vi.mock('../lib/viewport', () => ({ desktop: { value: true } }))
vi.mock('../state/terminalWrite', () => ({
  ventanaAbierta: { value: false },
  ventana: { token: '', venceAt: 0, idleAt: 0, inactividad: 0, now: Date.now() },
  countdown: { value: 0 },
  forgetVentana: vi.fn(),
  openVentana: vi.fn(),
  pinProblem: () => ({ message: 'x', retryAfter: null }),
  touchVentana: vi.fn(),
}))
vi.mock('./Icon.vue', () => ({ default: { props: ['name', 'size'], template: '<i />' } }))
vi.mock('./LogoLoader.vue', () => ({ default: { template: '<span class="loader" />' } }))

vi.stubGlobal('window', {
  matchMedia: () => ({ matches: true, addEventListener() {} }),
  addEventListener() {},
  removeEventListener() {},
  setTimeout: (fn: () => void) => {
    fn()
    return 0
  },
  clearTimeout: () => {},
})
vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => {} })
vi.stubGlobal('getComputedStyle', () => ({ getPropertyValue: (k: string) => (k === '--font-mono' ? 'monospace' : '#000') }))
vi.stubGlobal('location', { protocol: 'http:', host: 'localhost' })
vi.stubGlobal('MutationObserver', class {
  observe() {}
  disconnect() {}
})
vi.stubGlobal('ResizeObserver', class {
  observe() {}
  disconnect() {}
})

vi.stubGlobal('document', {
  visibilityState: 'visible',
  hidden: false,
  addEventListener() {},
  removeEventListener() {},
  documentElement: { dataset: {}, toggleAttribute() {}, setAttribute() {} },
  createElement: () => ({
    style: {},
    setAttribute: () => {},
    classList: { add: () => {} },
    querySelector: () => null,
    appendChild: () => {},
  }),
  body: { innerHTML: '' },
})

const { vivoAbierto, cerrarVivo } = await import('../state/terminalVivo')
const { default: TerminalVivo } = await import('./TerminalVivo.vue')

beforeEach(() => {
  termMock.instances.length = 0
  onFoto = null
  onEstado = null
  alAbrir = null
  cerrarVivo()
})

describe('TerminalVivo', () => {
  it('muestra título y conectando al abrir', async () => {
    vivoAbierto.value = { paneId: 'g1:p1', titulo: 'Mi sesión' }
    const html = await renderToString(createSSRApp({ render: () => h(TerminalVivo) }))
    expect(html).toContain('Mi sesión')
    expect(html).toContain('Conectando')
  })

  it('resize y write al recibir foto', async () => {
    vivoAbierto.value = { paneId: 'g1:p1', titulo: 'T' }
    await renderToString(createSSRApp({ render: () => h(TerminalVivo) }))
    onFoto?.({ columnas: 100, filas: 30, texto: 'pantalla' })
    const t = termMock.instances[0]
    expect(t?.resize).toHaveBeenCalledWith(100, 30)
    expect(t?.write).toHaveBeenCalledWith('pantalla')
  })

  it('al montar usa consumirPedirPinAlAbrir y debeMostrarPinAlAbrir', async () => {
    const fs = await import('node:fs')
    const src = fs.readFileSync(new URL('./TerminalVivo.vue', import.meta.url).pathname, 'utf8')
    expect(src).toContain('consumirPedirPinAlAbrir')
    expect(src).toContain('quizasAbrirPinAlMontar')
    expect(src).toContain('debeMostrarPinAlAbrir')
  })

  it('cerrar limpia vivoAbierto', async () => {
    vivoAbierto.value = { paneId: 'g1:p1', titulo: 'T' }
    await renderToString(createSSRApp({ render: () => h(TerminalVivo) }))
    cerrarVivo()
    expect(vivoAbierto.value).toBeNull()
  })
})

describe('TerminalVivo textos', () => {
  it('no incluye la palabra prohibida en textos visibles', async () => {
    vivoAbierto.value = { paneId: 'g1:p1', titulo: 'T' }
    const html = await renderToString(createSSRApp({ render: () => h(TerminalVivo) }))
    expect(html.toLowerCase()).not.toMatch(/\bflujo\b/)
  })

  it('TerminalVivo.vue y vivo.ts sin la palabra', async () => {
    const fs = await import('node:fs')
    for (const f of ['TerminalVivo.vue', '../lib/vivo.ts']) {
      const t = fs.readFileSync(new URL(f, import.meta.url).pathname, 'utf8').toLowerCase()
      expect(t).not.toMatch(/\bflujo\b/)
    }
  })

  it('muestra copy de sesión terminada en el template', async () => {
    const fs = await import('node:fs')
    const src = fs.readFileSync(new URL('./TerminalVivo.vue', import.meta.url).pathname, 'utf8')
    expect(src).toContain('La sesión terminó')
    expect(src).toContain('term?.dispose()')
  })
})
