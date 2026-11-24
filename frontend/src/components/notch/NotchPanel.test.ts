import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it, vi } from 'vitest'

vi.hoisted(() => {
  vi.stubGlobal('window', { matchMedia: () => ({ matches: false, addEventListener() {} }), addEventListener() {} })
})

const formaMock = vi.hoisted(() => ({ forma: { tipo: 'abrir', motivo: 'Contestala en Colmena' } as unknown }))

vi.mock('../../state/notchRespuesta', () => ({
  activa: { value: null },
  filas: {},
  activar: vi.fn(),
  elegirOpcion: vi.fn(),
  mandarTexto: vi.fn(),
  resolverPermiso: vi.fn(),
  resolverPedido: vi.fn(),
  formaDe: () => formaMock.forma,
}))

import type { SesionNotch } from '../../lib/notchCeldas'

vi.mock('../../motion', async () => {
  const { ref } = await import('vue')
  return {
    gsap: {
      set() {},
      to() {},
      fromTo() {},
      from() {},
      timeline: () => ({ to() { return this }, fromTo() { return this }, kill() {} }),
      delayedCall() {},
      utils: { random: () => 1 },
    },
    isSoft: () => true,
    soft: ref(true),
    brandHop: ref(0),
    useGsap: () => ({ run: (fn: () => void) => fn() }),
  }
})

const NOW = Date.parse('2026-11-04T18:00:00Z')

function s(id: string, estado: SesionNotch['estado']): SesionNotch {
  return {
    pane_id: 'p' + id,
    session_id: id,
    titulo: 't-' + id,
    donde: 'Acme · 1',
    estado,
    motivo: null,
    preguntas: 0,
    desdeMs: null,
    linea: 'linea',
    last_activity: null,
    hue: 120,
  }
}

type GruposProps = {
  teToca: SesionNotch[]
  trabajando: SesionNotch[]
  termino: SesionNotch[]
  otras: SesionNotch[]
  fuera: number
}

const render = async (props: { grupos: GruposProps; now: number; initialOtrasDesplegadas?: boolean; reunionDisponible?: boolean }) => {
  const { default: NotchPanel } = await import('./NotchPanel.vue')
  return renderToString(createSSRApp({ render: () => h(NotchPanel, props) }))
}

describe('NotchPanel', () => {
  it('el grupo Te toca muestra el renglón del pedido con Abrir y No', async () => {
    formaMock.forma = {
      tipo: 'pedido',
      pedidoId: 'p1',
      titulo: 'Abrir pestaña',
      detalle: '/tmp/demo',
      boton: 'Abrir',
      aviso: '',
      enviando: false,
      error: '',
    }
    const html = await render({
      grupos: { teToca: [{ ...s('a', 'te-toca'), motivo: 'pedido' }], trabajando: [], termino: [], otras: [], fuera: 0 },
      now: NOW,
    })
    formaMock.forma = { tipo: 'abrir', motivo: 'Contestala en Colmena' }
    expect(html).toContain('Abrir pestaña')
    expect(html).toContain('>Abrir<')
    expect(html).toContain('>No<')
    expect(html).not.toContain('Ver opciones')
  })

  it('muestra solo los grupos con sesiones, lo que quedó afuera y el pie', async () => {
    const html = await render({
      grupos: {
        teToca: [s('a', 'te-toca')],
        trabajando: [s('b', 'trabajando')],
        termino: [],
        otras: [s('c', 'tranquila'), s('d', 'tranquila')],
        fuera: 2,
      },
      now: NOW,
    })
    expect(html).toContain('Te toca')
    expect(html).toContain('Trabajando')
    expect(html).not.toContain('>Terminó<')
    expect(html).toContain('Ver 2 sesiones más')
    expect(html).not.toContain('>Otras<')
    expect(html).not.toContain('t-c')
    expect(html).toContain('Tocá una sesión para abrirla en Colmena')
    expect(html).toContain('Abrir Colmena')
  })

  it('una sola de más va en singular', async () => {
    const html = await render({
      grupos: { teToca: [s('a', 'te-toca')], trabajando: [], termino: [], otras: [s('x', 'tranquila')], fuera: 1 },
      now: NOW,
    })
    expect(html).toContain('Ver 1 sesión más')
    expect(html).not.toContain('Ver 1 sesiones más')
  })

  it('desplegado muestra Otras y las filas', async () => {
    const html = await render({
      grupos: {
        teToca: [],
        trabajando: [],
        termino: [],
        otras: [s('z', 'tranquila')],
        fuera: 1,
      },
      now: NOW,
      initialOtrasDesplegadas: true,
    })
    expect(html).toContain('>Otras<')
    expect(html).toContain('t-z')
    expect(html).toContain('Ocultar')
  })

  it('sin otras no muestra el botón', async () => {
    const html = await render({
      grupos: { teToca: [s('a', 'te-toca')], trabajando: [], termino: [], otras: [], fuera: 0 },
      now: NOW,
    })
    expect(html).not.toContain('class="mas"')
    expect(html).not.toContain('sesiones más')
  })

  it('la sección Notas es la lista con su cabecera y Anotar', async () => {
    const html = await render({
      grupos: { teToca: [], trabajando: [], termino: [], otras: [], fuera: 0 },
      now: NOW,
    })
    expect(html).toContain('class="notas-cab"')
    expect(html).toContain('Notas')
    expect(html).toContain('Anotar')
    expect(html).toContain('Sin notas. Anotá lo que no te querés olvidar.')
    expect(html).not.toContain('panal')
  })

  it('el botón Reunión aparece solo en la app de Windows', async () => {
    const grupos = { teToca: [], trabajando: [], termino: [], otras: [], fuera: 0 }
    expect(await render({ grupos, now: NOW })).not.toContain('Reunión')
    expect(await render({ grupos, now: NOW, reunionDisponible: true })).toContain('>Reunión</button>')
  })
})
