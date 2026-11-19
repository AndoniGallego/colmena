import { createSSRApp, h, ref } from 'vue'
import { renderToString } from 'vue/server-renderer'
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

const agente = (extra: Partial<Agent> = {}): Agent => ({
  pane_id: 'w1:p1', kind: 'claude', status: 'idle', session_id: 's1', title: 'Sesión', doing: '', pending: 'Texto pendiente suelto.',
  asks_user: false, last_activity: null, ...extra,
})

// Contraída y con session_id el resumen no se renderiza (ver AgentRow.contraida.test.ts):
// acá se ejercita el render del resumen en la cabecera, que es donde queda sin session_id.
const render = (a: Agent) => renderToString(createSSRApp({ render: () => h(AgentRow, { agent: { ...a, session_id: null }, wsLabel: 'W', now: Date.now() }) }))

describe('AgentRow con estado', () => {
  it('muestra hizo, falta y pide en lugar del pending', async () => {
    const html = await render(agente({ estado: { hizo: 'Saqué el mapa', falta: 'Elegir el diseño', pide: '¿Cuál preferís?' }, asks_user: true }))
    expect(html).not.toContain('Texto pendiente suelto.')
    expect(html).toContain('Saqué el mapa')
    expect(html).toContain('Falta: Elegir el diseño')
    expect(html).toContain('¿Cuál preferís?')
    expect(html).toContain('class="estado-linea estado-hizo"')
    expect(html).toMatch(/estado-linea estado-pide/)
  })

  it('muestra solo las líneas que hay', async () => {
    const html = await render(agente({ estado: { falta: 'Probarlo' } }))
    expect(html).toContain('Falta: Probarlo')
    expect(html).not.toContain('estado-hizo')
    expect(html).not.toContain('estado-pide')
  })

  it('sin estado muestra el pending como siempre', async () => {
    const html = await render(agente({ estado: null }))
    expect(html).toContain('Texto pendiente suelto.')
    expect(html).toContain('class="pending')
    expect(html).not.toContain('estado-linea')
  })
})
