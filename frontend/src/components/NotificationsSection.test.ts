import { createSSRApp, h, reactive } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.stubGlobal('window', {
  matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
  innerWidth: 800,
  addEventListener() {},
  removeEventListener() {},
  scrollTo() {},
  visualViewport: null,
})

vi.mock('../motion', () => ({
  gsap: { from() {}, fromTo() {} },
  isSoft: () => true,
  ring() {},
  useGsap: () => ({ run: (fn: () => void) => fn() }),
}))

vi.mock('../state/app', () => ({}))

const pushState = reactive({
  status: 'programa' as string,
  prefs: {
    asks: true,
    blocked: true,
    done: true,
    texto: true,
    demo: true,
    cierre: true,
    mrs: true,
    entornos: true,
    progreso: true,
    pestana: true,
  },
  busy: false,
  error: '',
  device: 'x',
  endpoint: '',
})

vi.mock('../state/push', () => ({
  pushState,
  refreshPush: vi.fn(),
  disablePush: vi.fn(),
  enablePush: vi.fn(),
  setPushPref: vi.fn(),
  testPush: vi.fn(),
  probarEnvio: vi.fn(),
  testCierre: vi.fn(),
  runProbarAviso: vi.fn(),
}))

vi.mock('../piezas', () => ({
  piezas: () => [
    {
      id: 'demo',
      notificaciones: {
        pref: { key: 'demo', label: 'Aviso de la pieza demo', hint: 'Cuando la pieza quiere' },
        probar: async () => {},
        probarEtiqueta: 'Probar el aviso demo',
        filaPrueba: { kind: 'demo', label: 'Demo' },
      },
    },
  ],
}))

vi.mock('./Icon.vue', () => ({ default: { name: 'Icon', render: () => null } }))

const { default: NotificationsSection } = await import('./NotificationsSection.vue')

async function html() {
  return renderToString(createSSRApp({ render: () => h(NotificationsSection) }))
}

describe('NotificationsSection', () => {
  beforeEach(() => {
    pushState.status = 'programa'
    pushState.busy = false
  })

  it('en programa de Windows muestra Probar avisos y En el notch en asks/blocked/done', async () => {
    const out = await html()
    expect(out).toContain('Probar avisos')
    const rowAsks = out.match(/data-kind="asks"[\s\S]*?<\/div>\s*<\/div>/i)?.[0] ?? ''
    expect(rowAsks).toContain('En el notch')
    expect(rowAsks).toContain('Al celu')
  })

  it('muestra el interruptor Entornos con su descripción', async () => {
    pushState.status = 'on'
    const out = await html()
    expect(out).toContain('Entornos')
    expect(out).toContain('Si un contenedor se cae solo o queda con problemas')
  })

  it('fuera del programa no hay botón En el notch', async () => {
    pushState.status = 'on'
    const out = await html()
    expect(out).not.toContain('En el notch')
    expect(out).toContain('Al celu')
  })

  it('la pref de una pieza va antes del cierre, con su botón Probar', async () => {
    pushState.status = 'on'
    const out = await html()
    expect(out.indexOf('Aviso de la pieza demo')).toBeGreaterThan(out.indexOf('Terminó'))
    expect(out.indexOf('Aviso de la pieza demo')).toBeLessThan(out.indexOf('Cierre del día'))
    expect(out).toContain('aria-label="Probar el aviso demo"')
    expect(out).toContain('aria-label="Probar el cierre del día"')
  })

  it('la fila de prueba de una pieza va después de Terminal', async () => {
    const out = await html()
    const kinds = [...out.matchAll(/data-kind="([a-z]+)"/g)].map((m) => m[1])
    expect(kinds.indexOf('demo')).toBe(kinds.indexOf('terminal') + 1)
  })
})
