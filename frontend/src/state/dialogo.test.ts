import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/types'
import { normalizeDialog } from '../lib/dialogo'

const api = vi.hoisted(() => ({ getDialog: vi.fn(), answerDialog: vi.fn(), decidirPermiso: vi.fn() }))
vi.mock('./app', () => api)
vi.mock('../motion', () => ({ haptic: vi.fn() }))

import { answerPermiso, askPin, confirmPin, decidirPedido, dlg, loadDialog, onPermisosPedidos, resetDialog } from './dialogo'
import type { PedidoPermiso } from '../api/types'

const pedido: PedidoPermiso = {
  id: 'p1',
  session_id: 's1',
  pane_id: 'w1:p1',
  herramienta: 'Bash',
  entrada: { command: 'ls' },
  estado: 'abierto',
  regla: { herramienta: 'Bash', contenido: 'ls:*', archivo: '/x.json', huella: 'h' },
}

const raw = (huella: string) => ({
  tipo: 'permiso',
  huella,
  pane_id: 'w1:p1',
  permiso: { herramienta: 'Bash', detalle: 'ls', descripcion: '', completo: true, opciones: ['si', 'si_siempre', 'no'], regla: 'ls *', mas_en_terminal: false },
})
const view = (h: string) => normalizeDialog(raw(h))
const ok = { ok: true, interrumpida: false }

beforeEach(() => {
  vi.clearAllMocks()
  resetDialog('s1')
})

describe('dialog state', () => {
  it('sends the fingerprint the PIN sheet was opened with', async () => {
    dlg.view = view('h1')
    askPin()
    expect(dlg.pin.regla).toBe('ls *')
    dlg.view = view('h2')
    api.answerDialog.mockResolvedValue(ok)
    await confirmPin('1234')
    expect(api.answerDialog.mock.calls[0][0].huella).toBe('h1')
  })

  it('sends the mode choice the PIN sheet was opened for', async () => {
    dlg.view = normalizeDialog({ ...raw('h1'), permiso: { ...raw('h1').permiso, opciones: ['si', 'si_auto', 'no'] } })
    askPin('si_auto')
    expect(dlg.pin.choice).toBe('si_auto')
    api.answerDialog.mockResolvedValue(ok)
    await confirmPin('1234')
    expect(api.answerDialog.mock.calls[0][0]).toMatchObject({ permiso: 'si_auto', pin: '1234', huella: 'h1' })
  })

  it('closes the PIN sheet when the prompt changes underneath it', async () => {
    dlg.view = view('h1')
    askPin()
    api.getDialog.mockResolvedValue(view('h2'))
    await loadDialog('s1')
    expect(dlg.pin.open).toBe(false)
    expect(dlg.notice).toBe('El diálogo cambió')
  })

  it('keeps the sheet open when the same prompt reloads', async () => {
    dlg.view = view('h1')
    askPin()
    api.getDialog.mockResolvedValue(view('h1'))
    await loadDialog('s1')
    expect(dlg.pin.open).toBe(true)
  })

  it('409 al decidir recarga y muestra el estado nuevo', async () => {
    api.decidirPermiso = vi.fn().mockRejectedValue(new ApiError(409, 'el pedido ya no espera'))
    api.getDialog = vi.fn().mockResolvedValue({ tipo: 'pedido', pedido: { ...pedido, estado: 'terminal' } })
    dlg.view = { tipo: 'pedido', pedido }
    await decidirPedido('p1', 'permitir')
    expect(api.getDialog).toHaveBeenCalled()
    expect(dlg.view?.tipo === 'pedido' && dlg.view.pedido.estado).toBe('terminal')
  })

  it('decidirPedido con id viejo no llama a decidirPermiso', async () => {
    dlg.view = { tipo: 'pedido', pedido: { ...pedido, id: 'p2' } }
    await decidirPedido('p1', 'permitir')
    expect(api.decidirPermiso).not.toHaveBeenCalled()
  })

  it('descarta el resultado si cambió la sesión mientras viaja', async () => {
    let done: (v: PedidoPermiso) => void
    api.decidirPermiso = vi.fn(
      () =>
        new Promise<PedidoPermiso>((resolve) => {
          done = resolve
        }),
    )
    dlg.view = { tipo: 'pedido', pedido }
    const pending = decidirPedido('p1', 'permitir')
    expect(dlg.phase).toBe('sending')
    const nuevo = { ...pedido, id: 'p2', session_id: 's2', estado: 'abierto' as const }
    resetDialog('s2')
    dlg.view = { tipo: 'pedido', pedido: nuevo }
    done!({ ...pedido, estado: 'permitido' })
    await pending
    expect(dlg.view?.tipo === 'pedido' && dlg.view.pedido.id).toBe('p2')
    expect(dlg.view?.tipo === 'pedido' && dlg.view.pedido.estado).toBe('abierto')
  })

  it('confirmarSiempre manda pin y huella capturados al abrir el PIN', async () => {
    api.decidirPermiso = vi.fn().mockResolvedValue({ ...pedido, estado: 'siempre' })
    dlg.view = { tipo: 'pedido', pedido }
    askPin('siempre')
    dlg.view = { tipo: 'pedido', pedido: { ...pedido, regla: { ...pedido.regla!, huella: 'otra' } } }
    await confirmPin('43215678')
    expect(api.decidirPermiso).toHaveBeenCalledWith('p1', { accion: 'siempre', pin: '43215678', huella_regla: 'h' })
  })

  it('confirmarSiempre con vista distinta cierra PIN sin API', async () => {
    dlg.view = { tipo: 'pedido', pedido }
    askPin('siempre')
    dlg.view = { tipo: 'ninguno' }
    await confirmPin('43215678')
    expect(api.decidirPermiso).not.toHaveBeenCalled()
    expect(dlg.pin.open).toBe(false)
    expect(dlg.notice).toBeTruthy()
  })

  it('confirmarSiempre con PIN incorrecto deja el sheet abierto', async () => {
    dlg.view = { tipo: 'pedido', pedido }
    askPin('siempre')
    api.decidirPermiso = vi.fn().mockRejectedValue(new ApiError(401, 'PIN incorrecto'))
    await confirmPin('00000000')
    expect(dlg.pin.open).toBe(true)
    expect(dlg.pin.error).toBe('PIN incorrecto')
  })

  it('confirmarSiempre con 429 deja cuenta regresiva', async () => {
    dlg.view = { tipo: 'pedido', pedido }
    askPin('siempre')
    api.decidirPermiso = vi.fn().mockRejectedValue(new ApiError(429, 'Demasiados intentos', 60))
    const before = Date.now()
    await confirmPin('43215678')
    expect(dlg.pin.open).toBe(true)
    expect(dlg.pin.error).toBe('Demasiados intentos.')
    expect(dlg.pin.lockedUntil).toBeGreaterThanOrEqual(before + 60_000 - 50)
  })

  describe('onPermisosPedidos', () => {
    it('con diálogo en ninguno y pedido de la sesión recarga', () => {
      resetDialog('s1')
      dlg.view = { tipo: 'ninguno' }
      api.getDialog = vi.fn().mockResolvedValue({ tipo: 'pedido', pedido })
      onPermisosPedidos([pedido])
      expect(api.getDialog).toHaveBeenCalledWith('s1')
    })

    it('pedido de otra sesión no recarga', () => {
      resetDialog('s1')
      dlg.view = { tipo: 'ninguno' }
      api.getDialog = vi.fn()
      onPermisosPedidos([{ ...pedido, id: 'p2', session_id: 's2' }])
      expect(api.getDialog).not.toHaveBeenCalled()
    })

    it('sin sessionId no recarga', () => {
      resetDialog(null)
      dlg.view = { tipo: 'ninguno' }
      api.getDialog = vi.fn()
      onPermisosPedidos([pedido])
      expect(api.getDialog).not.toHaveBeenCalled()
    })

    it('pedido seguido pasa a terminal recarga', async () => {
      api.getDialog = vi.fn().mockResolvedValue({ tipo: 'pedido', pedido })
      await loadDialog('s1')
      dlg.view = { tipo: 'ninguno' }
      api.getDialog = vi.fn().mockResolvedValue({ tipo: 'pedido', pedido: { ...pedido, estado: 'terminal' } })
      onPermisosPedidos([{ ...pedido, estado: 'terminal' }])
      expect(api.getDialog).toHaveBeenCalledWith('s1')
    })
  })

  it('after a 502 the same prompt turns read-only and stays so on reload', async () => {
    dlg.view = view('h1')
    api.answerDialog.mockRejectedValue(new ApiError(502, 'No se confirmó la respuesta: mirá la terminal'))
    api.getDialog.mockResolvedValue(view('h1'))
    await answerPermiso('si')
    expect(dlg.view?.tipo).toBe('desconocido')
    await loadDialog('s1', { keepNotice: true })
    expect(dlg.view?.tipo).toBe('desconocido')
    api.getDialog.mockResolvedValue(view('h3'))
    await loadDialog('s1')
    expect(dlg.view?.tipo).toBe('permiso')
  })
})
