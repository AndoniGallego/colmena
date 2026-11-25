import { createSSRApp, h, ref } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it, vi } from 'vitest'

vi.stubGlobal('window', {
  matchMedia: () => ({ matches: true, addEventListener() {}, removeEventListener() {} }),
  innerWidth: 1200,
  addEventListener() {},
  removeEventListener() {},
})

vi.mock('../motion', () => ({
  gsap: {
    from() {},
    fromTo() {},
    utils: { selector: () => () => [] },
  },
  isSoft: () => true,
  ring: () => {},
  useGsap: () => ({ run: (fn: () => void) => fn() }),
}))

vi.mock('../lib/viewport', () => ({ desktop: ref(true) }))

vi.mock('../state/app', () => ({
  boardState: ref({
    connection: 'live',
    board: null,
  }),
  jumpTo: vi.fn(),
  revokeAllSessions: vi.fn(async () => true),
}))

vi.mock('../state/biblioteca', () => ({ lib: { newCount: 0 }, libVisible: ref(false) }))
const demoVisible = vi.hoisted(() => ({ v: null as null | { value: boolean } }))
vi.mock('../piezas', async () => {
  const { ref: r } = await import('vue')
  const visible = r(false)
  demoVisible.v = visible
  return { piezas: () => [{ id: 'demo', seccion: { titulo: 'Demo', icono: 'clock', vista: {}, visible } }] }
})
vi.mock('../state/mrs', () => ({ mrs: { habilitado: false }, mrsVisible: ref(false), pendientesMrs: ref(false) }))
vi.mock('../state/limpieza', () => ({ abrirLimpieza: vi.fn() }))
vi.mock('../lib/theme', () => ({ theme: ref('light'), setTheme: vi.fn() }))
vi.mock('../state/ajustes', () => ({ openAjustes: vi.fn() }))
vi.mock('../state/entornos', () => ({ openEntornos: vi.fn() }))
vi.mock('../state/buscador', () => ({ abrirPaleta: vi.fn(), ATAJO: '⌘K' }))
vi.mock('../lib/time', () => ({
  useNow: () => ref(Date.now()),
  clock: (t: number) => String(t),
}))

vi.mock('./BrandLockup.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./Icon.vue', () => ({ default: { name: 'Icon', render: () => null } }))
vi.mock('./NavMark.vue', () => ({ default: { template: '<span />' } }))
vi.mock('./AvisosBell.vue', () => ({ default: { template: '<div class="bell" />' } }))
vi.mock('./RollingNumber.vue', () => ({ default: { template: '<span>0</span>' } }))

const { default: TopBar } = await import('./TopBar.vue')

async function renderBar(props: { compact?: boolean }) {
  const ctx: { teleports?: Record<string, string> } = {}
  await renderToString(createSSRApp({ render: () => h(TopBar, props) }), ctx)
  const body = ctx.teleports?.body ?? ''
  const main = await renderToString(createSSRApp({ render: () => h(TopBar, props) }))
  return main + body
}

describe('TopBar', () => {
  it('en escritorio (!compact) muestra cuatro acciones y no el menú de puntos', async () => {
    const html = await renderBar({ compact: false })
    expect(html).toContain('aria-label="Ajustes"')
    expect(html).toContain('aria-label="Entornos"')
    expect(html).toContain('aria-label="Limpiar sesiones"')
    expect(html).toContain('aria-label="Salir de Colmena"')
    expect(html).not.toContain('Más opciones')
  })

  it('en escritorio ofrece el botón de Tareas programadas', async () => {
    const html = await renderBar({ compact: false })
    expect(html).toContain('aria-label="Tareas programadas"')
  })

  it('los íconos de escritorio no llevan title y sí la descripción accesible', async () => {
    const html = await renderBar({ compact: false })
    for (const n of ['Ajustes', 'Entornos', 'Kit', 'Tareas programadas', 'Limpiar sesiones', 'Salir de Colmena', 'Tema oscuro']) {
      const tag = html.match(new RegExp(`<button[^>]*aria-label="${n}"[^>]*>`))?.[0] ?? ''
      expect(tag, n).not.toBe('')
      expect(tag, n).not.toContain('title=')
      expect(tag, n).toContain('aria-description=')
    }
    expect(html).toMatch(/class="conn"[^>]*aria-description="Conexión en vivo con la notebook"/)
    expect(html).toContain('aria-description="Pedidos que corren solos a su hora"')
  })

  it('en celu (compact) mantiene el menú de puntos', async () => {
    const html = await renderBar({ compact: true })
    expect(html).toContain('aria-label="Más opciones"')
    expect(html).not.toContain('aria-label="Limpiar sesiones"')
  })

  it('las secciones de piezas van entre MRs y Notas, y apagan el Tablero', async () => {
    const html = await renderBar({ compact: false })
    const titulos = [...html.matchAll(/class="sec[^"]*"[^>]*title="([^"]+)"|title="([^"]+)"[^>]*class="sec/g)].map((m) => m[1] ?? m[2])
    expect(titulos.indexOf('Demo')).toBe(titulos.indexOf('Notas') - 1)
    expect(html).toMatch(/title="Tablero"[^>]*aria-current="page"|aria-current="page"[^>]*title="Tablero"/)
    demoVisible.v!.value = true
    const conPieza = await renderBar({ compact: false })
    expect(conPieza).not.toMatch(/title="Tablero"[^>]*aria-current="page"/)
    expect(conPieza).toMatch(/title="Demo"[^>]*aria-current="page"/)
    demoVisible.v!.value = false
  })
})
