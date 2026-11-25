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

const base: Agent = { pane_id: 'w1:p1', kind: 'claude', status: 'idle', session_id: 's1', title: 'Sesión', doing: '', pending: 'Listo.', asks_user: false, last_activity: null }
const montar = (a: Agent) => mount(AgentRow, { props: { agent: a, wsLabel: 'W', now: Date.now() } })

describe('AgentRow: tokens y dólares de hoy', () => {
  it('la línea vive en el cajón, no en la cabecera contraída', async () => {
    const w = montar({ ...base, uso: { total: 312_000, usd: 4.1 } })
    expect(w.find('.head').text()).not.toContain('tok')
    await w.find('.head').trigger('click')
    const linea = w.find('.drawer .uso-line')
    expect(linea.text()).toContain('312 k tok')
    expect(linea.text()).toContain('4,10')
    expect(linea.text()).toContain('hoy')
  })

  it('sin precio muestra el guion y sin uso no muestra la línea', async () => {
    const sinPrecio = montar({ ...base, uso: { total: 5_000, usd: null } })
    await sinPrecio.find('.head').trigger('click')
    expect(sinPrecio.find('.uso-line').text()).toContain('≈ — hoy')
    expect(montar(base).find('.uso-line').exists()).toBe(false)
    expect(montar({ ...base, uso: { total: 0, usd: 0 } }).find('.uso-line').exists()).toBe(false)
  })
})
