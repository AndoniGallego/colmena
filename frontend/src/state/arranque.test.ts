import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Api, Board } from '../api/types'

vi.hoisted(() => {
  vi.stubGlobal('window', { matchMedia: () => ({ matches: false, addEventListener() {} }), addEventListener() {} })
  vi.stubGlobal('location', { search: '', pathname: '/' })
})

const { init, auth, boot } = await import('./app')

const boardVacio: Board = {
  updated_at: '',
  focused_tab_id: null,
  self_pane_id: null,
  workspaces: [],
  terminales: 'ok',
  conflictos: [],
  caidos: [],
}

beforeEach(() => {
  auth.value = 'checking'
})

describe('arranque del notch', () => {
  it('el notch arranca sin presencia y sin historial', async () => {
    const subscribeBoard = vi.fn(() => () => {})
    const getHistory = vi.fn()
    init(
      {
        getBoard: vi.fn().mockResolvedValue(boardVacio),
        subscribeBoard,
        getHistory,
      } as unknown as Api,
      { presencia: false, ligero: true },
    )
    await boot()
    expect(auth.value).toBe('ready')
    expect(subscribeBoard).toHaveBeenCalledWith(expect.any(Object), expect.objectContaining({ presencia: false }))
    expect(getHistory).not.toHaveBeenCalled()
  })
})

describe('notas al arrancar', () => {
  it('boot carga las notas', async () => {
    const listarNotas = vi.fn().mockResolvedValue({ notas: [], pendientes: 0, version: 1 })
    init({ getBoard: vi.fn().mockResolvedValue(boardVacio), subscribeBoard: vi.fn(() => () => {}), listarNotas } as unknown as Api)
    await boot()
    await vi.waitFor(() => expect(listarNotas).toHaveBeenCalled())
  })
})
