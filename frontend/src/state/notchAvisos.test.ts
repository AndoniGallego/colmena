import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Agent, Api, Aviso, AvisosPage, Board } from '../api/types'

vi.hoisted(() => {
  vi.stubGlobal('window', {
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    addEventListener() {},
    screen: { availWidth: 800, availHeight: 600 },
  })
  vi.stubGlobal('location', { search: '', pathname: '/notch' })
})

vi.mock('../motion', () => ({
  isSoft: () => true,
  gsap: { set() {}, to() {}, fromTo() {}, killTweensOf() {} },
}))

const getAvisos = vi.hoisted(() => vi.fn<Api['getAvisos']>())
const marcarAvisosLeidos = vi.hoisted(() => vi.fn<Api['marcarAvisosLeidos']>())
const marcarAvisosDe = vi.hoisted(() => vi.fn<Api['marcarAvisosDe']>())

import { MAX_ESPERA_TERMINO_MS, type AvisoNotch } from '../lib/notchAvisos'

const { auth, avisoEvent, boardState, init } = await import('./app')
const { modo, setPuente } = await import('./notch')
const { avisoActual, cerrarAviso, cola, iniciarAvisosNotch, marcarRetenerRespuestaAviso } = await import('./notchAvisos')

const aviso = (id: number, kind: Aviso['kind'], over: Partial<Aviso> = {}): Aviso => ({
  id,
  ts: id,
  kind,
  titulo: `t${id}`,
  cuerpo: `c${id}`,
  session_id: over.session_id ?? 's1',
  pane_id: 'p1',
  fecha: '',
  mr: '',
  tag: '',
  entregado: true,
  leido: false,
  motivo: '',
  ...over,
})

const page = (items: Aviso[]): AvisosPage => ({
  items,
  hayMas: false,
  noLeidos: 0,
  leidosHasta: 0,
})

const flush = () => new Promise<void>((r) => setTimeout(r, 0))

const NOW = Date.parse('2026-11-04T18:00:00Z')
const hace = (min: number) => new Date(NOW - min * 60_000).toISOString()

function ag(pane: string, sid: string, over: Partial<Agent> = {}): Agent {
  return {
    pane_id: pane,
    kind: 'claude',
    status: 'idle',
    session_id: sid,
    title: 't-' + pane,
    doing: '',
    pending: '',
    asks_user: false,
    last_activity: hace(30),
    ...over,
  }
}

function board(agents: Agent[]): Board {
  return {
    updated_at: hace(0),
    focused_tab_id: null,
    self_pane_id: null,
    workspaces: [
      {
        id: 'w1',
        number: 1,
        label: 'Acme',
        status: 'idle',
        tabs: agents.map((agent, i) => ({
          id: `t${i}`,
          label: String(i + 1),
          agents: [agent],
        })),
      },
    ],
    terminales: 'ok',
    conflictos: [],
    caidos: [],
  }
}

function fakeApi(): Api {
  return {
    getAvisos,
    marcarAvisosLeidos,
    marcarAvisosDe,
  } as unknown as Api
}

function pulseAviso() {
  avisoEvent.value = { id: 99, n: (avisoEvent.value?.n ?? 0) + 1 }
}

beforeEach(async () => {
  vi.useRealTimers()
  vi.clearAllMocks()
  init(fakeApi())
  getAvisos.mockResolvedValue(page([]))
  marcarAvisosLeidos.mockResolvedValue(0)
  marcarAvisosDe.mockResolvedValue(0)
  auth.value = 'checking'
  avisoEvent.value = null
  modo.value = 'cerrado'
  avisoActual.value = null
  cola.splice(0, cola.length)
  boardState.value = { ...boardState.value, board: null, connection: 'live' }
  setPuente({ enPrograma: false, tamano: vi.fn(), forma: vi.fn(), arrastrar: vi.fn(), abrirColmena: vi.fn(), abrirBiblioteca: vi.fn(), aviso: vi.fn(), mostrarReunion: vi.fn() })
  const { _resetIniciar } = await import('./notchAvisos')
  _resetIniciar()
})

describe('state/notchAvisos', () => {
  it('al arrancar no muestra los avisos que ya estaban', async () => {
    const sonar = vi.fn()
    getAvisos.mockResolvedValue(page([aviso(7, 'asks')]))
    iniciarAvisosNotch({ sonar })
    auth.value = 'ready'
    await flush()
    await flush()
    expect(avisoActual.value).toBeNull()
    expect(sonar).not.toHaveBeenCalled()
  })

  it('un aviso nuevo de te toca sale y suena; un done sale sin sonido', async () => {
    const sonar = vi.fn()
    const puenteAviso = vi.fn()
    setPuente({ enPrograma: true, tamano: vi.fn(), forma: vi.fn(), arrastrar: vi.fn(), abrirColmena: vi.fn(), abrirBiblioteca: vi.fn(), aviso: puenteAviso, mostrarReunion: vi.fn() })
    getAvisos
      .mockResolvedValueOnce(page([aviso(7, 'asks')]))
      .mockResolvedValueOnce(page([aviso(8, 'asks', { session_id: 's8' })]))
    iniciarAvisosNotch({ sonar })
    auth.value = 'ready'
    await flush()
    await flush()
    sonar.mockClear()
    puenteAviso.mockClear()
    boardState.value = {
      ...boardState.value,
      board: board([ag('p8', 's8', { status: 'blocked', asks_user: true })]),
    }
    await nextTick()
    pulseAviso()
    await flush()
    await flush()
    expect(avisoActual.value?.id).toBe(8)
    expect(sonar).toHaveBeenCalledTimes(1)
    expect(puenteAviso).toHaveBeenCalledWith('te-toca')

    getAvisos.mockResolvedValueOnce(page([aviso(9, 'done')]))
    pulseAviso()
    await flush()
    await flush()
    expect(sonar).toHaveBeenCalledTimes(1)
  })

  it('un aviso que llega antes de la base no muestra los viejos', async () => {
    const sonar = vi.fn()
    let resolveBase!: (v: AvisosPage) => void
    const baseLate = new Promise<AvisosPage>((r) => {
      resolveBase = r
    })
    getAvisos.mockImplementationOnce(() => baseLate)
    iniciarAvisosNotch({ sonar })
    auth.value = 'ready'
    await flush()
    getAvisos.mockResolvedValueOnce(page([aviso(7, 'asks')]))
    pulseAviso()
    await flush()
    resolveBase(page([aviso(7, 'asks')]))
    await flush()
    await flush()
    expect(avisoActual.value).toBeNull()
    expect(sonar).not.toHaveBeenCalled()
  })

  it('después de reconectar no repite lo del corte', async () => {
    const sonar = vi.fn()
    getAvisos
      .mockResolvedValueOnce(page([aviso(7, 'asks')]))
      .mockResolvedValueOnce(page([aviso(8, 'done'), aviso(9, 'asks')]))
      .mockResolvedValueOnce(page([aviso(10, 'done'), aviso(9, 'asks'), aviso(8, 'done')]))
    iniciarAvisosNotch({ sonar })
    auth.value = 'ready'
    await flush()
    await flush()
    boardState.value = { ...boardState.value, connection: 'reconnecting' }
    await nextTick()
    boardState.value = { ...boardState.value, connection: 'live' }
    await flush()
    await flush()
    sonar.mockClear()
    pulseAviso()
    await flush()
    await flush()
    expect(avisoActual.value?.id).toBe(10)
    expect(sonar).not.toHaveBeenCalled()
  })

  it('con el panel abierto no encola', async () => {
    const sonar = vi.fn()
    getAvisos
      .mockResolvedValueOnce(page([aviso(7, 'asks')]))
      .mockResolvedValueOnce(page([aviso(8, 'blocked')]))
    iniciarAvisosNotch({ sonar })
    auth.value = 'ready'
    await flush()
    await flush()
    modo.value = 'panel'
    pulseAviso()
    await flush()
    await flush()
    expect(avisoActual.value).toBeNull()
    expect(cola).toEqual([])
    expect(sonar).toHaveBeenCalledTimes(1)
  })

  it('muestra te-toca antes que un done que llegó en el mismo lote', async () => {
    const sonar = vi.fn()
    getAvisos
      .mockResolvedValueOnce(page([aviso(7, 'asks')]))
      .mockResolvedValueOnce(page([aviso(8, 'done'), aviso(9, 'asks', { session_id: 's9' })]))
    iniciarAvisosNotch({ sonar })
    auth.value = 'ready'
    boardState.value = {
      ...boardState.value,
      board: board([ag('p9', 's9', { status: 'blocked', asks_user: true })]),
    }
    await nextTick()
    pulseAviso()
    await flush()
    await flush()
    expect(avisoActual.value?.id).toBe(9)
    expect(cola.map((a) => a.id)).toEqual([8])
  })

  it('descarta un done que esperó demasiado en cola', async () => {
    vi.useFakeTimers({ now: NOW, shouldAdvanceTime: true })
    const sonar = vi.fn()
    getAvisos
      .mockResolvedValueOnce(page([aviso(7, 'asks')]))
      .mockResolvedValueOnce(page([aviso(8, 'done'), aviso(9, 'asks', { session_id: 's1' })]))
    iniciarAvisosNotch({ sonar })
    auth.value = 'ready'
    boardState.value = {
      ...boardState.value,
      board: board([ag('p1', 's1', { status: 'blocked', asks_user: true })]),
    }
    await flush()
    await flush()
    pulseAviso()
    await flush()
    await flush()
    expect(avisoActual.value?.id).toBe(9)
    await vi.advanceTimersByTimeAsync(MAX_ESPERA_TERMINO_MS + 1)
    cerrarAviso()
    await flush()
    await flush()
    expect(avisoActual.value).toBeNull()
    expect(cola.some((a) => a.id === 8)).toBe(false)
    vi.useRealTimers()
  })

  it('encola y muestra de a uno', async () => {
    const sonar = vi.fn()
    getAvisos
      .mockResolvedValueOnce(page([aviso(7, 'asks')]))
      .mockResolvedValueOnce(page([aviso(8, 'asks'), aviso(9, 'done')]))
    iniciarAvisosNotch({ sonar })
    auth.value = 'ready'
    boardState.value = {
      ...boardState.value,
      board: board([ag('p1', 's1', { status: 'blocked', asks_user: true })]),
    }
    await nextTick()
    pulseAviso()
    await flush()
    await flush()
    expect(avisoActual.value?.id).toBe(8)
    expect(cola.map((a) => a.id)).toEqual([])
    cerrarAviso()
    await flush()
    await flush()
    expect(avisoActual.value).toBeNull()
  })

  it('un te toca que llega antes que el tablero se muestra igual', async () => {
    const sonar = vi.fn()
    getAvisos
      .mockResolvedValueOnce(page([aviso(7, 'asks')]))
      .mockResolvedValueOnce(page([aviso(8, 'asks', { session_id: 's1' })]))
    iniciarAvisosNotch({ sonar })
    auth.value = 'ready'
    boardState.value = {
      ...boardState.value,
      board: board([ag('p1', 's1', { status: 'working' })]),
    }
    await flush()
    await flush()
    pulseAviso()
    await flush()
    await flush()
    expect(avisoActual.value?.id).toBe(8)
  })

  it('se recoge recién cuando la sesión pasó por te toca', async () => {
    const sonar = vi.fn()
    getAvisos
      .mockResolvedValueOnce(page([aviso(7, 'asks')]))
      .mockResolvedValueOnce(page([aviso(8, 'asks', { session_id: 's1' })]))
    iniciarAvisosNotch({ sonar })
    auth.value = 'ready'
    boardState.value = {
      ...boardState.value,
      board: board([ag('p1', 's1', { status: 'working' })]),
    }
    await flush()
    await flush()
    pulseAviso()
    await flush()
    await flush()
    expect(avisoActual.value?.id).toBe(8)

    boardState.value = {
      ...boardState.value,
      board: board([ag('p1', 's1', { status: 'blocked', asks_user: true })]),
    }
    await nextTick()
    expect(avisoActual.value?.id).toBe(8)

    boardState.value = {
      ...boardState.value,
      board: board([ag('p1', 's1', { status: 'working' })]),
    }
    await nextTick()
    await flush()
    expect(avisoActual.value).toBeNull()
  })

  it('recoge el aviso visible si la sesión ya no te toca', async () => {
    const sonar = vi.fn()
    getAvisos
      .mockResolvedValueOnce(page([aviso(7, 'asks')]))
      .mockResolvedValueOnce(page([aviso(8, 'asks', { session_id: 's1' })]))
    iniciarAvisosNotch({ sonar })
    auth.value = 'ready'
    boardState.value = {
      ...boardState.value,
      board: board([ag('p1', 's1', { status: 'blocked', asks_user: true })]),
    }
    await flush()
    await flush()
    pulseAviso()
    await flush()
    await flush()
    expect(avisoActual.value?.session_id).toBe('s1')
    boardState.value = {
      ...boardState.value,
      board: board([ag('p1', 's1', { status: 'working' })]),
    }
    await nextTick()
    await flush()
    await flush()
    expect(avisoActual.value).toBeNull()
  })

  it('ultimo no retrocede si las respuestas de avisos llegan desordenadas', async () => {
    const sonar = vi.fn()
    getAvisos
      .mockResolvedValueOnce(page([aviso(7, 'asks')]))
      .mockResolvedValueOnce(page([aviso(10, 'done')]))
    iniciarAvisosNotch({ sonar })
    auth.value = 'ready'
    await flush()
    await flush()
    getAvisos.mockResolvedValueOnce(page([aviso(8, 'asks')]))
    pulseAviso()
    pulseAviso()
    await flush()
    await flush()
    getAvisos.mockResolvedValueOnce(page([aviso(8, 'asks')]))
    pulseAviso()
    await flush()
    await flush()
    expect(avisoActual.value?.id).toBe(10)
    expect(cola.some((a) => a.id === 8)).toBe(false)
  })

  it('si la base falla reintenta antes de mostrar avisos', async () => {
    const sonar = vi.fn()
    getAvisos
      .mockRejectedValueOnce(new Error('corte'))
      .mockResolvedValueOnce(page([aviso(7, 'asks')]))
      .mockResolvedValueOnce(page([aviso(8, 'asks', { session_id: 's8' })]))
    iniciarAvisosNotch({ sonar })
    auth.value = 'ready'
    await flush()
    await flush()
    boardState.value = {
      ...boardState.value,
      board: board([ag('p8', 's8', { status: 'blocked', asks_user: true })]),
    }
    await nextTick()
    pulseAviso()
    await flush()
    await flush()
    expect(avisoActual.value?.id).toBe(8)
    expect(getAvisos.mock.calls.length).toBeGreaterThanOrEqual(3)
  })

  it('recoge un te toca visible tras la gracia aunque nunca haya sido te toca en el tablero', async () => {
    vi.useFakeTimers({ now: NOW, shouldAdvanceTime: true })
    const sonar = vi.fn()
    getAvisos
      .mockResolvedValueOnce(page([aviso(7, 'asks')]))
      .mockResolvedValueOnce(page([aviso(8, 'asks', { session_id: 's1' })]))
    iniciarAvisosNotch({ sonar })
    auth.value = 'ready'
    boardState.value = {
      ...boardState.value,
      board: board([ag('p1', 's1', { status: 'working' })]),
    }
    await flush()
    await flush()
    pulseAviso()
    await flush()
    await flush()
    expect(avisoActual.value?.id).toBe(8)
    await vi.advanceTimersByTimeAsync(5000)
    expect(avisoActual.value).toBeNull()
    vi.useRealTimers()
  })

  it('con respuesta en edición no cierra por gracia ni al dejar de estar te toca', async () => {
    vi.useFakeTimers({ now: NOW, shouldAdvanceTime: true })
    const sonar = vi.fn()
    getAvisos
      .mockResolvedValueOnce(page([aviso(7, 'asks')]))
      .mockResolvedValueOnce(page([aviso(8, 'asks', { session_id: 's1' })]))
    iniciarAvisosNotch({ sonar })
    auth.value = 'ready'
    boardState.value = {
      ...boardState.value,
      board: board([ag('p1', 's1', { status: 'working' })]),
    }
    await flush()
    await flush()
    pulseAviso()
    await flush()
    await flush()
    expect(avisoActual.value?.id).toBe(8)

    marcarRetenerRespuestaAviso(true)
    await vi.advanceTimersByTimeAsync(5000)
    expect(avisoActual.value?.id).toBe(8)

    boardState.value = {
      ...boardState.value,
      board: board([ag('p1', 's1', { status: 'blocked', asks_user: true })]),
    }
    await nextTick()
    boardState.value = {
      ...boardState.value,
      board: board([ag('p1', 's1', { status: 'working' })]),
    }
    await nextTick()
    expect(avisoActual.value?.id).toBe(8)

    marcarRetenerRespuestaAviso(false)
    await nextTick()
    expect(avisoActual.value).toBeNull()
    vi.useRealTimers()
  })

  it('al soltar retención con sesión ya fuera de te toca cierra el aviso', async () => {
    const sonar = vi.fn()
    getAvisos
      .mockResolvedValueOnce(page([aviso(7, 'asks')]))
      .mockResolvedValueOnce(page([aviso(8, 'asks', { session_id: 's1' })]))
    iniciarAvisosNotch({ sonar })
    auth.value = 'ready'
    boardState.value = {
      ...boardState.value,
      board: board([ag('p1', 's1', { status: 'blocked', asks_user: true })]),
    }
    await flush()
    await flush()
    pulseAviso()
    await flush()
    await flush()
    marcarRetenerRespuestaAviso(true)
    boardState.value = {
      ...boardState.value,
      board: board([ag('p1', 's1', { status: 'working' })]),
    }
    await nextTick()
    expect(avisoActual.value?.id).toBe(8)
    marcarRetenerRespuestaAviso(false)
    await nextTick()
    expect(avisoActual.value).toBeNull()
  })

  it('un te-toca de la misma sesión reemplaza un done visible al instante', async () => {
    const sonar = vi.fn()
    const puenteAviso = vi.fn()
    setPuente({ enPrograma: true, tamano: vi.fn(), forma: vi.fn(), arrastrar: vi.fn(), abrirColmena: vi.fn(), abrirBiblioteca: vi.fn(), aviso: puenteAviso, mostrarReunion: vi.fn() })
    getAvisos
      .mockResolvedValueOnce(page([aviso(7, 'asks')]))
      .mockResolvedValueOnce(page([aviso(8, 'done', { session_id: 's1' })]))
      .mockResolvedValueOnce(page([aviso(9, 'asks', { session_id: 's1' })]))
    iniciarAvisosNotch({ sonar })
    auth.value = 'ready'
    await flush()
    await flush()
    puenteAviso.mockClear()
    pulseAviso()
    await flush()
    await flush()
    expect(avisoActual.value?.id).toBe(8)
    expect(avisoActual.value?.kind).toBe('done')

    boardState.value = {
      ...boardState.value,
      board: board([ag('p1', 's1', { status: 'blocked', asks_user: true })]),
    }
    await nextTick()
    pulseAviso()
    await flush()
    await flush()
    expect(avisoActual.value?.id).toBe(9)
    expect(avisoActual.value?.kind).toBe('asks')
    expect(puenteAviso).toHaveBeenCalledWith('te-toca')
    expect(cola.some((a) => a.id === 8)).toBe(false)
  })

  it('un te-toca de otra sesión no reemplaza un done visible', async () => {
    const sonar = vi.fn()
    getAvisos
      .mockResolvedValueOnce(page([aviso(7, 'asks')]))
      .mockResolvedValueOnce(page([aviso(8, 'done', { session_id: 's1' })]))
      .mockResolvedValueOnce(page([aviso(9, 'asks', { session_id: 's2' })]))
    iniciarAvisosNotch({ sonar })
    auth.value = 'ready'
    await flush()
    await flush()
    pulseAviso()
    await flush()
    await flush()
    expect(avisoActual.value?.id).toBe(8)

    boardState.value = {
      ...boardState.value,
      board: board([ag('p2', 's2', { status: 'blocked', asks_user: true })]),
    }
    await nextTick()
    pulseAviso()
    await flush()
    await flush()
    expect(avisoActual.value?.id).toBe(8)
    expect(cola.map((a) => a.id)).toEqual([9])
  })

  it('cerrar un aviso no marca nada como leído', async () => {
    const sonar = vi.fn()
    getAvisos
      .mockResolvedValueOnce(page([aviso(7, 'asks')]))
      .mockResolvedValueOnce(page([aviso(8, 'done')]))
    iniciarAvisosNotch({ sonar })
    auth.value = 'ready'
    await flush()
    await flush()
    pulseAviso()
    await flush()
    await flush()
    cerrarAviso()
    await flush()
    expect(marcarAvisosLeidos).not.toHaveBeenCalled()
    expect(marcarAvisosDe).not.toHaveBeenCalled()
  })

  it('con notas abierta un aviso no tapa la captura y sale al cerrarla', async () => {
    getAvisos
      .mockResolvedValueOnce(page([]))
      .mockResolvedValueOnce(page([aviso(8, 'blocked')]))
    iniciarAvisosNotch({ sonar: vi.fn() })
    auth.value = 'ready'
    await flush()
    await flush()
    modo.value = 'notas'
    pulseAviso()
    await flush()
    await flush()
    expect(modo.value).toBe('notas')
    expect(avisoActual.value).toBeNull()
    expect(cola.map((a) => a.id)).toEqual([8])
    modo.value = 'cerrado'
    await nextTick()
    await flush()
    expect(avisoActual.value?.id).toBe(8)
    expect(modo.value).toBe('aviso')
  })

  it('cerrar un aviso con notas abierta no cierra la captura', () => {
    modo.value = 'notas'
    cerrarAviso()
    expect(modo.value).toBe('notas')
  })

  it('abrir notas sobre un aviso visible lo deja en pausa y vuelve al cerrarla', async () => {
    getAvisos
      .mockResolvedValueOnce(page([]))
      .mockResolvedValueOnce(page([aviso(9, 'asks')]))
    iniciarAvisosNotch({ sonar: vi.fn() })
    auth.value = 'ready'
    await flush()
    await flush()
    pulseAviso()
    await flush()
    await flush()
    expect(modo.value).toBe('aviso')
    modo.value = 'notas'
    await nextTick()
    modo.value = 'cerrado'
    await nextTick()
    await flush()
    expect(modo.value).toBe('aviso')
    expect(avisoActual.value?.id).toBe(9)
  })

  it('un pedido de pestaña que se actualiza con notas abierta no tapa la captura', async () => {
    const { pedidosPestana } = await import('./pedidosPestana')
    const { pedidoPestanaEvent } = await import('./app')
    pedidosPestana.items = [
      { id: 'pp1', carpeta: '/x', mensaje: 'm', origen: { pane_id: 'w:p', nombre: 'n' }, ts: 1, vence: Date.now() / 1000 + 600 },
    ] as typeof pedidosPestana.items
    iniciarAvisosNotch({ sonar: vi.fn() })
    const pedido: AvisoNotch = { id: 50, kind: 'pestana', titulo: 't', cuerpo: 'c', session_id: 's1', pedido: 'pp1' } as AvisoNotch
    avisoActual.value = pedido
    modo.value = 'notas'
    pedidoPestanaEvent.value = { id: 'pp1', estado: 'pendiente', n: 1 } as typeof pedidoPestanaEvent.value
    await nextTick()
    await flush()
    expect(modo.value).toBe('notas')
    modo.value = 'cerrado'
    await nextTick()
    await flush()
    expect(modo.value).toBe('aviso')
    expect(avisoActual.value?.id).toBe(50)
    pedidosPestana.items = []
  })
})
