// @vitest-environment jsdom
import { h, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import type { Agent } from '../api/types'

vi.mock('../motion', () => ({
  gsap: {}, isSoft: () => true, useGsap: () => ({ run: (fn: () => void) => fn() }), haptic: () => {}, burst: () => {}, ring: () => {},
}))
vi.mock('../state/app', () => ({
  highlight: { value: null }, loadDigest: vi.fn(), orderFromSession: vi.fn(), viewRequest: { value: null },
}))
vi.mock('../state/cerrar', () => ({ openClose: vi.fn() }))
vi.mock('../state/session', () => ({ openSessionChat: vi.fn(), openSessionId: { value: null } }))
vi.mock('../lib/viewport', () => ({ desktop: { value: true } }))
vi.mock('../lib/time', () => ({ ago: () => 'hace 1 min', useNow: () => ref(Date.now()) }))
vi.mock('../state/mrs', () => ({ irAMr: vi.fn(), mrDeSesion: () => null }))
vi.mock('../state/mudanza', () => ({ abrirMudanza: vi.fn(), puedeMudar: () => false }))
vi.mock('../state/terminalVivo', () => ({ abrirVivo: vi.fn(), loadTerminalConfig: vi.fn(), vivoHabilitado: { value: false } }))
vi.mock('../state/terminalActions', () => ({ tconfig: { value: null } }))
vi.mock('./SessionPreview.vue', () => ({ default: { render: () => null } }))
vi.mock('./Icon.vue', () => ({ default: { props: ['name'], render() { return h('i', { class: 'icon' }) } } }))
vi.mock('./StatusPill.vue', () => ({ default: { render: () => null } }))
vi.mock('./MrPipe.vue', () => ({ default: { render: () => null } }))
vi.mock('./CtxRing.vue', () => ({ default: { render: () => null } }))

import AgentRow from './AgentRow.vue'

const base: Agent = {
  pane_id: 'w1:p1', kind: 'claude', status: 'idle', session_id: 's1', title: 'Sesión', doing: 'Armando el mapa', pending: 'Texto pendiente suelto.',
  asks_user: false, last_activity: null, fondo: [{ id: 't1', tipo: 'comando', texto: 'corriendo tests', desde: 0 }],
}
const conEstado: Agent = { ...base, estado: { hizo: 'Saqué el mapa', falta: 'Elegir el diseño', pide: '¿Cuál preferís?' }, asks_user: true, unread: true }

const montar = (a: Agent) => mount(AgentRow, { props: { agent: a, wsLabel: 'W', now: Date.now() } })
const RESUMENES = ['Saqué el mapa', 'Elegir el diseño', '¿Cuál preferís?', 'Armando el mapa', 'corriendo tests']

describe('AgentRow contraída: solo título, píldoras, tiempo y ctx', () => {
  it('no renderiza estado, pending, doing ni línea de fondo', () => {
    const w = montar(conEstado)
    for (const t of RESUMENES) expect(w.text()).not.toContain(t)
    expect(w.find('.estado').exists()).toBe(false)
    expect(w.find('.doing').exists()).toBe(false)
    expect(w.find('.fondo').exists()).toBe(false)
    expect(montar(base).find('.pending').exists()).toBe(false)
    expect(montar(base).text()).not.toContain('Texto pendiente suelto.')
  })

  it('mantiene título, tiempo y las píldoras (Nueva respuesta, Te pregunta)', () => {
    const w = montar(conEstado)
    expect(w.find('.title').text()).toBe('Sesión')
    expect(w.find('.when').text()).toBe('hace 1 min')
    expect(w.find('.new-chip').exists()).toBe(true)
    expect(w.find('.pide').text()).toContain('Te pregunta')
  })

  it('no dibuja la fila de píldoras si no hay ninguna', () => {
    expect(montar({ ...base, fondo: [] }).find('.meta').exists()).toBe(false)
  })
})

describe('AgentRow expandida: los resúmenes aparecen dentro del cajón', () => {
  it('estado, doing y fondo viven en el cajón tras abrir', async () => {
    const w = montar(conEstado)
    await w.find('.head').trigger('click')
    const cajon = w.find('.drawer')
    for (const t of RESUMENES) expect(cajon.text()).toContain(t)
    expect(cajon.find('.fondo').exists()).toBe(true)
    expect(w.find('.head .estado').exists()).toBe(false)
  })

  it('el pending aparece en el cajón al abrir', async () => {
    const w = montar(base)
    await w.find('.head').trigger('click')
    expect(w.find('.drawer .pending').text()).toContain('Texto pendiente suelto.')
  })

  it('al cerrar el contenido queda montado para que el pliegue anime sin saltos', async () => {
    const w = montar(conEstado)
    await w.find('.head').trigger('click')
    await w.find('.head').trigger('click')
    expect(w.find('.drawer .estado').exists()).toBe(true)
    expect(w.find('.drawer').attributes('aria-hidden')).toBe('true')
  })
})

describe('AgentRow sin session_id (no se puede expandir)', () => {
  it('sigue mostrando el resumen en la cabecera, como antes', () => {
    const w = montar({ ...conEstado, session_id: null })
    expect(w.find('.head .estado').exists()).toBe(true)
    expect(w.find('.head .doing').exists()).toBe(true)
    expect(w.find('.head .fondo').exists()).toBe(true)
  })
})
