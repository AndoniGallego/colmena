// @vitest-environment jsdom
import { createApp, nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ClosePreview } from '../api/types'

vi.mock('../state/app', () => ({
  ALREADY_DONE: /ya (se )?(mand|ejecut|cerr)/i,
  boardState: { value: { board: null } },
  guardados: {},
  accionGuardado: vi.fn(),
  previewClose: vi.fn(),
  executeClose: vi.fn(),
  postBorrarCopia: vi.fn(async () => ({ ok: true })),
}))
vi.mock('../motion', () => ({ gsap: { fromTo: (_e: unknown, _a: unknown, v: { onComplete?: () => void }) => v.onComplete?.(), to: (_e: unknown, v: { onComplete?: () => void }) => v.onComplete?.(), set: () => {} }, haptic: vi.fn(), isSoft: () => true, useGsap: () => ({ run: (fn: () => void) => fn() }) }))
vi.mock('./Icon.vue', () => ({ default: { name: 'Icon', render: () => null } }))

const { default: CloseSheet } = await import('./CloseSheet.vue')
const { close } = await import('../state/cerrar')

const preview = (bloqueantes: ClosePreview['bloqueantes']): ClosePreview => ({
  tipo: 'tab', target_id: 'w1:t1', label: 'tests', workspace_label: 'ws', cierra_workspace: false, tab_count: 1, panes: [], bloqueantes, huella: 'h1',
})

function abrir(bloqueantes: ClosePreview['bloqueantes'], tipo: 'tab' | 'workspace' = 'tab', tabCount = 1) {
  close.target = { tipo, targetId: 'w1:t1', label: 'tests', tabCount, origen: 'manual', destino: '', porQue: '', id: 'abcdefgh12' }
  close.preview = preview(bloqueantes)
  close.notice = null
  close.phase = 'ready'
}

const botones = () => [...document.body.querySelectorAll('button')].filter((b) => b.textContent?.trim() === 'Cerrar igual')

let app: ReturnType<typeof createApp>
beforeEach(() => {
  vi.useFakeTimers()
  app = createApp(CloseSheet)
  app.mount(document.createElement('div'))
})
afterEach(() => {
  app.unmount()
  close.target = null
  close.preview = null
  close.copias = []
  close.phase = 'idle'
  vi.useRealTimers()
})

describe('CloseSheet: Cerrar igual', () => {
  it('aparece solo cuando todos los bloqueantes son unknown', async () => {
    abrir([{ pane_id: 'w1:p1', status: 'unknown' }])
    await nextTick()
    expect(botones()).toHaveLength(1)
    abrir([{ pane_id: 'w1:p1', status: 'unknown' }, { pane_id: 'w1:p2', status: 'working' }])
    await nextTick()
    expect(botones()).toHaveLength(0)
    abrir([])
    await nextTick()
    expect(botones()).toHaveLength(0)
  })

  it('respeta la demora de armado de un workspace con varios tabs', async () => {
    close.target = null
    await nextTick()
    abrir([{ pane_id: 'w1:p1', status: 'unknown' }], 'workspace', 3)
    await nextTick()
    expect(botones()[0].disabled).toBe(true)
    vi.advanceTimersByTime(1100)
    await nextTick()
    expect(botones()[0].disabled).toBe(false)
  })
})

describe('CloseSheet: copia del repo de una tarea', () => {
  const hecho = (copias: Array<{ ruta: string; rama: string; borrable: boolean; motivo: string; estado: 'pendiente'; error: string }>) => {
    close.target = { tipo: 'tab', targetId: 'w1:t1', label: 'tests', tabCount: 1, origen: 'manual', destino: '', porQue: '', id: 'abcdefgh12' }
    close.sesiones = []
    close.copias = copias
    close.phase = 'done'
  }
  const botonBorrar = () => [...document.body.querySelectorAll('button')].find((b) => b.textContent?.includes('Borrar también la copia del repo'))

  it('ofrece borrar la copia solo si se puede', async () => {
    hecho([{ ruta: '/r/proy-x', rama: 'feature/x', borrable: true, motivo: '', estado: 'pendiente', error: '' }])
    await nextTick()
    expect(botonBorrar()).toBeDefined()
    botonBorrar()!.click()
    await vi.waitFor(() => expect(document.body.textContent).toContain('Copia borrada'))
  })

  it('si no se puede, explica por qué y no ofrece el botón', async () => {
    hecho([{ ruta: '/r/proy-x', rama: 'feature/x', borrable: false, motivo: 'Tiene cambios sin guardar', estado: 'pendiente', error: '' }])
    await nextTick()
    expect(botonBorrar()).toBeUndefined()
    expect(document.body.textContent).toContain('No la borro: tiene cambios sin guardar.')
  })
})
