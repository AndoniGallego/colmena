import { createSSRApp, defineComponent, h, provide, ssrContextKey, type SetupContext } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { readFileSync } from 'node:fs'
import { describe, it, expect, vi } from 'vitest'
import type { PedidoPermiso } from '../api/types'

vi.mock('../motion', () => ({ gsap: {}, isSoft: () => true, useGsap: () => ({ run: (fn: () => void) => fn() }) }))
vi.mock('../state/app', () => ({}))
vi.mock('./Icon.vue', () => ({ default: { name: 'Icon', render: () => null } }))
const { default: PedidoCard } = await import('./PedidoCard.vue')

const base: PedidoPermiso = {
  id: 'p1',
  session_id: 's1',
  pane_id: 'w1:p1',
  herramienta: 'Bash',
  entrada: { command: 'touch foo' },
  estado: 'abierto',
  regla: { herramienta: 'Bash', contenido: 'touch:*', archivo: '/home/u/p/.claude/settings.local.json', huella: 'h' },
}

type PedidoCardCompiled = typeof PedidoCard & {
  setup: NonNullable<(typeof PedidoCard)['setup']>
  ssrRender: (...args: unknown[]) => void
  __scopeId?: string
  props: Record<string, unknown>
}

const PC = PedidoCard as PedidoCardCompiled

function host(
  pedido: PedidoPermiso,
  emit: SetupContext['emit'],
  prep?: (bindings: Record<string, unknown>) => void,
) {
  return defineComponent({
    props: PC.props,
    emits: ['permitir', 'rechazar', 'siempre'],
    __scopeId: PC.__scopeId,
    setup(props: { pedido: PedidoPermiso; busy?: boolean; done?: boolean }) {
      provide(ssrContextKey, { modules: new Set<string>() })
      const bindings = PC.setup(props as Parameters<PedidoCardCompiled['setup']>[0], {
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

async function renderPedido(
  pedido: PedidoPermiso,
  emit: SetupContext['emit'] = () => {},
  prep?: (bindings: Record<string, unknown>) => void,
) {
  const Host = host(pedido, emit, prep)
  return renderToString(createSSRApp({ render: () => h(Host, { pedido }) }))
}

async function withBindings(pedido: PedidoPermiso, emit: SetupContext['emit']) {
  let bindings!: Record<string, unknown>
  await renderPedido(pedido, emit, (b) => {
    bindings = b
  })
  return bindings
}

describe('PedidoCard', () => {
  it('abierto con regla muestra tres acciones', async () => {
    const html = await renderPedido(base, () => {})
    expect(html).toContain('Permitir')
    expect(html).toContain('Rechazar')
    expect(html).toContain('Permitir siempre')
  })
  it('sin regla no ofrece Permitir siempre', async () => {
    const html = await renderPedido({ ...base, regla: null }, () => {})
    expect(html).not.toContain('Permitir siempre')
  })
  it('Permitir siempre: primer toque no emite y despliega regla', async () => {
    const emitted: unknown[][] = []
    const emit: SetupContext['emit'] = (event, ...args) => {
      if (event === 'siempre') emitted.push(args)
    }
    const bindings = await withBindings(base, emit)
    ;(bindings.onSiempre as () => void)()
    expect(emitted).toHaveLength(0)
    const html = await renderPedido(base, () => {}, (b) => {
      ;(b.onSiempre as () => void)()
    })
    expect(html).toContain('touch:*')
    expect(html).toContain('/home/u/p/.claude/settings.local.json')
  })
  it('Permitir siempre: segundo toque emite siempre', async () => {
    const emitted: unknown[][] = []
    const emit: SetupContext['emit'] = (event, ...args) => {
      if (event === 'siempre') emitted.push(args)
    }
    const bindings = await withBindings(base, emit)
    ;(bindings.onSiempre as () => void)()
    ;(bindings.onSiempre as () => void)()
    expect(emitted).toEqual([['p1']])
  })
  it.each([
    ['terminal', 'Resuelto en la terminal'],
    ['vencido', 'Se contesta en el diálogo'],
    ['dialogo', 'Se contesta en el diálogo'],
    ['enviando', 'Mandando la respuesta…'],
    ['permitido', 'Permitido'],
    ['rechazado', 'Rechazado'],
    ['siempre', 'Permitido siempre'],
  ])('estado %s sin botones', async (estado, texto) => {
    const html = await renderPedido({ ...base, estado: estado as PedidoPermiso['estado'] }, () => {})
    expect(html).toContain(texto)
    expect(html).not.toContain('type="button"')
  })
  it('rechazar emite el motivo', async () => {
    const emitted: unknown[][] = []
    const emit: SetupContext['emit'] = (event, ...args) => {
      if (event === 'rechazar') emitted.push(args)
    }
    const bindings = await withBindings(base, emit)
    ;(bindings.motivo as { value: string }).value = 'usá otra cosa'
    ;(bindings.onRechazar as () => void)()
    expect(emitted[0]).toEqual(['p1', 'usá otra cosa'])
  })
  it('permitir emite permitir', async () => {
    const emitted: unknown[][] = []
    const emit: SetupContext['emit'] = (event, ...args) => {
      if (event === 'permitir') emitted.push(args)
    }
    const bindings = await withBindings(base, emit)
    ;(bindings.onPermitir as () => void)()
    expect(emitted[0]).toEqual(['p1'])
  })

  it('Write muestra content en el detalle', async () => {
    const html = await renderPedido(
      { ...base, herramienta: 'Write', entrada: { file_path: '/x.txt', content: 'contenido largo' } },
      () => {},
    )
    expect(html).toContain('/x.txt')
    expect(html).toContain('contenido largo')
  })

  it('ExitPlanMode muestra el plan', async () => {
    const plan = 'Plan línea 1\nPlan línea 2'
    const html = await renderPedido({ ...base, herramienta: 'ExitPlanMode', entrada: { plan } }, () => {})
    expect(html).toContain('Plan línea 1')
    expect(html).toContain('Plan línea 2')
  })

  it('no muestra textos de política ni zona gris aunque venga categoria', async () => {
    for (const categoria of ['gris', 'auto', 'usuario'] as const) {
      const html = await renderPedido(
        { ...base, categoria, regla_politica: 'r', motivo_politica: 'm' },
        () => {},
      )
      expect(html).not.toMatch(/Zona gris|política|Centinela|Habría aprobado|Por ahora todo te llega/i)
    }
  })

  it('no usa centinelaHabilitada ni textoCategoria', () => {
    expect(readFileSync(new URL('./PedidoCard.vue', import.meta.url).pathname, 'utf8')).not.toMatch(
      /centinelaHabilitada|textoCategoria/,
    )
  })

  it('categoria auto no emite permitir al montar', async () => {
    const emitted: unknown[][] = []
    const emit: SetupContext['emit'] = (event, ...args) => {
      if (event === 'permitir') emitted.push(args)
    }
    await renderPedido({ ...base, categoria: 'auto' }, emit)
    expect(emitted).toHaveLength(0)
    const html = await renderPedido({ ...base, categoria: 'auto' }, () => {})
    expect(html).toContain('Permitir')
    expect(html).toContain('Rechazar')
  })
})
