import { createSSRApp, h, reactive } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Aviso } from '../api/types'

vi.hoisted(() => {
  vi.stubGlobal('window', {
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    innerWidth: 800,
    addEventListener() {},
    removeEventListener() {},
  })
})

vi.mock('../motion', () => ({
  gsap: { fromTo() {}, from() {} },
  haptic: () => {},
  isSoft: () => true,
  useGsap: () => ({ run: (fn: () => void) => fn() }),
}))

vi.mock('../lib/viewport', () => ({ desktop: { value: false } }))

const av = reactive({
  open: true,
  loading: false,
  loadingMore: false,
  loaded: true,
  error: '',
  items: [] as Aviso[],
  hayMas: false,
  noLeidos: 0,
  leidosHasta: 0,
  nuevosDesde: 0,
})

vi.mock('../piezas', () => ({
  piezas: () => [{ id: 'demo', avisos: { kind: 'demo', icono: 'calendar', etiqueta: 'Demo', acento: true, abierto: () => false, ir: () => {} } }],
}))

vi.mock('../state/avisos', () => ({
  av,
  abrirAvisos: vi.fn(),
  cerrarAvisos: vi.fn(),
  irAAviso: vi.fn(),
  marcarTodoLeido: vi.fn(),
  masAvisos: vi.fn(),
  refrescarAvisos: vi.fn(),
}))

const pedidoCierre = {
  id: '550e8400-e29b-41d4-a716-446655440000',
  accion: 'cerrar',
  carpeta: '/home/usuario/proyecto',
  mensaje: '',
  origen: { pane_id: 'w1:p1', nombre: 'Origen', session_id: '' },
  ts: 1_800_000_000,
  vence: 1_900_000_000,
  cierre: {
    objetivo: 'pestana',
    tipo: 'tab',
    target_id: 'w1:t1',
    label: 'API',
    workspace_label: 'Tienda',
    carpeta: '/home/usuario/proyecto',
    sesiones: 1,
    terminales: 0,
  },
}
const pedidosPestanaMock = reactive({
  listo: false,
  listoTxt: '',
  porId: {} as Record<string, { vista?: unknown; enviando?: boolean; error?: string }>,
})
vi.mock('../state/pedidosPestana', () => ({
  pedidosPestana: pedidosPestanaMock,
  pedidoPestanaPorId: () => pedidoCierre,
  pedidoPestanaPendiente: () => true,
  abrirPedidoPestana: vi.fn(),
  rechazarPedidoPestana: vi.fn(),
}))

const mk = (over: Partial<Aviso> = {}): Aviso => ({
  id: 1,
  ts: Math.floor(new Date(2026, 10, 5, 14, 30).getTime() / 1000),
  kind: 'asks',
  titulo: '¿Sigo?',
  cuerpo: '',
  session_id: 's1',
  pane_id: '',
  fecha: '2026-11-05',
  mr: '',
  tag: '',
  entregado: true,
  leido: false,
  motivo: '',
  ...over,
})

const render = async () => {
  const { default: AvisosBell } = await import('./AvisosBell.vue')
  const ctx: { teleports?: Record<string, string> } = {}
  await renderToString(createSSRApp({ render: () => h(AvisosBell) }), ctx)
  return ctx.teleports?.body ?? ''
}

describe('AvisosBell', () => {
  beforeEach(() => {
    av.open = true
    av.loaded = true
    av.loading = false
    av.items = []
    av.noLeidos = 0
    av.nuevosDesde = 0
  })

  it('la hora no usa mono y no repite la etiqueta del tipo', async () => {
    av.items = [mk({ kind: 'asks', titulo: '¿Sigo?' }), mk({ id: 2, kind: 'done', titulo: 'Listo', ts: mk().ts - 60 })]
    const html = await render()
    expect(html).toMatch(/<time[^>]*>14:30<\/time>/)
    expect(html).not.toMatch(/<time[^>]*class="[^"]*mono/)
    expect(html).not.toContain('>Pregunta<')
    expect(html).not.toContain('>Terminó<')
  })

  it('solo muestra meta cuando no fue entregado', async () => {
    av.items = [mk({ entregado: true }), mk({ id: 2, entregado: false, motivo: 'push', titulo: 'Otro' })]
    const html = await render()
    expect(html.match(/class="meta"/g)?.length ?? 0).toBe(1)
    expect(html).toContain('No llegó al celu')
    expect(html).not.toContain('Estabas en la app')
  })

  it('pasa la vista a la tarjeta de un pedido de cierre', async () => {
    av.items = [mk({ kind: 'pestana', pedido: pedidoCierre.id, titulo: 'Cerrar' })]
    pedidosPestanaMock.porId = { [pedidoCierre.id]: { vista: { trabajando: true, estados: ['working'], huella: 'h' } } }
    expect(await render()).toContain('Cerrar igual')
    pedidosPestanaMock.porId = {}
    const sin = await render()
    expect(sin).not.toContain('Cerrar igual')
    expect(sin).toContain('Cerrar pestaña')
  })

  it('un aviso de pieza usa su ícono y el acento', async () => {
    av.items = [mk({ kind: 'demo', titulo: 'De la pieza' }), mk({ id: 2, kind: 'done', titulo: 'Listo', ts: mk().ts - 60 })]
    const html = await render()
    expect(html).toMatch(/k-demo[^"]*acento/)
    expect(html).not.toMatch(/k-done[^"]*acento/)
  })

  it('la campana no lleva title y sí la descripción accesible', async () => {
    const { default: AvisosBell } = await import('./AvisosBell.vue')
    const tag = (await renderToString(createSSRApp({ render: () => h(AvisosBell) }))).match(/<button[^>]*class="bell[^>]*>/)?.[0] ?? ''
    expect(tag).not.toBe('')
    expect(tag).not.toContain('title=')
    expect(tag).toContain('aria-description="Lo que pidieron o terminaron las sesiones"')
  })
})
