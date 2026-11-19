// @vitest-environment jsdom
import { h, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Agent } from '../api/types'

vi.mock('../motion', () => ({
  gsap: {}, isSoft: () => true, useGsap: () => ({ run: (fn: () => void) => fn() }), haptic: () => {}, burst: () => {}, ring: () => {},
}))
vi.mock('../state/app', () => ({
  highlight: { value: null }, loadDigest: vi.fn(), orderFromSession: vi.fn(), viewRequest: { value: null },
  marcarPreguntaVista: vi.fn(async () => {}),
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
import { openSessionChat } from '../state/session'
import { marcarPreguntaVista } from '../state/app'

const agente: Agent = {
  pane_id: 'w1:p1', kind: 'claude', status: 'idle', session_id: 's1', title: 'Sesión', doing: '', pending: '',
  asks_user: false, last_activity: null,
}
const montar = (extra: Partial<Agent> = {}) => mount(AgentRow, { props: { agent: { ...agente, ...extra }, wsLabel: 'W', now: Date.now() } })

describe('AgentRow: Te pregunta', () => {
  beforeEach(() => vi.mocked(openSessionChat).mockClear())

  it('tocar "Te pregunta" abre el chat de esa sesión', async () => {
    const w = montar({ session_id: 's9', asks_user: true })
    await w.get('[aria-label="Abrir el chat de la sesión"]').trigger('click')
    expect(openSessionChat).toHaveBeenCalledWith('s9')
  })

  it('no ofrece pedirle a Centinela', () => {
    expect(montar().html()).not.toMatch(/Centinela/)
  })
})

describe('AgentRow: Marcar leído y Pendiente', () => {
  beforeEach(() => vi.mocked(marcarPreguntaVista).mockClear())

  it('con pregunta ofrece "Marcar leído" y avisa al servidor', async () => {
    const w = montar({ session_id: 's9', asks_user: true })
    const b = w.get('button.marcar-leido')
    expect(b.text()).toMatch(/Marcar leído/)
    await b.trigger('click')
    expect(marcarPreguntaVista).toHaveBeenCalledWith('s9')
  })

  it('tocar "Marcar leído" no abre el chat', async () => {
    vi.mocked(openSessionChat).mockClear()
    const w = montar({ session_id: 's9', asks_user: true })
    await w.get('button.marcar-leido').trigger('click')
    expect(openSessionChat).not.toHaveBeenCalled()
  })

  it('pendiente muestra la píldora Pendiente y ya no "Te pregunta" ni el botón', () => {
    const w = montar({ session_id: 's9', asks_user: false, pendiente: true })
    expect(w.get('.pendiente-chip').text()).toMatch(/Pendiente/)
    expect(w.html()).not.toMatch(/Te pregunta/)
    expect(w.find('button.marcar-leido').exists()).toBe(false)
  })

  it('tocar Pendiente abre el chat para contestar', async () => {
    vi.mocked(openSessionChat).mockClear()
    const w = montar({ session_id: 's9', asks_user: false, pendiente: true })
    await w.get('.pendiente-chip').trigger('click')
    expect(openSessionChat).toHaveBeenCalledWith('s9')
  })

  it('sin pregunta ni pendiente no hay ninguna de las dos cosas', () => {
    const w = montar()
    expect(w.find('.pendiente-chip').exists()).toBe(false)
    expect(w.find('button.marcar-leido').exists()).toBe(false)
  })
})
