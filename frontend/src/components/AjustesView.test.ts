import { createSSRApp, h, ref } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it, vi } from 'vitest'

vi.stubGlobal('window', {
  matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
  innerWidth: 800,
  addEventListener() {},
  removeEventListener() {},
  scrollTo() {},
  visualViewport: null,
})

vi.mock('../motion', () => ({
  gsap: { from() {} },
  isSoft: () => true,
  motionPref: ref('full'),
  setMotion: () => {},
  systemReduced: ref(false),
  useGsap: () => ({ run: (fn: () => void) => fn() }),
}))
vi.mock('../lib/viewport', () => ({ desktop: ref(false) }))
vi.mock('../lib/keyboard', () => ({
  useKeyboard: () => ({ open: ref(false), height: ref(null), top: ref(0) }),
}))
vi.mock('../lib/theme', () => ({ setTheme: () => {}, theme: ref('light') }))
vi.mock('../state/app', () => ({
  revokeAllSessions: vi.fn(async () => true),
}))
vi.mock('../state/ajustes', () => ({ closeAjustes: vi.fn() }))
vi.mock('../state/limpieza', () => ({ abrirLimpieza: vi.fn() }))

vi.mock('./Icon.vue', () => ({ default: { name: 'Icon', render: () => null } }))
vi.mock('./SegControl.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./ClaudePanel.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./NotificationsSection.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./PermisosHistorial.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./MemoriaSection.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./ViewFrame.vue', () => ({
  default: {
    name: 'ViewFrame',
    template: '<div><slot name="back" /><slot /></div>',
  },
}))

const { default: AjustesView } = await import('./AjustesView.vue')

describe('AjustesView', () => {
  it('no muestra la sección para elegir el logo de Colmena', async () => {
    const html = await renderToString(createSSRApp({ render: () => h(AjustesView) }))
    expect(html).not.toContain('Elegí la marca de Colmena')
  })

  it('muestra Memoria y Permisos, sin Centinela ni Dios', async () => {
    const html = await renderToString(createSSRApp({ render: () => h(AjustesView) }))
    expect(html).toContain('Memoria')
    expect(html).toContain('Permisos')
    expect(html).not.toMatch(/Centinela|Dios/)
  })
})
