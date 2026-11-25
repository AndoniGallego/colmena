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
vi.mock('../lib/time', () => ({ ago: () => 'hace 4 min', useNow: () => ref(Date.now()) }))
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
  pane_id: 'w1:p1', kind: 'claude', status: 'working', session_id: 's1', title: 'Sesión', doing: 'Armando el mapa', pending: '',
  asks_user: false, last_activity: null,
}
const montar = (a: Agent) => mount(AgentRow, { props: { agent: a, wsLabel: 'W', now: Date.now() } })

describe('AgentRow: chip de sesión trabada', () => {
  it('muestra el tipo y desde cuándo, con el detalle como ayuda', () => {
    const w = montar({ ...base, traba: { tipo: 'repetida', desde: 1, detalle: 'Grep repetido 4 veces con lo mismo' } })
    const chip = w.find('.traba-chip')
    expect(chip.exists()).toBe(true)
    expect(chip.text()).toBe('Repite lo mismo · hace 4 min')
    expect(chip.attributes('title')).toBe('Grep repetido 4 veces con lo mismo')
    expect(chip.attributes('role')).toBe('status')
  })

  it('desaparece cuando el servidor deja de mandar la traba', async () => {
    const w = montar({ ...base, traba: { tipo: 'quieta', desde: 1, detalle: 'x' } })
    expect(w.find('.traba-chip').exists()).toBe(true)
    await w.setProps({ agent: { ...base } })
    expect(w.find('.traba-chip').exists()).toBe(false)
  })

  it('sin traba no hay chip', () => {
    expect(montar(base).find('.traba-chip').exists()).toBe(false)
  })
})
