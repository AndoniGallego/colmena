import { describe, expect, it, vi } from 'vitest'
import { debeAbrirTerminalLocal } from '../lib/abrirTerminalCliente'

describe('manejo abrir_terminal en app', () => {
  it('llama abrirVivo solo en escritorio con presencia', async () => {
    const abrirVivo = vi.fn()
    const { manejarAbrirTerminalSse } = await import('./abrirTerminalSse')
    manejarAbrirTerminalSse({ pane_id: 'g1:p1', titulo: 'T' }, { presenciaActiva: true, esEscritorio: true }, abrirVivo)
    expect(abrirVivo).toHaveBeenCalledWith('g1:p1', 'T')
    abrirVivo.mockClear()
    manejarAbrirTerminalSse({ pane_id: 'g1:p1', titulo: 'T' }, { presenciaActiva: true, esEscritorio: false }, abrirVivo)
    expect(abrirVivo).not.toHaveBeenCalled()
    manejarAbrirTerminalSse({ pane_id: 'g1:p1', titulo: 'T' }, { presenciaActiva: false, esEscritorio: true }, abrirVivo)
    expect(abrirVivo).not.toHaveBeenCalled()
  })

  it('debeAbrirTerminalLocal alinea con la regla', () => {
    expect(debeAbrirTerminalLocal({ presenciaActiva: true, esEscritorio: true })).toBe(true)
  })
})
