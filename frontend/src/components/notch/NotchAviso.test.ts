import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it, vi } from 'vitest'
import type { SesionNotch } from '../../lib/notchCeldas'
import { abrirSesionDesdeAvisoSimple, type AvisoNotch } from '../../lib/notchAvisos'

vi.hoisted(() => {
  vi.stubGlobal('window', {
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    addEventListener() {},
  })
})

vi.mock('../../motion', async () => {
  const { ref } = await import('vue')
  return {
    gsap: {
      set() {},
      to() {},
      fromTo() {},
      from() {},
      killTweensOf() {},
      delayedCall() {},
    },
    isSoft: () => true,
    soft: ref(true),
    useGsap: () => ({ run: (fn: () => void) => fn() }),
  }
})

vi.mock('../../piezas', () => ({ piezas: () => [] }))

vi.mock('../../state/pedidosPestana', () => ({
  pedidosPestana: { porId: {} },
  pedidoPestanaPorId: () => ({
    id: '550e8400-e29b-41d4-a716-446655440000',
    carpeta: '/home/usuario/tienda',
    mensaje: 'Contexto largo',
    origen: { pane_id: 'w:p', nombre: 'tienda sonarqube' },
    ts: 1_800_000_000,
    vence: 1_800_000_900,
  }),
  abrirPedidoPestana: vi.fn(),
  rechazarPedidoPestana: vi.fn(),
}))

const NOW = Date.parse('2026-11-04T18:00:00Z')

const teToca: SesionNotch = {
  pane_id: 'pa',
  session_id: 'a',
  titulo: 'Sesión a',
  donde: 'Acme · 1',
  estado: 'te-toca',
  motivo: 'pregunta',
  preguntas: 0,
  desdeMs: null,
  linea: 'Te toca',
  last_activity: null,
  hue: 120,
}

const doneAviso = (): AvisoNotch => ({
  id: 1,
  kind: 'done',
  titulo: 'Terminó Notch',
  cuerpo: 'Los tests pasan',
  session_id: 's',
})

const render = async (props: { aviso: AvisoNotch; sesion: SesionNotch | null; now: number }) => {
  const { default: NotchAviso } = await import('./NotchAviso.vue')
  return renderToString(createSSRApp({ render: () => h(NotchAviso, props) }))
}

describe('NotchAviso', () => {
  it('simple done muestra nombre sin sufijo del backend', async () => {
    const html = await render({
      aviso: {
        id: 4,
        kind: 'done',
        titulo: 'Colmena terminó',
        cuerpo: 'Quedó listo',
        session_id: 's',
      },
      sesion: null,
      now: NOW,
    })
    expect(html).toContain('>Colmena<')
    expect(html).toContain('k-done')
    expect(html).toContain('simple')
    expect(html).not.toContain('Colmena terminó')
  })

  it('terminó muestra el texto y la barra', async () => {
    const html = await render({
      aviso: {
        id: 1,
        kind: 'done',
        titulo: 'Terminó Notch',
        cuerpo: 'Los tests pasan',
        session_id: 's',
      },
      sesion: null,
      now: NOW,
    })
    expect(html).toContain('Terminó Notch')
    expect(html).toContain('Los tests pasan')
    expect(html).toMatch(/\bico\b/)
    expect(html).not.toContain('class="dot"')
    expect(html).toContain('class="prog"')
    expect(html).toContain('aria-label="Cerrar aviso"')
    const closeIdx = html.indexOf('aria-label="Cerrar aviso"')
    const progIdx = html.indexOf('class="prog"')
    expect(closeIdx).toBeLessThan(progIdx)
  })

  it('terminó pone el tiempo en .l1 y la barra en columna de texto', async () => {
    const html = await render({
      aviso: {
        id: 3,
        kind: 'done',
        titulo: 'Terminó',
        cuerpo: 'Listo',
        session_id: 's',
      },
      sesion: null,
      now: NOW,
    })
    const l1Start = html.indexOf('class="l1"')
    expect(l1Start).toBeGreaterThan(-1)
    const l1End = html.indexOf('</div>', l1Start)
    expect(html.slice(l1Start, l1End)).toContain('class="when"')
    expect(html.slice(l1Start, l1End)).toContain('ahora')
    expect(html).not.toContain('class="t"')
    expect(html).toContain('class="prog"')
  })

  it('terminó: .main es accionable para abrir sesión', async () => {
    const html = await render({ aviso: doneAviso(), sesion: null, now: NOW })
    expect(html).toContain('role="button"')
    expect(html).toContain('tabindex="0"')
    expect(html).toContain('aria-label="Abrir sesión"')
  })

  it('click en .main usa session_id para abrir-sesion (misma regla que el handler)', () => {
    expect(abrirSesionDesdeAvisoSimple('s-done')).toBe('s-done')
  })

  it('cerrar con × no pasa por abrirSesionDesdeAvisoSimple', () => {
    expect(abrirSesionDesdeAvisoSimple('')).toBeNull()
  })

  it('pedido de pestaña: toast ancho, sin simple, tarjeta en modo notch', async () => {
    const html = await render({
      aviso: {
        id: 9,
        kind: 'pestana',
        titulo: 'Pedido de pestaña',
        cuerpo: 'Una sesión pide abrir pestaña',
        session_id: 's',
        pedido: '550e8400-e29b-41d4-a716-446655440000',
      },
      sesion: null,
      now: NOW,
    })
    expect(html).toMatch(/\bpestana\b/)
    expect(html).not.toMatch(/\bsimple\b/)
    expect(html).toMatch(/class="[^"]*\bnotch\b[^"]*"/)
    expect(html).not.toMatch(/Pedido de pestaña/i)
    expect(html).toContain('tienda sonarqube')
    expect(html).toContain('aria-label="Cerrar aviso"')
  })

  it('te toca con sesión ofrece ver las opciones del diálogo', async () => {
    const html = await render({
      aviso: {
        id: 2,
        kind: 'asks',
        titulo: 't',
        cuerpo: 'c',
        session_id: 'a',
      },
      sesion: teToca,
      now: NOW,
    })
    expect(html).toContain('Ver opciones')
    expect(html).not.toContain('Escribir otra respuesta')
    expect(html).not.toContain('class="prog"')
    expect(html).toContain('class="titulo"')
    expect(html).toContain('aria-label="Abrir Sesión a en Colmena"')
  })
})
