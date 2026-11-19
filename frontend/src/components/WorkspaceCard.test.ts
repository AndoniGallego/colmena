// @vitest-environment jsdom
import { readFileSync } from 'node:fs'
import { mount } from '@vue/test-utils'
import { createSSRApp, h, ref } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it, vi } from 'vitest'
import type { Agent, Workspace } from '../api/types'

vi.mock('../motion', () => ({ gsap: {}, isSoft: () => true, useGsap: () => ({ run: (fn: () => void) => fn() }), haptic: () => {} }))
const renombrarTerminal = vi.hoisted(() => vi.fn(async () => {}))
vi.mock('../state/app', () => ({ boardState: { value: { transitions: {} } }, renombrarTerminal }))
vi.mock('../state/cerrar', () => ({ openClose: vi.fn() }))
vi.mock('../state/session', () => ({ openSessionId: { value: null } }))
vi.mock('../state/ordenTablero', () => ({
  ordenPestanasGuardado: ref({ 'w1:w1:t1': ['p2', 'p1'] }),
  guardarOrdenPestanas: vi.fn(),
}))
vi.mock('../lib/viewport', () => ({ desktop: { value: true } }))
vi.mock('./Icon.vue', () => ({ default: { render: () => null } }))
vi.mock('./AgentRow.vue', () => ({
  default: {
    props: ['agent'],
    render(this: { agent: Agent }) {
      return h('div', { 'data-pane': this.agent.pane_id })
    },
  },
}))
vi.mock('./TabLine.vue', () => ({ default: { render: () => null } }))
vi.mock('./TerminalGroup.vue', () => ({ default: { render: () => null } }))
vi.mock('./StatusPill.vue', () => ({ default: { render: () => null } }))

const {
  default: WorkspaceCard,
  superaUmbral,
  debeCancelarGripHoldPorMovimiento,
  debeCancelarPestHoldPorMovimiento,
} = await import('./WorkspaceCard.vue')

const ws: Workspace = {
  id: 'w1',
  number: 1,
  label: 'Uno',
  pinned: false,
  status: 'idle',
  tabs: [{ id: 'w1:t1', label: '1', agents: [] }],
}

const ag = (pane: string): Agent => ({
  pane_id: pane,
  kind: 'claude',
  status: 'idle',
  session_id: pane,
  title: pane,
  doing: '',
  pending: '',
  asks_user: false,
  last_activity: null,
})

const wsDosPest: Workspace = {
  ...ws,
  tabs: [{ id: 'w1:t1', label: '1', agents: [ag('p1'), ag('p2')] }],
}

describe('debeCancelarGripHoldPorMovimiento', () => {
  it('no cancela si el arrastre ya está armado', () => {
    expect(debeCancelarGripHoldPorMovimiento(0, 0, 30, 0, true)).toBe(false)
  })
  it('cancela movimiento antes de armar', () => {
    expect(debeCancelarGripHoldPorMovimiento(0, 0, 9, 0, false)).toBe(true)
  })
})

describe('debeCancelarPestHoldPorMovimiento', () => {
  it('cancela el long-press si el dedo se mueve más de 8 px antes de armar', () => {
    expect(debeCancelarPestHoldPorMovimiento(0, 0, 9, 0, false)).toBe(true)
    expect(debeCancelarPestHoldPorMovimiento(10, 10, 10, 19, false)).toBe(true)
  })
  it('no cancela con jitter menor a 8 px', () => {
    expect(debeCancelarPestHoldPorMovimiento(0, 0, 5, 5, false)).toBe(false)
  })
  it('no cancela si el arrastre ya está armado', () => {
    expect(debeCancelarPestHoldPorMovimiento(0, 0, 20, 0, true)).toBe(false)
  })
})

describe('superaUmbral', () => {
  it('no cancela con jitter menor a 8 px', () => {
    expect(superaUmbral(0, 0, 5, 5)).toBe(false)
    expect(superaUmbral(10, 10, 17, 10)).toBe(false)
  })
  it('cancela al superar 8 px', () => {
    expect(superaUmbral(0, 0, 9, 0)).toBe(true)
    expect(superaUmbral(0, 0, 6, 6)).toBe(true)
  })
})

describe('WorkspaceCard manija', () => {
  it('la manija tiene aria-label Mover tarjeta', async () => {
    const html = await renderToString(
      createSSRApp({
        render: () => h(WorkspaceCard, { ws, now: Date.now(), reorder: { index: 0, total: 2 } }),
      }),
    )
    expect(html).toContain('aria-label="Mover tarjeta"')
  })

  it('la manija de tarjeta no participa del layout flex (posición absoluta)', () => {
    const src = readFileSync('src/components/WorkspaceCard.vue', 'utf8')
    expect(src).toMatch(/\.ws-grip\s*\{[\s\S]*?position:\s*absolute/)
  })

  it('la manija evita gestos nativos táctiles', () => {
    const src = readFileSync('src/components/WorkspaceCard.vue', 'utf8')
    expect(src).toMatch(/touch-action:\s*none/)
    expect(src).toMatch(/-webkit-touch-callout:\s*none/)
    expect(src).toMatch(/@contextmenu\.prevent/)
  })

  it('en celu la manija de tarjeta y pestaña queda oculta', () => {
    const src = readFileSync('src/components/WorkspaceCard.vue', 'utf8')
    expect(src).toMatch(/@media \(pointer: coarse\)[\s\S]*\.ws-grip[\s\S]*display:\s*none/)
    expect(src).toMatch(/@media \(pointer: coarse\)[\s\S]*\.pest-grip[\s\S]*display:\s*none/)
  })

  it('.ws-fold:hover solo dentro de @media (hover: hover)', () => {
    const src = readFileSync('src/components/WorkspaceCard.vue', 'utf8')
    expect(src).toMatch(/@media \(hover: hover\)\s*\{[\s\S]*?\.ws-fold:hover/)
    expect(src).not.toMatch(/\.ws-fold:hover,\s*\n\.ws-fold:focus-visible/)
  })

  it('chevron desplegado apunta abajo y plegado a la derecha', () => {
    const src = readFileSync('src/components/WorkspaceCard.vue', 'utf8')
    expect(src).toMatch(/\.fold-ico\s*\{[\s\S]*?transform:\s*rotate\(90deg\)/)
    expect(src).toMatch(/\.ws-fold\.fold-ico-on \.fold-ico[\s\S]*?transform:\s*rotate\(0/)
  })

  it('plegada muestra aria-expanded y contador de pestañas', async () => {
    const html = await renderToString(
      createSSRApp({
        render: () => h(WorkspaceCard, { ws: wsDosPest, now: Date.now(), plegada: true }),
      }),
    )
    expect(html).toContain('aria-label="Desplegar tarjeta"')
    expect(html).toContain('1 pestaña')
    expect(html).toMatch(/aria-hidden="true"/)
  })

  it('doble toque rápido en plegar cancela tween en curso', () => {
    const src = readFileSync('src/components/WorkspaceCard.vue', 'utf8')
    expect(src).toMatch(/watch\([\s\S]*?props\.plegada[\s\S]*?cuerpoTween\?\.kill/)
  })

  it('plegar usa Transition y v-show en el cuerpo', () => {
    const src = readFileSync('src/components/WorkspaceCard.vue', 'utf8')
    expect(src).toMatch(/<Transition :css="false" @enter="onCuerpoEnter" @leave="onCuerpoLeave">/)
    expect(src).toMatch(/v-show="!plegada"[\s\S]*?class="ws-body"/)
    expect(src).not.toMatch(/ws-body[\s\S]*?:class="\{ hidden: plegada \}"/)
  })

  it('manija en tarjeta sin leer (reorder habilitado)', async () => {
    const wsUnread: Workspace = {
      ...ws,
      tabs: [
        {
          id: 'w1:t1',
          label: '1',
          agents: [{ ...ag('p1'), unread: true }],
        },
      ],
    }
    const html = await renderToString(
      createSSRApp({
        render: () => h(WorkspaceCard, { ws: wsUnread, now: Date.now(), reorder: { index: 0, total: 2 } }),
      }),
    )
    expect(html).toContain('aria-label="Mover tarjeta"')
  })

  it('desplegada tiene aria-expanded en el plegado', async () => {
    const html = await renderToString(createSSRApp({ render: () => h(WorkspaceCard, { ws, now: Date.now(), plegada: false }) }))
    expect(html).toContain('aria-label="Plegar tarjeta"')
    expect(html).toMatch(/aria-expanded="true"/)
  })

  it('la manija de pestaña usa onPestGripMove, no onGripMove de la tarjeta', () => {
    const src = readFileSync('src/components/WorkspaceCard.vue', 'utf8')
    expect(src).toMatch(/class="pest-grip hit"[\s\S]*?@pointermove\.stop="onPestGripMove"/)
    expect(src).not.toMatch(/class="pest-grip"[\s\S]*?@pointermove\.stop="onGripMove"/)
  })

  it('la manija de pestaña tiene aria-label Mover pestaña', async () => {
    const html = await renderToString(createSSRApp({ render: () => h(WorkspaceCard, { ws: wsDosPest, now: Date.now() }) }))
    expect(html).toContain('aria-label="Mover pestaña"')
  })

  it('menú quieto muestra Subir/Bajar y emite reorder-move', async () => {
    const w = mount(WorkspaceCard, {
      props: { ws, now: Date.now(), reorder: { index: 1, total: 3, canUp: true, canDown: true } },
      attachTo: document.body,
    })
    await w.find('.dots').trigger('click')
    const items = w.findAll('[role="menuitem"]')
    expect(items.map((n) => n.text())).toEqual(expect.arrayContaining(['Subir', 'Bajar', 'Cerrar workspace']))
    await items.find((n) => n.text().includes('Subir'))!.trigger('click')
    expect(w.emitted('reorder-move')?.[0]).toEqual([-1])
    await items.find((n) => n.text().includes('Bajar'))!.trigger('click')
    expect(w.emitted('reorder-move')?.[1]).toEqual([1])
    w.unmount()
  })

  it('Subir/Bajar deshabilitados en extremos del bloque quieto', async () => {
    const w = mount(WorkspaceCard, {
      props: { ws, now: Date.now(), reorder: { index: 0, total: 2, canUp: false, canDown: true } },
      attachTo: document.body,
    })
    await w.find('.dots').trigger('click')
    const subir = w.findAll('[role="menuitem"]').find((n) => n.text().includes('Subir'))!
    expect(subir.attributes('aria-disabled')).toBe('true')
    w.unmount()
  })

  it('tarjeta activa no muestra Subir/Bajar', async () => {
    const w = mount(WorkspaceCard, {
      props: { ws, now: Date.now(), reorder: null },
      attachTo: document.body,
    })
    await w.find('.dots').trigger('click')
    const txt = w.find('.pop').text()
    expect(txt).not.toMatch(/Subir/)
    expect(txt).not.toMatch(/Bajar/)
    w.unmount()
  })

  it('renderiza pestañas según orden manual', async () => {
    const html = await renderToString(createSSRApp({ render: () => h(WorkspaceCard, { ws: wsDosPest, now: Date.now() }) }))
    const p2 = html.indexOf('data-pane="p2"')
    const p1 = html.indexOf('data-pane="p1"')
    expect(p2).toBeGreaterThan(-1)
    expect(p1).toBeGreaterThan(p2)
  })

  describe('renombrar', () => {
    const wsG: Workspace = { ...ws, id: 'g1', label: 'Viejo', tabs: [{ id: 'g1:t1', label: 'Logs', agents: [] }] }
    const montar = (w: Workspace) => mount(WorkspaceCard, { props: { ws: w, now: Date.now() }, attachTo: document.body })

    it('menú: Renombrar grupo edita el título y Enter guarda', async () => {
      renombrarTerminal.mockClear()
      const w = montar(wsG)
      await w.find('.dots').trigger('click')
      await w.findAll('.pop .item').find((b) => /Renombrar grupo/.test(b.text()))!.trigger('click')
      const input = w.find('input.ws-rename')
      expect((input.element as HTMLInputElement).value).toBe('Viejo')
      await input.setValue('Nuevo')
      await input.trigger('keydown', { key: 'Enter' })
      expect(renombrarTerminal).toHaveBeenCalledWith({ tipo: 'grupo', id: 'g1', nombre: 'Nuevo' })
      expect(w.find('input.ws-rename').exists()).toBe(false)
      w.unmount()
    })

    it('Esc cancela y blur cancela sin llamar a la API', async () => {
      renombrarTerminal.mockClear()
      const w = montar(wsG)
      await w.find('.dots').trigger('click')
      await w.findAll('.pop .item').find((b) => /Renombrar grupo/.test(b.text()))!.trigger('click')
      await w.find('input.ws-rename').setValue('Otro')
      await w.find('input.ws-rename').trigger('keydown', { key: 'Escape' })
      expect(w.find('input.ws-rename').exists()).toBe(false)
      expect(renombrarTerminal).not.toHaveBeenCalled()
      w.unmount()
    })

    it('clic derecho sobre la pestaña abre la edición', async () => {
      renombrarTerminal.mockClear()
      const w = montar(wsG)
      await w.find('.tab-head').trigger('contextmenu')
      const input = w.find('input.tab-rename')
      expect((input.element as HTMLInputElement).value).toBe('Logs')
      await input.setValue('Build')
      await input.trigger('keydown', { key: 'Enter' })
      expect(renombrarTerminal).toHaveBeenCalledWith({ tipo: 'pestana', id: 'g1:t1', nombre: 'Build' })
      w.unmount()
    })

    it('menú: Renombrar pestaña edita la pestaña activa', async () => {
      renombrarTerminal.mockClear()
      const w2: Workspace = { ...wsG, tabs: [{ id: 'g1:t1', label: 'Logs', agents: [] }, { id: 'g1:t2', label: 'Api', agents: [] }] }
      const w = montar(w2)
      await w.find('.dots').trigger('click')
      await w.findAll('.pop .item').find((b) => /Renombrar pestaña/.test(b.text()))!.trigger('click')
      const input = w.find('input.tab-rename')
      expect((input.element as HTMLInputElement).value).toBe('Logs')
      await input.setValue('Build')
      await input.trigger('keydown', { key: 'Enter' })
      expect(renombrarTerminal).toHaveBeenCalledWith({ tipo: 'pestana', id: 'g1:t1', nombre: 'Build' })
      w.unmount()
    })

    it('grupos no del guardián no ofrecen renombrar', async () => {
      const w = montar(ws)
      await w.find('.dots').trigger('click')
      expect(w.find('.pop').text()).not.toMatch(/Renombrar/)
      await w.find('.tab-head').trigger('contextmenu')
      expect(w.find('input.tab-rename').exists()).toBe(false)
      w.unmount()
    })
  })

  describe('sumar pestaña', () => {
    const base: Workspace = { ...ws, id: 'g1', label: 'G', tabs: [{ id: 'g1:t1', label: 'a', agents: [] }] }
    const montar = (w: Workspace) => mount(WorkspaceCard, { props: { ws: w, now: Date.now() }, attachTo: document.body })

    const abrirMenu = async (w: ReturnType<typeof montar>) => {
      await w.find('button[aria-label^="Más acciones"]').trigger('click')
    }
    const item = (w: ReturnType<typeof montar>) => w.findAll('.pop .item').find((x) => /Sumar pestaña/.test(x.text()))

    it('ya no hay botón + suelto en la tarjeta', () => {
      const w = montar(base)
      expect(w.find('button[aria-label="Sumar pestaña"]').exists()).toBe(false)
      w.unmount()
    })

    it('el menú ⋯ trae Sumar pestaña y emite sumar-pestana', async () => {
      const w = montar(base)
      await abrirMenu(w)
      const b = item(w)
      expect(b).toBeTruthy()
      await b!.trigger('click')
      expect(w.emitted('sumar-pestana')).toHaveLength(1)
      expect(w.find('.pop').exists()).toBe(false)
      w.unmount()
    })

    it('no aparece en grupos que no son del guardián', async () => {
      const b = montar(ws)
      await abrirMenu(b)
      expect(item(b)).toBeFalsy()
      b.unmount()
    })
  })
})
