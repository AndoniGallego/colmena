import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, type LimpiezaItem, type LimpiezaPreviewItem } from '../api/types'

const api = vi.hoisted(() => ({ getLimpieza: vi.fn(), previewLimpieza: vi.fn(), ejecutarLimpieza: vi.fn(), accionGuardado: vi.fn() }))
vi.mock('./app', () => ({ boardState: { value: { board: null } }, ...api }))
vi.mock('../motion', () => ({ haptic: vi.fn() }))
vi.mock('../lib/storage', () => ({ loadLimpiezaDias: () => null, saveLimpiezaDias: vi.fn() }))

import { abrirLimpieza, accionLimpieza, cerrarHoja, confirmar, lm, marcadas, reintentar, revisar, toggleMarca, volverAElegir } from './limpieza'

const item = (id: string, over: Partial<LimpiezaItem> = {}): LimpiezaItem => ({
  tipo: 'tab', target_id: id, workspace: 'ws', label: id, razones: [{ tipo: 'quieto', dias: 8 }], sesiones: [], terminales: 1, marcado: true, bloqueado: null, ...over,
})
const prev = (id: string, over: Partial<LimpiezaPreviewItem> = {}): LimpiezaPreviewItem => ({
  tipo: 'tab', target_id: id, error: '', bloqueantes: [],
  preview: { tipo: 'tab', target_id: id, label: id, workspace_label: 'ws', cierra_workspace: false, tab_count: 1, panes: [], bloqueantes: [], huella: `h-${id}` },
  ...over,
})
const settle = () => new Promise((r) => setTimeout(r, 0))

async function opened(items: LimpiezaItem[]) {
  api.getLimpieza.mockResolvedValue({ dias: 7, items, generado_at: '', git: 'ok' })
  abrirLimpieza()
  await settle()
}

beforeEach(() => {
  vi.clearAllMocks()
  lm.paso = 'elegir'
  cerrarHoja()
  lm.items = []
  lm.loaded = false
  lm.marcas = {}
})

describe('limpieza state', () => {
  it('marks proposed rows, never blocked ones, and blocked cannot be toggled', async () => {
    await opened([item('a'), item('b', { bloqueado: 'corriendo' })])
    expect(marcadas.value.map((i) => i.target_id)).toEqual(['a'])
    toggleMarca('tab:b')
    expect(lm.marcas['tab:b']).toBeUndefined()
    toggleMarca('tab:a')
    expect(marcadas.value).toEqual([])
  })

  it('review unmarks rows the server flags and keeps the motive', async () => {
    await opened([item('a'), item('b')])
    api.previewLimpieza.mockResolvedValue([prev('a'), prev('b', { preview: null, error: 'Cambió' })])
    await revisar()
    expect(lm.paso).toBe('revisar')
    expect(lm.motivos['tab:b']).toBe('Cambió')
    expect(lm.marcas['tab:b']).toBe(false)
    expect(marcadas.value.map((i) => i.target_id)).toEqual(['a'])
  })

  it('going back during review ignores the late preview', async () => {
    await opened([item('a')])
    let resolve!: (v: LimpiezaPreviewItem[]) => void
    api.previewLimpieza.mockReturnValue(new Promise((r) => (resolve = r)))
    const p = revisar()
    volverAElegir()
    resolve([prev('a')])
    await p
    expect(lm.paso).toBe('elegir')
    expect(lm.previews).toEqual({})
  })

  it('confirm sends the huella of each reviewed row with fresh ids and one lote', async () => {
    await opened([item('a'), item('b')])
    api.previewLimpieza.mockResolvedValue([prev('a'), prev('b')])
    await revisar()
    api.ejecutarLimpieza.mockImplementation(async (_b, h) => {
      h.onItem({ target_id: 'a', ok: true, error: '', sesiones: [] })
      h.onItem({ target_id: 'b', ok: false, error: 'Cambió', sesiones: [] })
      h.onFin({ cerrados: 1, salteados: 1 })
    })
    await confirmar()
    const body = api.ejecutarLimpieza.mock.calls[0][0]
    expect(body.items.map((x: { huella: string }) => x.huella)).toEqual(['h-a', 'h-b'])
    expect(new Set(body.items.map((x: { id: string }) => x.id)).size).toBe(2)
    expect(body.lote_id).toMatch(/^[A-Za-z0-9_-]{8,64}$/)
    expect(lm.paso).toBe('fin')
    expect([lm.cerrados, lm.salteados]).toEqual([1, 1])
  })

  it('an unresolved item after a dropped stream is reported as unknown, never as closed', async () => {
    await opened([item('a')])
    api.previewLimpieza.mockResolvedValue([prev('a')])
    await revisar()
    api.ejecutarLimpieza.mockRejectedValue(new Error('network'))
    await confirmar()
    expect(lm.resultados['tab:a'].ok).toBe(false)
    expect(lm.resultados['tab:a'].error).toContain('revisá el tablero')
    expect(lm.cerrados).toBe(0)
  })

  it('does not confirm with nothing reviewed or while the sheet is not in review', async () => {
    await opened([item('a')])
    await confirmar()
    expect(api.ejecutarLimpieza).not.toHaveBeenCalled()
  })

  it('retry goes back through review instead of closing straight away', async () => {
    await opened([item('a')])
    api.previewLimpieza.mockResolvedValue([prev('a')])
    await revisar()
    api.ejecutarLimpieza.mockImplementation(async (_b, h) => {
      h.onItem({ target_id: 'a', ok: false, error: 'x', sesiones: [] })
      h.onFin({ cerrados: 0, salteados: 1 })
    })
    await confirmar()
    api.ejecutarLimpieza.mockClear()
    reintentar(['tab:a'])
    await settle()
    expect(lm.paso).toBe('revisar')
    expect(api.ejecutarLimpieza).not.toHaveBeenCalled()
  })

  it('preselection from Centinela marks only the known candidates', async () => {
    api.getLimpieza.mockResolvedValue({ dias: 7, items: [item('a'), item('b'), item('c', { bloqueado: 'sin_leer' })], generado_at: '', git: 'ok' })
    abrirLimpieza(['b', 'c', 'nope'])
    await settle()
    expect(marcadas.value.map((i) => i.target_id)).toEqual(['b'])
  })

  it('server error on load surfaces a message', async () => {
    api.getLimpieza.mockRejectedValue(new ApiError(500, 'boom'))
    abrirLimpieza()
    await settle()
    expect(lm.error).toBe('boom')
  })
})

describe('limpieza con guardado', () => {
  const lote = { id: 'L1', vencido: false, puede_cerrar_igual: false, targets: [] } as never

  it('confirmar sends sin_guardar only when asked, and keeps the lote while closing', async () => {
    await opened([item('a')])
    api.previewLimpieza.mockResolvedValue([prev('a')])
    await revisar()
    let visto: unknown = null
    api.ejecutarLimpieza.mockImplementation(async (_b, h) => {
      h.onGuardando(lote)
      visto = lm.lote
      h.onItem({ target_id: 'a', ok: true, error: '', sesiones: [] })
      h.onFin({ cerrados: 1, salteados: 0 })
    })
    await confirmar(true)
    expect(api.ejecutarLimpieza.mock.calls.at(-1)![0].sin_guardar).toBe(true)
    expect(visto).toEqual(lote)
    expect(lm.lote).toBeNull()
    expect(lm.paso).toBe('fin')
  })

  it('default confirm does not send sin_guardar', async () => {
    await opened([item('a')])
    api.previewLimpieza.mockResolvedValue([prev('a')])
    await revisar()
    api.ejecutarLimpieza.mockImplementation(async (_b, h) => h.onFin({ cerrados: 0, salteados: 0 }))
    await confirmar()
    expect('sin_guardar' in api.ejecutarLimpieza.mock.calls.at(-1)![0]).toBe(false)
  })

  it('accionLimpieza calls the lote action and replaces the lote', async () => {
    await opened([item('a')])
    api.previewLimpieza.mockResolvedValue([prev('a')])
    await revisar()
    const nuevo = { ...(lote as object), vencido: true } as never
    api.accionGuardado.mockResolvedValue(nuevo)
    let fin: () => void = () => {}
    api.ejecutarLimpieza.mockImplementation(async (_b, h) => {
      h.onGuardando(lote)
      await new Promise<void>((r) => (fin = r))
      h.onFin({ cerrados: 0, salteados: 0 })
    })
    const p = confirmar()
    await settle()
    await accionLimpieza('cerrar_igual')
    expect(api.accionGuardado).toHaveBeenCalledWith('L1', 'cerrar_igual')
    expect(lm.lote).toEqual(nuevo)
    fin()
    await p
  })
})
