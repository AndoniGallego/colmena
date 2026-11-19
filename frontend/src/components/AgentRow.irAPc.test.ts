// @vitest-environment jsdom
import { h, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Agent } from '../api/types'

const { irAPcEnviando, irAPcAviso, irAPcSesion } = await vi.hoisted(async () => {
  const { ref: r } = await import('vue')
  return {
    irAPcEnviando: r<Record<string, boolean>>({}),
    irAPcAviso: r<{ sid: string; texto: string; ok: boolean } | null>(null),
    irAPcSesion: (await import('vitest')).vi.fn(),
  }
})

vi.mock('../motion', () => ({
  gsap: {}, isSoft: () => true, useGsap: () => ({ run: (fn: () => void) => fn() }), haptic: () => {}, burst: () => {}, ring: () => {},
}))
vi.mock('../state/app', () => ({
  highlight: { value: null }, loadDigest: vi.fn(), orderFromSession: vi.fn(), viewRequest: { value: null },
}))
vi.mock('../state/ordenTablero', () => ({
  silenciadasGuardado: ref<string[]>([]), silencioError: ref(null), silenciarSesion: vi.fn(),
}))
vi.mock('../state/irAPc', () => ({ irAPcEnviando, irAPcAviso, irAPcSesion: (...a: unknown[]) => irAPcSesion(...a) }))
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

const agente = (pane_id: string): Agent => ({
  pane_id, kind: 'claude', status: 'idle', session_id: 's1', title: 'Sesión', doing: '', pending: '',
  asks_user: false, last_activity: null,
})
const montar = (pane = 'g1:p1') => mount(AgentRow, { props: { agent: agente(pane), wsLabel: 'W', now: Date.now() } })

describe('AgentRow Ir a PC', () => {
  beforeEach(() => {
    irAPcSesion.mockReset()
    irAPcEnviando.value = {}
    irAPcAviso.value = null
  })

  it('el botón llama con el sid', async () => {
    await montar().get('button[aria-label="Ir a PC"]').trigger('click')
    expect(irAPcSesion).toHaveBeenCalledWith('s1')
  })

  it('usa el ícono de monitor', () => {
    expect(montar().get('button[aria-label="Ir a PC"] .icon').attributes('data-name')).toBe('monitor')
  })

  it('solo aparece en sesiones de una terminal de Colmena', () => {
    expect(montar('w1:p1').find('button[aria-label="Ir a PC"]').exists()).toBe(false)
  })

  it('queda deshabilitado mientras envía', () => {
    irAPcEnviando.value = { s1: true }
    expect(montar().get('button[aria-label="Ir a PC"]').attributes('disabled')).toBeDefined()
  })

  it('muestra el aviso de éxito y el de error de esa sesión', async () => {
    irAPcAviso.value = { sid: 's1', texto: 'Abierta en la notebook', ok: true }
    const w = montar()
    expect(w.get('.ir-pc-aviso').text()).toBe('Abierta en la notebook')
    irAPcAviso.value = { sid: 's1', texto: 'La notebook no tiene la pantalla activa', ok: false }
    await w.vm.$nextTick()
    expect(w.get('.ir-pc-aviso').text()).toBe('La notebook no tiene la pantalla activa')
  })

  it('no se deshabilita si envía otra sesión', () => {
    irAPcEnviando.value = { otra: true }
    expect(montar().get('button[aria-label="Ir a PC"]').attributes('disabled')).toBeUndefined()
  })

  it('tiene el title que explica que abre la notebook', () => {
    expect(montar().get('button[aria-label="Ir a PC"]').attributes('title')).toBe('Abre una terminal en la notebook')
  })

  it('no aparece en una terminal que no es una sesión (g1:t3)', () => {
    expect(montar('g1:t3').find('button[aria-label="Ir a PC"]').exists()).toBe(false)
  })

  it('no muestra el aviso de otra sesión', () => {
    irAPcAviso.value = { sid: 'otra', texto: 'x', ok: true }
    expect(montar().find('.ir-pc-aviso').exists()).toBe(false)
  })
})
