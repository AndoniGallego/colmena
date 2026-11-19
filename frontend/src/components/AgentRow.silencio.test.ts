// @vitest-environment jsdom
import { h, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Agent } from '../api/types'

const { silenciadasGuardado, silencioError, silenciarSesion } = await vi.hoisted(async () => {
  const { ref: r } = await import('vue')
  return {
    silenciadasGuardado: r<string[]>([]),
    silencioError: r<{ sid: string; texto: string } | null>(null),
    silenciarSesion: (await import('vitest')).vi.fn(),
  }
})

vi.mock('../motion', () => ({
  gsap: {}, isSoft: () => true, useGsap: () => ({ run: (fn: () => void) => fn() }), haptic: () => {}, burst: () => {}, ring: () => {},
}))
vi.mock('../state/app', () => ({
  highlight: { value: null }, loadDigest: vi.fn(), orderFromSession: vi.fn(), viewRequest: { value: null },
}))
vi.mock('../state/ordenTablero', () => ({
  silenciadasGuardado,
  silencioError,
  silenciarSesion: (...a: unknown[]) => silenciarSesion(...a),
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
vi.mock('./Icon.vue', () => ({ default: { props: ['name'], render() { return h('i', { class: 'icon', 'data-name': (this as any).name }) } } }))
vi.mock('./StatusPill.vue', () => ({ default: { render: () => null } }))
vi.mock('./MrPipe.vue', () => ({ default: { render: () => null } }))
vi.mock('./CtxRing.vue', () => ({ default: { render: () => null } }))

import AgentRow from './AgentRow.vue'

const agente: Agent = {
  pane_id: 'w1:p1', kind: 'claude', status: 'idle', session_id: 's1', title: 'Sesión', doing: '', pending: '',
  asks_user: false, last_activity: null,
}

const montar = () => mount(AgentRow, { props: { agent: agente, wsLabel: 'W', now: Date.now() } })

describe('AgentRow silencio', () => {
  beforeEach(() => {
    silenciarSesion.mockReset()
    silenciadasGuardado.value = []
    silencioError.value = null
  })

  it('el botón silencia con el sid y on=true', async () => {
    const w = montar()
    const b = w.get('button[aria-label="Silenciar avisos"]')
    await b.trigger('click')
    expect(silenciarSesion).toHaveBeenCalledWith('s1', true)
  })

  it('si ya está silenciada el botón quita el silencio y se ve el indicador', async () => {
    silenciadasGuardado.value = ['s1']
    const w = montar()
    expect(w.find('.silencio-ind').exists()).toBe(true)
    expect(w.find('button[aria-label="Silenciar avisos"]').exists()).toBe(false)
    await w.get('button[aria-label="Volver a avisar"]').trigger('click')
    expect(silenciarSesion).toHaveBeenCalledWith('s1', false)
  })

  it('sin silencio no hay indicador', () => {
    expect(montar().find('.silencio-ind').exists()).toBe(false)
  })

  it('muestra el error del silencio solo en la fila de esa sesión', () => {
    silencioError.value = { sid: 'otra', texto: 'No pude cambiar el silencio' }
    expect(montar().find('[role="alert"]').exists()).toBe(false)
    silencioError.value = { sid: 's1', texto: 'No pude cambiar el silencio' }
    expect(montar().get('[role="alert"]').text()).toBe('No pude cambiar el silencio')
  })
})
