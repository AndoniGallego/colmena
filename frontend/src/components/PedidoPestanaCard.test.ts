import { createSSRApp, defineComponent, h, provide, ssrContextKey, type SetupContext } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it, vi } from 'vitest'
import type { PedidoPestana } from '../api/types'

vi.mock('../motion', () => ({ gsap: {}, isSoft: () => true, useGsap: () => ({ run: (fn: () => void) => fn() }) }))
vi.mock('./Icon.vue', () => ({ default: { name: 'Icon', render: () => null } }))

const { default: PedidoPestanaCard } = await import('./PedidoPestanaCard.vue')

const base: PedidoPestana = {
  id: '550e8400-e29b-41d4-a716-446655440000',
  carpeta: '/home/usuario/proyecto',
  mensaje: 'Arrancá con este contexto',
  origen: { pane_id: 'w1:p1', nombre: 'Tienda plugins', session_id: '' },
  ts: 1_800_000_000,
  vence: 1_800_000_900,
}

type Card = typeof PedidoPestanaCard & {
  setup: NonNullable<(typeof PedidoPestanaCard)['setup']>
  ssrRender: (...args: unknown[]) => void
  __scopeId?: string
  props: Record<string, unknown>
}

const PC = PedidoPestanaCard as Card

function host(pedido: PedidoPestana, emit: SetupContext['emit'], prep?: (b: Record<string, unknown>) => void) {
  return defineComponent({
    props: PC.props,
    emits: ['abrir', 'rechazar'],
    __scopeId: PC.__scopeId,
    setup(props: { pedido: PedidoPestana; busy?: boolean }) {
      provide(ssrContextKey, { modules: new Set<string>() })
      const bindings = PC.setup(props as Parameters<Card['setup']>[0], {
        emit,
        attrs: {},
        slots: {},
        expose: () => {},
      }) as Record<string, unknown>
      prep?.(bindings)
      return bindings
    },
    ssrRender: PC.ssrRender,
  } as Parameters<typeof defineComponent>[0])
}

async function renderCard(pedido: PedidoPestana, emit: SetupContext['emit'] = () => {}) {
  const Host = host(pedido, emit)
  return renderToString(createSSRApp({ render: () => h(Host, { pedido }) }))
}

async function renderCardProps(
  pedido: PedidoPestana,
  extra: { compact?: boolean; notch?: boolean } = {},
) {
  const Host = defineComponent({
    props: { ...(PC.props as object), compact: { type: Boolean }, notch: { type: Boolean } },
    emits: ['abrir', 'rechazar'],
    __scopeId: PC.__scopeId,
    setup(props: { pedido: PedidoPestana; compact?: boolean; notch?: boolean }) {
      provide(ssrContextKey, { modules: new Set<string>() })
      return PC.setup(props as Parameters<Card['setup']>[0], {
        emit: () => {},
        attrs: {},
        slots: {},
        expose: () => {},
      }) as Record<string, unknown>
    },
    ssrRender: PC.ssrRender,
  } as Parameters<typeof defineComponent>[0])
  return renderToString(createSSRApp({ render: () => h(Host, { pedido, ...extra }) }))
}

describe('PedidoPestanaCard', () => {
  it('muestra sesión, carpeta, mensaje y botones', async () => {
    const html = await renderCard(base)
    expect(html).toContain('Tienda plugins')
    expect(html).toContain('/home/usuario/proyecto')
    expect(html).toContain('Arrancá con este contexto')
    expect(html).toContain('Abrir')
    expect(html).toContain('No')
  })

  it('modo notch: sin título propio de pedido y clase notch', async () => {
    const html = await renderCardProps(base, { notch: true, compact: true })
    expect(html).toMatch(/\bnotch\b/)
    expect(html).not.toMatch(/Pedido de pestaña/i)
    expect(html).toContain('Tienda plugins')
    expect(html).toContain('Abrir')
    expect(html).toContain('No')
  })

  it('modo campana: conserva el encabezado de pedido', async () => {
    const html = await renderCard(base)
    expect(html).toContain('Pedido de pestaña')
  })

  it('lista pestañas y nombre de tarjeta', async () => {
    const pedido = {
      ...base,
      mensaje: '',
      tarjeta: 'Workspace',
      pestanas: [
        { nombre: 'API', tipo: 'claude' as const, carpeta: '/home/usuario/proyecto', mensaje: 'Hola' },
        { nombre: 'Logs', tipo: 'terminal' as const, carpeta: '/var/log', comando: 'tail -f x' },
      ],
    }
    const html = await renderCard(pedido)
    expect(html).toContain('Workspace')
    expect(html).toContain('API')
    expect(html).toContain('Logs')
    expect(html).toContain('tail -f x')
    expect(html).toContain('2 pestañas')
  })
})

describe('PedidoPestanaCard: mensajes de cada pestaña (A1)', () => {
  const largo = 'Línea uno\nLínea dos\nLínea tres\nLínea cuatro\nLínea cinco que no se ve recortada'
  const multi: PedidoPestana = {
    ...base,
    mensaje: '',
    tarjeta: 'Workspace',
    pestanas: [
      { nombre: 'API', tipo: 'claude', carpeta: '/home/usuario/proyecto', mensaje: 'Revisá el endpoint de pagos' },
      { nombre: 'Front', tipo: 'claude', carpeta: '/home/usuario/proyecto', mensaje: largo },
      { nombre: 'Logs', tipo: 'terminal', carpeta: '/var/log', comando: 'tail -f x' },
    ],
  }

  it('muestra el mensaje de cada pestaña claude con la etiqueta de origen', async () => {
    const html = await renderCard(multi)
    expect(html).toContain('Revisá el endpoint de pagos')
    expect(html).toContain('Línea uno')
    expect(html.split('Mensaje para Claude (lo escribió otra sesión)').length - 1).toBe(2)
  })

  it('"Ver todo" por pestaña solo en mensajes largos y expande', async () => {
    const cerrado = await renderCard(multi)
    expect(cerrado.split('Ver todo').length - 1).toBe(1)
    expect(cerrado).toContain('recortado tab-msg')
    const Host = host(multi, () => {}, (b) => {
      ;(b.abiertos as { value: number[] }).value = [1]
    })
    const abierto = await renderToString(createSSRApp({ render: () => h(Host, { pedido: multi }) }))
    expect(abierto).toContain('Ver menos')
    expect(abierto).not.toContain('recortado tab-msg')
  })

  it('suma la línea de modo seguro si alguna pestaña lleva mensaje', async () => {
    const html = await renderCard(multi)
    expect(html).toContain('Las sesiones nuevas van a arrancar preguntando antes de cada herramienta.')
    const sin = await renderCard({
      ...multi,
      pestanas: [{ nombre: 'Logs', tipo: 'terminal', carpeta: '/var/log', comando: 'tail -f x' }],
    })
    expect(sin).not.toContain('preguntando antes de cada herramienta')
  })

  it('el pedido de una pestaña con mensaje también avisa el modo seguro', async () => {
    const html = await renderCard(base)
    expect(html).toContain('Las sesiones nuevas van a arrancar preguntando antes de cada herramienta.')
  })
})

describe('PedidoPestanaCard: pedido para cerrar una terminal', () => {
  const cerrar: PedidoPestana = {
    ...base,
    carpeta: '',
    mensaje: '',
    accion: 'cerrar',
    terminal: { pane_id: 'w2:p1', titulo: 'npm run dev', cwd: '~/Proyectos/front', proceso: 'node', estado: 'corriendo', donde: 'Front / Dev' },
  }

  it('dice qué terminal se cierra, dónde y qué corre, con botones Cerrar y No', async () => {
    const html = await renderCard(cerrar)
    expect(html).toContain('Cerrar terminal')
    expect(html).toContain('npm run dev')
    expect(html).toContain('~/Proyectos/front')
    expect(html).toContain('node')
    expect(html).toContain('pide cerrar una terminal')
    expect(html).toContain('aria-label="Cerrar la terminal"')
    expect(html).toContain('aria-label="No cerrar"')
    expect(html).not.toContain('Pedido de pestaña')
    expect(html).not.toContain('>Abrir<')
  })
})

describe('PedidoPestanaCard: pedido de trabajador Cursor', () => {
  const cursor: PedidoPestana = {
    ...base,
    carpeta: '/home/usuario/repo',
    nombre: 'Renombrar helpers',
    mensaje: 'Renombrá foo a bar en a.py y b.py; no toques tests',
    accion: 'cursor',
    cursor: { modelo: 'composer-2.5-fast' },
  }

  it('dice que pide un trabajador Cursor, con carpeta, pedido, aviso y botones Lanzar y No', async () => {
    const html = await renderCard(cursor)
    expect(html).toContain('Trabajador Cursor')
    expect(html).toContain('pide un trabajador Cursor')
    expect(html).toContain('/home/usuario/repo')
    expect(html).toContain('Renombrá foo a bar en a.py y b.py; no toques tests')
    expect(html).toContain('composer-2.5-fast')
    expect(html).toContain('Cursor va a editar archivos en una copia aparte; solo corre los comandos que tu configuración de Cursor permite.')
    expect(html).not.toContain('sin poder correr comandos')
    expect(html).toContain('aria-label="Lanzar el trabajador Cursor"')
    expect(html).toContain('aria-label="No lanzar"')
    expect(html).toContain('>Lanzar<')
    expect(html).not.toContain('Pedido de pestaña')
    expect(html).not.toContain('preguntando antes de cada herramienta')
  })

  it('el pedido largo se recorta a 6 líneas con Ver todo', async () => {
    const largo = { ...cursor, mensaje: 'x'.repeat(500) }
    const html = await renderCard(largo)
    expect(html).toContain('recortado cursor-msg')
    expect(html).toContain('Ver todo')
    const corto = await renderCard(cursor)
    expect(corto).not.toContain('Ver todo')
    const Host = host(largo, () => {}, (b) => {
      ;(b.cursorAbierto as { value: boolean }).value = true
    })
    const abierto = await renderToString(createSSRApp({ render: () => h(Host, { pedido: largo }) }))
    expect(abierto).toContain('Ver menos')
    expect(abierto).not.toContain('recortado cursor-msg')
  })

  it('sin modelo no muestra la línea del modelo', async () => {
    const html = await renderCard({ ...cursor, cursor: {} })
    expect(html).not.toContain('Modelo')
  })
})

describe('PedidoPestanaCard: cierre de sesión, pestaña o tarjeta', () => {
  const cierre = (objetivo: 'sesion' | 'pestana' | 'tarjeta'): PedidoPestana => ({
    ...base,
    accion: 'cerrar',
    cierre: {
      objetivo,
      tipo: objetivo === 'tarjeta' ? 'workspace' : 'tab',
      target_id: 'w1:t1',
      label: 'Pestaña API',
      workspace_label: 'Tienda demo',
      carpeta: '/home/usuario/proyecto',
      sesiones: 1,
      terminales: 2,
    },
  })
  const trab = { trabajando: true, estados: ['working'], huella: 'h' }

  async function conVista(pedido: PedidoPestana, vista?: typeof trab, emit: (...a: unknown[]) => void = () => {}) {
    const Host = defineComponent({
      props: { ...(PC.props as object), vista: { type: Object } },
      emits: ['abrir', 'rechazar'],
      __scopeId: PC.__scopeId,
      setup(props: { pedido: PedidoPestana }) {
        provide(ssrContextKey, { modules: new Set<string>() })
        return PC.setup(props as Parameters<Card['setup']>[0], {
          emit,
          attrs: {},
          slots: {},
          expose: () => {},
        } as unknown as SetupContext) as Record<string, unknown>
      },
      ssrRender: PC.ssrRender,
    } as Parameters<typeof defineComponent>[0])
    return { html: await renderToString(createSSRApp({ render: () => h(Host, { pedido, vista }) })), Host }
  }

  it('muestra qué se cierra y Cerrar', async () => {
    const { html } = await conVista(cierre('pestana'))
    expect(html).toContain('Cerrar pestaña')
    expect(html).toContain('pide cerrar una pestaña')
    expect(html).toContain('Pestaña API')
    expect(html).toContain('Tienda demo')
    expect(html).toContain('/home/usuario/proyecto')
    expect(html).toContain('1 sesión de Claude · 2 terminales')
    expect(html).toContain('Antes de cerrar, se le pide a cada sesión de Claude que guarde lo que tenía.')
    expect(html).toMatch(/>\s*Cerrar\s*</)
    expect(html).not.toContain('Cerrar igual')
    expect(html).toContain('aria-label="Cerrar la pestaña"')
    // La región viva queda montada (vacía) para que el aviso de "trabajando" se anuncie al aparecer.
    expect(html).toMatch(/role="status"[^>]*>\s*(<!--[^>]*-->\s*)*<\/div>/)
  })

  it('muestra el espacio y el id del objetivo, no solo el título', async () => {
    const { html } = await conVista(cierre('pestana'))
    expect(html).toContain('Tienda demo · w1:t1')
    const sinEspacio: PedidoPestana = { ...cierre('sesion'), cierre: { ...cierre('sesion').cierre!, workspace_label: '' } }
    const h2 = (await conVista(sinEspacio)).html
    expect(h2).toMatch(/class="term-donde mono"[^>]*>w1:t1<\/p>/)
  })

  it('con la vista trabajando muestra el aviso y Cerrar igual', async () => {
    const { html } = await conVista(cierre('pestana'), trab)
    expect(html).toContain('role="status"')
    expect(html).toContain('Está trabajando')
    expect(html).toContain('Si cerrás igual, no se le pide que guarde.')
    expect(html).toMatch(/>\s*Cerrar igual\s*</)
    expect(html).toContain('aria-label="Cerrar la pestaña igual"')
    expect(html).not.toContain('Antes de cerrar, se le pide')
  })

  it('el botón principal emite abrir con el id', async () => {
    const emit = vi.fn()
    const pedido = cierre('sesion')
    const Host = host(pedido, emit as unknown as SetupContext['emit'], (b) => (b.onAbrir as () => void)())
    await renderToString(createSSRApp({ render: () => h(Host, { pedido }) }))
    expect(emit).toHaveBeenCalledWith('abrir', base.id)
  })

  it('una sesión no muestra conteo ni lo dice de la tarjeta', async () => {
    const { html } = await conVista(cierre('sesion'))
    expect(html).toContain('pide cerrar una sesión')
    expect(html).not.toContain('sesión de Claude ·')
    const t = (await conVista(cierre('tarjeta'))).html
    expect(t).toContain('pide cerrar una tarjeta')
    expect(t).toContain('1 sesión de Claude · 2 terminales')
  })
})
