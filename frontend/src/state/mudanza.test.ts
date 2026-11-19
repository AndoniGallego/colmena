import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { ApiError } from '../api/types'
import type { Candidata, Pendiente } from '../api/mudanzaApi'

const api = vi.hoisted(() => ({
  listarMudanza: vi.fn(),
  mudar: vi.fn(),
  mudarTodas: vi.fn(),
  retomarMudanza: vi.fn(),
}))
vi.mock('./app', () => ({ boardState: { value: { board: null } } }))
vi.mock('../motion', () => ({ haptic: vi.fn() }))
vi.mock('../api/mudanzaApi', () => ({
  listarMudanza: api.listarMudanza,
  mudar: api.mudar,
  mudarTodas: api.mudarTodas,
  retomarMudanza: api.retomarMudanza,
}))

import {
  abrirMudanza,
  abrirMudarTodas,
  confirmarMudanza,
  mz,
  refreshMudanza,
  retomar,
} from './mudanza'

const cand = (pane: string, puede = true, motivo = ''): Candidata => ({
  pane_id: pane,
  session_id: `s-${pane}`,
  nombre: `Nom ${pane}`,
  workspace: 'ws',
  puede,
  motivo,
})

const flush = () => new Promise((r) => setTimeout(r, 0))

beforeEach(() => {
  vi.clearAllMocks()
  api.listarMudanza.mockResolvedValue({ disponible: true, motivo: '', sesiones: [], pendientes: [] })
  Object.assign(mz, {
    disponible: true,
    motivo: '',
    sesiones: [],
    pendientes: [],
    loaded: false,
    open: false,
    modo: 'una',
    objetivo: null,
    ocupado: false,
    error: '',
    resultado: null,
    listo: false,
    listoTxt: '',
    bloqueoMsg: '',
  })
})

describe('mudanza state', () => {
  it('abrir con una no-quieta no abre y avisa', () => {
    mz.sesiones = [cand('p1', false, 'Está trabajando')]
    abrirMudanza('p1')
    expect(mz.open).toBe(false)
    expect(mz.bloqueoMsg).toBe('Está trabajando')
  })

  it('confirmar una llama mudar con el pane y muestra listo', async () => {
    vi.useFakeTimers()
    mz.sesiones = [cand('p1')]
    abrirMudanza('p1')
    api.mudar.mockResolvedValue({ ok: true, mudanza: {} })
    await confirmarMudanza()
    expect(api.mudar).toHaveBeenCalledWith('p1')
    expect(mz.listo).toBe(true)
    expect(mz.listoTxt).toContain('Nom p1')
    vi.advanceTimersByTime(1200)
    expect(mz.open).toBe(false)
    vi.useRealTimers()
  })

  it('error del server queda en mz.error y la hoja sigue abierta', async () => {
    mz.sesiones = [cand('p1')]
    abrirMudanza('p1')
    api.mudar.mockRejectedValue(new ApiError(409, 'Se puso a trabajar'))
    await confirmarMudanza()
    await flush()
    expect(mz.error).toBe('Se puso a trabajar')
    expect(mz.open).toBe(true)
  })

  it('mudar todas manda solo las quietas y guarda el resultado', async () => {
    mz.sesiones = [cand('a'), cand('b', false, 'busy'), cand('c')]
    abrirMudarTodas()
    const res = { ok: true, mudadas: [{}], saltadas: [{ pane_id: 'b', motivo: 'busy' }], fallidas: [] }
    api.mudarTodas.mockResolvedValue(res)
    await confirmarMudanza()
    expect(api.mudarTodas).toHaveBeenCalledWith(['a', 'c'])
    expect(mz.resultado).toEqual(res)
    expect(mz.open).toBe(true)
  })

  it('retomar llama con el id del pendiente', async () => {
    const p: Pendiente = { id: 'mud-1', pane_viejo: 'h1', session_id: 's', nombre: 'X', workspace: 'w', estado: 'pendiente' }
    api.retomarMudanza.mockResolvedValue({ ok: true, mudanza: {} })
    await retomar(p)
    expect(api.retomarMudanza).toHaveBeenCalledWith('mud-1')
  })

  it('respuestas viejas de refresh se descartan', async () => {
    let resolve1!: (v: unknown) => void
    let resolve2!: (v: unknown) => void
    api.listarMudanza.mockReturnValueOnce(new Promise((r) => (resolve1 = r)))
    api.listarMudanza.mockReturnValueOnce(new Promise((r) => (resolve2 = r)))
    const p1 = refreshMudanza()
    const p2 = refreshMudanza()
    resolve2({ disponible: true, motivo: '', sesiones: [], pendientes: [] })
    await p2
    resolve1({ disponible: false, motivo: 'viejo', sesiones: [], pendientes: [] })
    await p1
    expect(mz.disponible).toBe(true)
    expect(mz.motivo).toBe('')
  })

  it('refresh con hoja cerrada no guarda error', async () => {
    api.listarMudanza.mockRejectedValue(new ApiError(500, 'boom'))
    await refreshMudanza()
    expect(mz.error).toBe('')
  })
})

describe('textos mudanza', () => {
  it('nada visible dice "flujo"', () => {
    const archivos = ['../components/MudanzaSheet.vue', '../components/MudanzaChip.vue', './mudanza.ts'] as const
    const todo = archivos.map((f) => readFileSync(new URL(f, import.meta.url).pathname, 'utf8')).join('\n')
    expect(todo.toLowerCase()).not.toContain('flujo')
  })
})
