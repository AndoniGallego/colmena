import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, type ClosePreview } from '../api/types'

const api = vi.hoisted(() => ({ accionGuardado: vi.fn(), previewClose: vi.fn(), executeClose: vi.fn(), postBorrarCopia: vi.fn() }))
vi.mock('./app', () => ({
  ALREADY_DONE: /ya (se )?(mand|ejecut|cerr)/i,
  messages: { value: [] },
  guardados: {},
  accionGuardado: api.accionGuardado,
  previewClose: api.previewClose,
  executeClose: api.executeClose,
  postBorrarCopia: api.postBorrarCopia,
}))
vi.mock('../motion', () => ({ haptic: vi.fn() }))

import type { Guardado } from '../api/types'
import { accionLoteSheet, borrarCopia, close, confirmClose, dismissClose, openClose } from './cerrar'

const preview = (over: Partial<ClosePreview> = {}): ClosePreview => ({
  tipo: 'tab',
  target_id: 'w1:t1',
  label: 'tests',
  workspace_label: 'ws',
  cierra_workspace: false,
  tab_count: 1,
  panes: [],
  bloqueantes: [],
  huella: 'h1',
  ...over,
})
const target = { tipo: 'tab' as const, targetId: 'w1:t1', label: 'tests', tabCount: 1, origen: 'jefe' as const, destino: 'ws / tests', porQue: 'listo' }
const settle = () => new Promise((r) => setTimeout(r, 0))

beforeEach(() => {
  vi.clearAllMocks()
  dismissClose()
})

describe('close sheet state', () => {
  it('loads the server preview and becomes ready', async () => {
    api.previewClose.mockResolvedValue(preview())
    openClose(target)
    expect(close.phase).toBe('loading')
    await settle()
    expect(close.phase).toBe('ready')
    expect(close.preview?.huella).toBe('h1')
  })

  it('does not execute while there are blockers', async () => {
    api.previewClose.mockResolvedValue(preview({ bloqueantes: [{ pane_id: 'w1:p1', status: 'working' }] }))
    openClose(target)
    await settle()
    await confirmClose()
    expect(api.executeClose).not.toHaveBeenCalled()
  })

  it('forzar: with only unknown blockers it executes with forzar; with a working one it never does', async () => {
    api.previewClose.mockResolvedValue(preview({ bloqueantes: [{ pane_id: 'w1:p1', status: 'unknown' }] }))
    api.executeClose.mockResolvedValue({ ok: true, sesiones: [], event: null })
    openClose(target)
    await settle()
    await confirmClose()
    expect(api.executeClose).not.toHaveBeenCalled()
    await confirmClose(false, true)
    expect(api.executeClose.mock.calls[0][0]).toMatchObject({ forzar: true })
    dismissClose()
    api.previewClose.mockResolvedValue(preview({ bloqueantes: [{ pane_id: 'w1:p1', status: 'working' }] }))
    openClose(target)
    await settle()
    await confirmClose(false, true)
    expect(api.executeClose).toHaveBeenCalledTimes(1)
  })

  it('sends the fingerprint, marks the card and finishes', async () => {
    api.previewClose.mockResolvedValue(preview())
    api.executeClose.mockResolvedValue({ ok: true, sesiones: [{ session_id: 'abcdefgh1', cwd: '/x', titulo: 't' }], event: null })
    openClose(target)
    await settle()
    await confirmClose()
    expect(api.executeClose.mock.calls[0][0]).toMatchObject({ huella: 'h1', origen: 'jefe', tipo: 'tab', target_id: 'w1:t1' })
    expect(close.phase).toBe('done')
    expect(close.sesiones).toHaveLength(1)
  })

  it('uses the id of the block when Centinela proposed it so every device resolves the card', async () => {
    api.previewClose.mockResolvedValue(preview())
    api.executeClose.mockResolvedValue({ ok: true, sesiones: [], event: null })
    openClose({ ...target, id: '0b6f1c1e-4a55-4e1d-9d33-1f3c2a7d9e10' })
    await settle()
    await confirmClose()
    expect(api.executeClose.mock.calls[0][0].id).toBe('0b6f1c1e-4a55-4e1d-9d33-1f3c2a7d9e10')
  })

  it('warns when Herdr could not confirm the close', async () => {
    api.previewClose.mockResolvedValue(preview())
    api.executeClose.mockResolvedValue({ ok: true, sesiones: [{ session_id: 'abcdefgh1', cwd: '', titulo: '' }], event: null, aviso: 'No pude confirmar' })
    openClose(target)
    await settle()
    await confirmClose()
    expect(close.listoTxt).toBe('No pude confirmar')
    expect(close.phase).toBe('done')
  })

  it('shows the blockers a 409 brings and stays open', async () => {
    const blocked = [{ pane_id: 'w1:p1', status: 'working' as const }]
    api.previewClose.mockResolvedValueOnce(preview()).mockResolvedValue(preview({ bloqueantes: blocked }))
    api.executeClose.mockRejectedValue(new ApiError(409, 'Frenala primero', null, blocked))
    openClose(target)
    await settle()
    await confirmClose()
    await settle()
    expect(close.phase).toBe('ready')
    expect(close.notice).toBe('Frenala primero')
    expect(close.preview?.bloqueantes).toHaveLength(1)
  })

  it('treats an already closed target as done', async () => {
    api.previewClose.mockResolvedValue(preview())
    api.executeClose.mockRejectedValue(new ApiError(409, 'Ya se cerró'))
    openClose(target)
    await settle()
    await confirmClose()
  })

  it('reports a target that no longer exists', async () => {
    api.previewClose.mockRejectedValue(new ApiError(404, 'Ya no existe'))
    openClose(target)
    await settle()
    expect(close.phase).toBe('gone')
  })

  it('a Claude that showed up after the preview turns the sheet into an error', async () => {
    api.previewClose.mockResolvedValueOnce(preview())
    api.previewClose.mockRejectedValueOnce(new ApiError(403, 'Ese tab del workspace protegido tiene una sesión de Claude'))
    api.executeClose.mockRejectedValue(new ApiError(403, 'Ese tab del workspace protegido tiene una sesión de Claude'))
    openClose(target)
    await settle()
    await confirmClose()
    await settle()
    expect(api.previewClose).toHaveBeenCalledTimes(2)
    expect(close.phase).toBe('error')
    expect(close.error).toContain('Claude')
  })
})


const lote = (over: Partial<Guardado> = {}, estado: 'guardando' | 'cerrado' | 'error' = 'guardando', error = ''): Guardado => ({
  id: 'id-fijo-0001',
  origen: 'manual',
  plan_id: '',
  vencido: false,
  puede_cerrar_igual: false,
  terminado: estado !== 'guardando',
  targets: [{ key: 't1', tipo: 'tab', target_id: 'w1:t1', label: 'tests', estado, error, guardado: '', sesiones: [{ session_id: 'abcdefgh1', cwd: '/x', titulo: 't' }], panes: [{ pane_id: 'w1:p1', titulo: 'a', estado: 'guardando' }] }],
  ...over,
})

describe('close sheet: guardado en Engram', () => {
  const abrir = async () => {
    api.previewClose.mockResolvedValue(preview())
    openClose({ ...target, id: 'id-fijo-0001' })
    await settle()
  }

  it('asks to close without saving only when the user says so', async () => {
    await abrir()
    api.executeClose.mockResolvedValue({ ok: true, sesiones: [], event: null })
    await confirmClose(true)
    expect(api.executeClose.mock.calls[0][0].sin_guardar).toBe(true)
    await abrir()
    await confirmClose()
    expect(api.executeClose.mock.calls[1][0].sin_guardar).toBeUndefined()
  })

  it('waits for the sessions when the server answers with a lote', async () => {
    await abrir()
    api.executeClose.mockResolvedValue({ ok: true, sesiones: [], event: null, guardando: lote() })
    await confirmClose()
    expect(close.phase).toBe('guardando')
    expect(close.lote?.targets[0].panes[0].estado).toBe('guardando')
  })

  it('closes the sheet when the lote ends closed (Cerrar igual)', async () => {
    await abrir()
    api.executeClose.mockResolvedValue({ ok: true, sesiones: [], event: null, guardando: lote({ vencido: true, puede_cerrar_igual: true }) })
    await confirmClose()
    api.accionGuardado.mockResolvedValue(lote({}, 'cerrado'))
    await accionLoteSheet('cerrar_igual')
    expect(api.accionGuardado).toHaveBeenCalledWith('id-fijo-0001', 'cerrar_igual')
    expect(close.phase).toBe('done')
    expect(close.sesiones).toHaveLength(1)
  })

  it('goes back to the list when the target changed while saving', async () => {
    await abrir()
    api.executeClose.mockResolvedValue({ ok: true, sesiones: [], event: null, guardando: lote() })
    await confirmClose()
    api.accionGuardado.mockResolvedValue(lote({}, 'error', 'cambió mientras guardaba: revisalo de nuevo'))
    await accionLoteSheet('esperar_mas')
    await settle()
    expect(close.phase).toBe('ready')
    expect(close.notice).toBe('cambió mientras guardaba: revisalo de nuevo')
  })

  it('a discarded lote without targets frees the sheet instead of leaving it on "guardando"', async () => {
    await abrir()
    api.executeClose.mockResolvedValue({ ok: true, sesiones: [], event: null, guardando: lote() })
    await confirmClose()
    api.previewClose.mockResolvedValue(preview())
    api.accionGuardado.mockResolvedValue(lote({ targets: [], terminado: true }))
    await accionLoteSheet('esperar_mas')
    await settle()
    expect(close.phase).toBe('ready')
    expect(close.notice).toContain('ya se resolvió')
  })
})

describe('close sheet: copia del repo de una tarea', () => {
  const copia = { ruta: '/r/proy-x', rama: 'feature/x', borrable: true, motivo: '' }
  const abrir = async () => {
    api.previewClose.mockResolvedValue(preview())
    openClose({ ...target, id: 'id-fijo-0001' })
    await settle()
  }

  it('guarda las copias ofrecidas y no se cierra solo', async () => {
    await abrir()
    vi.useFakeTimers()
    try {
      api.executeClose.mockResolvedValue({ ok: true, sesiones: [], event: null, copias: [copia] })
      await confirmClose()
      vi.advanceTimersByTime(5000)
      expect(close.phase).toBe('done')
      expect(close.target).not.toBeNull()
      expect(close.copias).toEqual([{ ...copia, estado: 'pendiente', error: '' }])
    } finally {
      vi.useRealTimers()
    }
  })

  it('sin copias se cierra solo como siempre', async () => {
    await abrir()
    vi.useFakeTimers()
    try {
      api.executeClose.mockResolvedValue({ ok: true, sesiones: [], event: null })
      await confirmClose()
      vi.advanceTimersByTime(5000)
      expect(close.copias).toEqual([])
      expect(close.phase).toBe('idle')
    } finally {
      vi.useRealTimers()
    }
  })

  it('también llegan por el cierre con guardado en Engram', async () => {
    await abrir()
    api.executeClose.mockResolvedValue({ ok: true, sesiones: [], event: null, guardando: lote() })
    await confirmClose()
    const l = lote({}, 'cerrado')
    l.targets[0].copias = [copia]
    api.accionGuardado.mockResolvedValue(l)
    await accionLoteSheet('cerrar_igual')
    expect(close.copias).toHaveLength(1)
  })

  it('borrarCopia la borra y la marca', async () => {
    await abrir()
    api.executeClose.mockResolvedValue({ ok: true, sesiones: [], event: null, copias: [copia] })
    await confirmClose()
    api.postBorrarCopia.mockResolvedValue({ ok: true })
    await borrarCopia('/r/proy-x')
    expect(api.postBorrarCopia).toHaveBeenCalledWith('/r/proy-x')
    expect(close.copias[0].estado).toBe('borrada')
  })

  it('borrarCopia no borra si no era borrable', async () => {
    await abrir()
    api.executeClose.mockResolvedValue({ ok: true, sesiones: [], event: null, copias: [{ ...copia, borrable: false, motivo: 'Tiene cambios sin guardar' }] })
    await confirmClose()
    await borrarCopia('/r/proy-x')
    expect(api.postBorrarCopia).not.toHaveBeenCalled()
  })

  it('si el servidor la rechaza muestra el motivo', async () => {
    await abrir()
    api.executeClose.mockResolvedValue({ ok: true, sesiones: [], event: null, copias: [copia] })
    await confirmClose()
    api.postBorrarCopia.mockRejectedValue(new ApiError(409, 'La rama no está mergeada'))
    await borrarCopia('/r/proy-x')
    expect(close.copias[0]).toMatchObject({ estado: 'error', error: 'La rama no está mergeada' })
  })
})
