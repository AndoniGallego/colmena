import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, type Api, type PedidoPestana } from '../api/types'

vi.hoisted(() => {
  vi.stubGlobal('window', { matchMedia: () => ({ matches: false, addEventListener() {} }), addEventListener() {} })
  vi.stubGlobal('location', { search: '', pathname: '/' })
})

vi.mock('./terminales', () => ({
  openTerminal: vi.fn(),
  closeTerminal: vi.fn(),
  openTerminalId: { value: null },
}))

const pedido = (id: string, over: Partial<PedidoPestana> = {}): PedidoPestana => ({
  id,
  carpeta: '/proyecto/foo',
  mensaje: 'Hola',
  origen: { pane_id: 'w1:p1', nombre: 'Sesión A', session_id: '' },
  ts: 1_800_000_000,
  vence: 1_800_000_600,
  ...over,
})

async function mockApi(over: Partial<Api>) {
  const { init } = await import('./app')
  init({
    getPedidosPestana: vi.fn(async () => []),
    abrirPedidoPestana: vi.fn(),
    rechazarPedidoPestana: vi.fn(),
    ...over,
  } as unknown as Api)
}

const {
  _resetPedidosPestana,
  cargarVistaCierre,
  abrirPedidoPestana,
  aplicarPedidoPestanaSse,
  initPedidosPestana,
  pedidosDeSesion,
  pedidosPestana,
  rechazarPedidoPestana,
  refrescarPedidosPestana,
} = await import('./pedidosPestana')

beforeEach(() => {
  _resetPedidosPestana()
})

describe('state/pedidosPestana', () => {
  it('carga pendientes al arrancar', async () => {
    await mockApi({ getPedidosPestana: vi.fn(async () => [pedido('a'), pedido('b')]) })
    initPedidosPestana()
    const { auth } = await import('./app')
    auth.value = 'ready'
    await nextTick()
    await vi.waitFor(() => expect(pedidosPestana.items).toHaveLength(2))
  })

  it('sse no pendiente saca de la lista', () => {
    pedidosPestana.items = [pedido('a'), pedido('b')]
    aplicarPedidoPestanaSse('a', 'rechazado')
    expect(pedidosPestana.items.map((p) => p.id)).toEqual(['b'])
    aplicarPedidoPestanaSse('b', 'pendiente')
    expect(pedidosPestana.items.map((p) => p.id)).toEqual(['b'])
  })

  it('abrir llama API y maneja 404/409/429', async () => {
    await mockApi({
      abrirPedidoPestana: vi
        .fn()
        .mockRejectedValueOnce(new ApiError(404, 'x'))
        .mockRejectedValueOnce(new ApiError(409, 'x'))
        .mockRejectedValueOnce(new ApiError(429, 'x')),
    })
    pedidosPestana.items = [pedido('a')]
    await abrirPedidoPestana('a')
    expect(pedidosPestana.porId.a?.error).toBe('Ya no está disponible')
    await abrirPedidoPestana('a')
    expect(pedidosPestana.porId.a?.error).toBe('Ya se decidió')
    await abrirPedidoPestana('a')
    expect(pedidosPestana.porId.a?.error).toBe('Llegaste al tope de pestañas por hora')
  })

  it('abrir con pegado:false deja aviso', async () => {
    await mockApi({
      abrirPedidoPestana: vi.fn(async () => ({ ok: true as const, pane_id: 'g2:p3', pegado: false })),
    })
    pedidosPestana.items = [pedido('a')]
    await abrirPedidoPestana('a')
    expect(pedidosPestana.porId.a?.error).toBe('Se abrió, pero no pude pegar el mensaje')
    expect(pedidosPestana.porId.a?.pane_id).toBe('g2:p3')
  })

  it('rechazar llama a la API', async () => {
    const rechazar = vi.fn(async () => ({ ok: true as const }))
    await mockApi({ rechazarPedidoPestana: rechazar })
    pedidosPestana.items = [pedido('a')]
    await rechazarPedidoPestana('a')
    expect(rechazar).toHaveBeenCalledWith('a')
  })

  it('sse abierto durante el envío no quita la tarjeta hasta que termina la respuesta', async () => {
    let resolver!: (v: { ok: true; pane_id: string }) => void
    await mockApi({
      abrirPedidoPestana: vi.fn(
        () => new Promise<{ ok: true; pane_id: string }>((res) => {
          resolver = res
        }),
      ),
    })
    pedidosPestana.items = [pedido('a'), pedido('b')]
    const enCurso = abrirPedidoPestana('a')
    aplicarPedidoPestanaSse('a', 'abierto')
    expect(pedidosPestana.items.map((p) => p.id)).toEqual(['a', 'b'])
    resolver({ ok: true, pane_id: 'g1:p1' })
    await enCurso
    expect(pedidosPestana.items.map((p) => p.id)).toEqual(['b'])
  })

  it('sse abierto durante el envío quita la tarjeta aunque la respuesta falle', async () => {
    let rechazar!: (e: unknown) => void
    await mockApi({
      abrirPedidoPestana: vi.fn(
        () => new Promise<{ ok: true; pane_id: string }>((_, rej) => {
          rechazar = rej
        }),
      ),
    })
    pedidosPestana.items = [pedido('a')]
    const enCurso = abrirPedidoPestana('a')
    aplicarPedidoPestanaSse('a', 'abierto')
    expect(pedidosPestana.items.map((p) => p.id)).toEqual(['a'])
    rechazar(new ApiError(502, 'x'))
    await enCurso
    expect(pedidosPestana.items).toEqual([])
  })

  it('refrescar durante el envío conserva la tarjeta que se está abriendo', async () => {
    let resolver!: (v: { ok: true; pane_id: string }) => void
    await mockApi({
      getPedidosPestana: vi.fn(async () => [pedido('b')]),
      abrirPedidoPestana: vi.fn(
        () => new Promise<{ ok: true; pane_id: string }>((res) => {
          resolver = res
        }),
      ),
    })
    const { auth } = await import('./app')
    auth.value = 'ready'
    pedidosPestana.items = [pedido('a'), pedido('b')]
    const enCurso = abrirPedidoPestana('a')
    await refrescarPedidosPestana()
    expect(pedidosPestana.items.map((p) => p.id).sort()).toEqual(['a', 'b'])
    resolver({ ok: true, pane_id: 'g1:p1' })
    await enCurso
    expect(pedidosPestana.items.map((p) => p.id)).toEqual(['b'])
  })
})

describe('state/pedidosPestana: pedido para cerrar una terminal', () => {
  const cerrar = (id: string) =>
    pedido(id, {
      carpeta: '',
      mensaje: '',
      accion: 'cerrar',
      terminal: { pane_id: 'w2:p1', titulo: 'logs', cwd: '~/tmp', proceso: '', estado: 'prompt', donde: '' },
    })

  it('al aprobar no abre el visor y avisa que se cerró', async () => {
    const { openTerminal } = await import('./terminales')
    vi.mocked(openTerminal).mockClear()
    await mockApi({ abrirPedidoPestana: vi.fn(async () => ({ ok: true as const, pane_id: 'w2:p1', cerrada: true })) })
    pedidosPestana.items = [cerrar('a')]
    await abrirPedidoPestana('a')
    expect(pedidosPestana.listoTxt).toBe('Terminal cerrada')
    expect(openTerminal).not.toHaveBeenCalled()
    expect(pedidosPestana.items).toEqual([])
  })

  it('si la terminal cambió la tarjeta queda con el motivo', async () => {
    await mockApi({ abrirPedidoPestana: vi.fn().mockRejectedValue(new ApiError(409, 'la terminal cambió, revisala de nuevo')) })
    pedidosPestana.items = [cerrar('a')]
    await abrirPedidoPestana('a')
    expect(pedidosPestana.porId.a?.error).toBe('La terminal cambió. Revisala de nuevo')
    expect(pedidosPestana.items.map((p) => p.id)).toEqual(['a'])
  })

  it('si ahora es otra terminal, avisa que se descartó y la tarjeta se va', async () => {
    await mockApi({ abrirPedidoPestana: vi.fn().mockRejectedValue(new ApiError(409, 'ya es otra terminal: descarté el pedido')) })
    pedidosPestana.items = [cerrar('a')]
    await abrirPedidoPestana('a')
    expect(pedidosPestana.porId.a?.error).toBe('Ahora es otra terminal: descarté el pedido')
    expect(pedidosPestana.items).toEqual([])
  })

  it('si se movió o cambió de carpeta, la tarjeta queda con el motivo', async () => {
    await mockApi({
      abrirPedidoPestana: vi.fn().mockRejectedValue(new ApiError(409, 'la terminal se movió o cambió de carpeta desde el pedido')),
    })
    pedidosPestana.items = [cerrar('a')]
    await abrirPedidoPestana('a')
    expect(pedidosPestana.porId.a?.error).toBe('La terminal se movió o cambió de carpeta desde el pedido. Revisala antes de cerrarla')
    expect(pedidosPestana.items.map((p) => p.id)).toEqual(['a'])
  })

  it('si falló al cerrar y se descartó, la tarjeta se va con el motivo', async () => {
    await mockApi({ abrirPedidoPestana: vi.fn().mockRejectedValue(new ApiError(502, 'no pude cerrar la terminal: descarté el pedido')) })
    pedidosPestana.items = [cerrar('a')]
    await abrirPedidoPestana('a')
    expect(pedidosPestana.porId.a?.error).toBe('No pude cerrar la terminal: descarté el pedido')
    expect(pedidosPestana.items).toEqual([])
  })

  it('si la terminal ya no está, la tarjeta se va', async () => {
    await mockApi({ abrirPedidoPestana: vi.fn().mockRejectedValue(new ApiError(404, 'la terminal ya no está')) })
    pedidosPestana.items = [cerrar('a')]
    await abrirPedidoPestana('a')
    expect(pedidosPestana.porId.a?.error).toBe('La terminal ya no está')
    expect(pedidosPestana.items).toEqual([])
  })
})

describe('state/pedidosPestana: cierre de sesiones y Cerrar igual', () => {
  const A = 'a', B = 'b', C = 'c', D = 'd'
  const ped = (o: { id: string; ts: number; sid: string }, cierre = true) =>
    pedido(o.id, {
      ts: o.ts,
      origen: { pane_id: 'w1:p1', nombre: 'X', session_id: o.sid },
      ...(cierre
        ? {
            carpeta: '',
            mensaje: '',
            accion: 'cerrar' as const,
            cierre: { objetivo: 'sesion', tipo: 'tab', target_id: 't1', label: 'S', workspace_label: 'W', carpeta: '/p', sesiones: 1, terminales: 0 },
          }
        : {}),
    }) as PedidoPestana
  const vista = (trabajando: boolean, huella: string) => ({ trabajando, estados: [], huella })

  it('pedidosDeSesion filtra por session_id y ordena del más viejo', () => {
    pedidosPestana.items = [ped({ id: A, ts: 20, sid: 's1' }), ped({ id: B, ts: 10, sid: 's1' }), ped({ id: C, ts: 5, sid: 's2' }), ped({ id: D, ts: 1, sid: '' })]
    expect(pedidosDeSesion('s1').map((p) => p.id)).toEqual([B, A])
    expect(pedidosDeSesion('')).toEqual([])
    expect(pedidosDeSesion(null)).toEqual([])
  })

  it('un pedido de cierre manda forzar solo si la vista dijo trabajando', async () => {
    const abrir = vi.fn(async () => ({ ok: true as const, pane_id: '', cerrada: true }))
    await mockApi({ abrirPedidoPestana: abrir })
    pedidosPestana.items = [ped({ id: A, ts: 1, sid: 's' })]
    pedidosPestana.porId = { [A]: { vista: vista(false, 'h0') } }
    await abrirPedidoPestana(A)
    expect(abrir).toHaveBeenLastCalledWith(A, { huella: 'h0', forzar: false })
    expect(pedidosPestana.listoTxt).toBe('Cerrado')
    pedidosPestana.items = [ped({ id: A, ts: 1, sid: 's' })]
    pedidosPestana.porId = { [A]: { vista: vista(true, 'h1') } }
    await abrirPedidoPestana(A)
    expect(abrir).toHaveBeenLastCalledWith(A, { huella: 'h1', forzar: true })
  })

  it('sin vista no aprueba: primero la carga para que se vea qué se cierra', async () => {
    const abrir = vi.fn(async () => ({ ok: true as const, pane_id: '', cerrada: true }))
    const vistaFn = vi.fn(async () => vista(false, 'h5'))
    await mockApi({ abrirPedidoPestana: abrir, vistaCierrePedido: vistaFn })
    pedidosPestana.items = [ped({ id: A, ts: 1, sid: 's' })]
    pedidosPestana.porId = {}
    await abrirPedidoPestana(A)
    expect(abrir).not.toHaveBeenCalled()
    expect(vistaFn).toHaveBeenCalledWith(A)
    expect(pedidosPestana.porId[A]?.vista).toEqual(vista(false, 'h5'))
    expect(pedidosPestana.items.map((p) => p.id)).toEqual([A])
  })

  it('guardando avisa y no navega a un panel vacío', async () => {
    const { openTerminal } = await import('./terminales')
    vi.mocked(openTerminal).mockClear()
    await mockApi({ abrirPedidoPestana: vi.fn(async () => ({ ok: true as const, pane_id: '', guardando: true })) })
    pedidosPestana.items = [ped({ id: A, ts: 1, sid: 's' })]
    pedidosPestana.porId = { [A]: { vista: vista(false, 'h0') } }
    await abrirPedidoPestana(A)
    expect(pedidosPestana.listoTxt).toBe('Guardando y cerrando')
    expect(openTerminal).not.toHaveBeenCalled()
    expect(pedidosPestana.items).toEqual([])
  })

  it('un 409 con bloqueantes deja la tarjeta y recarga la vista', async () => {
    const vistaFn = vi.fn(async () => vista(true, 'h2'))
    await mockApi({
      abrirPedidoPestana: vi.fn().mockRejectedValue(new ApiError(409, 'Está trabajando: revisalo', null, [{ pane_id: 'w2:p9', status: 'working' }])),
      vistaCierrePedido: vistaFn,
    })
    pedidosPestana.items = [ped({ id: A, ts: 1, sid: 's' })]
    pedidosPestana.porId = { [A]: { vista: vista(false, 'h0') } }
    await abrirPedidoPestana(A)
    expect(pedidosPestana.items.map((p) => p.id)).toEqual([A])
    expect(pedidosPestana.porId[A]?.error ?? '').toBe('')
    expect(vistaFn).toHaveBeenCalledWith(A)
    expect(pedidosPestana.porId[A]?.vista).toEqual(vista(true, 'h2'))
  })

  it('resolver por SSE lo saca de pedidosDeSesion', () => {
    pedidosPestana.items = [ped({ id: A, ts: 1, sid: 's1' })]
    aplicarPedidoPestanaSse(A, 'abierto')
    expect(pedidosDeSesion('s1')).toEqual([])
  })

  it('cargarVistaCierre quita el pedido si el servidor dice 404', async () => {
    await mockApi({ vistaCierrePedido: vi.fn().mockRejectedValue(new ApiError(404, 'x')) })
    pedidosPestana.items = [ped({ id: A, ts: 1, sid: 's' })]
    await cargarVistaCierre(A)
    expect(pedidosPestana.items).toEqual([])
  })

  it('al refrescar carga la vista de los pedidos de cierre nuevos', async () => {
    const vistaFn = vi.fn(async () => vista(false, 'h'))
    await mockApi({ getPedidosPestana: vi.fn(async () => [ped({ id: A, ts: 1, sid: 's' }), ped({ id: B, ts: 2, sid: 's' }, false)]), vistaCierrePedido: vistaFn })
    const { auth } = await import('./app')
    auth.value = 'ready'
    await refrescarPedidosPestana()
    await vi.waitFor(() => expect(pedidosPestana.porId[A]?.vista).toBeTruthy())
    expect(vistaFn).toHaveBeenCalledTimes(1)
    expect(vistaFn).toHaveBeenCalledWith(A)
  })

  it('recarga la vista cuando cambia el tablero, con debounce', async () => {
    vi.useFakeTimers()
    try {
      const vistaFn = vi.fn(async () => vista(true, 'h9'))
      await mockApi({ vistaCierrePedido: vistaFn })
      const { boardState, auth } = await import('./app')
      auth.value = 'checking'
      initPedidosPestana()
      pedidosPestana.items = [ped({ id: A, ts: 1, sid: 's' }), ped({ id: B, ts: 2, sid: 's' })]
      pedidosPestana.porId = { [A]: { vista: vista(true, 'h1') }, [B]: { vista: vista(false, 'h0') } }
      boardState.value = { ...boardState.value, board: { workspaces: [] } as never }
      await nextTick()
      boardState.value = { ...boardState.value, board: { workspaces: [] } as never }
      await nextTick()
      await vi.advanceTimersByTimeAsync(1000)
      // Todas las vistas de cierre se refrescan: la huella que se aprueba tiene que ser la que se ve ahora.
      expect(vistaFn).toHaveBeenCalledTimes(2)
      expect(vistaFn).toHaveBeenCalledWith(A)
      expect(vistaFn).toHaveBeenCalledWith(B)
    } finally {
      vi.useRealTimers()
    }
  })
  it('cargarVistaCierre no quita el pedido si el servidor dice 409: sigue pendiente', async () => {
    await mockApi({ vistaCierrePedido: vi.fn().mockRejectedValue(new ApiError(409, 'No pude ver todos sus paneles')) })
    pedidosPestana.items = [ped({ id: A, ts: 1, sid: 's' })]
    await cargarVistaCierre(A)
    expect(pedidosPestana.items.map((p) => p.id)).toEqual([A])
  })

  it('cargarVistaCierre no quita el pedido con 404 mientras se está enviando', async () => {
    await mockApi({ vistaCierrePedido: vi.fn().mockRejectedValue(new ApiError(404, 'x')) })
    pedidosPestana.items = [ped({ id: A, ts: 1, sid: 's' })]
    pedidosPestana.porId = { [A]: { enviando: true } }
    await cargarVistaCierre(A)
    expect(pedidosPestana.items.map((p) => p.id)).toEqual([A])
  })

  it('pedidosDeSesion no devuelve pedidos vencidos', () => {
    const ahora = Math.floor(Date.now() / 1000)
    pedidosPestana.items = [
      { ...ped({ id: A, ts: ahora - 700, sid: 's1' }), vence: ahora - 100 },
      { ...ped({ id: B, ts: ahora - 10, sid: 's1' }), vence: ahora + 590 },
    ]
    expect(pedidosDeSesion('s1').map((p) => p.id)).toEqual([B])
  })

  it('una vista vieja que llega tarde no pisa a la nueva', async () => {
    const res: Array<(v: ReturnType<typeof vista>) => void> = []
    await mockApi({ vistaCierrePedido: vi.fn(() => new Promise<ReturnType<typeof vista>>((r) => res.push(r))) })
    pedidosPestana.items = [ped({ id: A, ts: 1, sid: 's' })]
    const vieja = cargarVistaCierre(A)
    const nueva = cargarVistaCierre(A)
    res[1](vista(true, 'nueva'))
    await nueva
    res[0](vista(false, 'vieja'))
    await vieja
    expect(pedidosPestana.porId[A]?.vista?.huella).toBe('nueva')
  })

  it('si el pedido ya no está al volver la vista, no la guarda', async () => {
    let res!: (v: ReturnType<typeof vista>) => void
    await mockApi({ vistaCierrePedido: vi.fn(() => new Promise<ReturnType<typeof vista>>((r) => { res = r })) })
    pedidosPestana.items = [ped({ id: A, ts: 1, sid: 's' })]
    const carga = cargarVistaCierre(A)
    aplicarPedidoPestanaSse(A, 'abierto')
    res(vista(true, 'h'))
    await carga
    expect(pedidosPestana.porId[A]).toBeUndefined()
  })

  it('el error de un cierre de sesión no habla de terminales', async () => {
    await mockApi({ abrirPedidoPestana: vi.fn().mockRejectedValue(new ApiError(404, '')) })
    pedidosPestana.items = [ped({ id: A, ts: 1, sid: 's' })]
    pedidosPestana.porId = { ...pedidosPestana.porId, [A]: { vista: vista(false, 'h0') } }
    await abrirPedidoPestana(A)
    expect(pedidosPestana.porId[A]?.error).toBe('Ya no está: descarté el pedido')
    expect(pedidosPestana.items).toEqual([])

    await mockApi({ abrirPedidoPestana: vi.fn().mockRejectedValue(new ApiError(502, '')) })
    pedidosPestana.items = [ped({ id: B, ts: 1, sid: 's' })]
    pedidosPestana.porId = { ...pedidosPestana.porId, [B]: { vista: vista(false, 'h0') } }
    await abrirPedidoPestana(B)
    expect(pedidosPestana.porId[B]?.error).toBe('No pude cerrarlo')
    expect(pedidosPestana.items.map((p) => p.id)).toEqual([B])

    await mockApi({ abrirPedidoPestana: vi.fn().mockRejectedValue(new ApiError(502, 'No pude cerrar la pestaña: descarté el pedido')) })
    pedidosPestana.items = [ped({ id: C, ts: 1, sid: 's' })]
    pedidosPestana.porId = { ...pedidosPestana.porId, [C]: { vista: vista(false, 'h0') } }
    await abrirPedidoPestana(C)
    expect(pedidosPestana.porId[C]?.error).toBe('No pude cerrar la pestaña: descarté el pedido')
    expect(pedidosPestana.items).toEqual([])
  })

  it('el debounce del tablero no dispara antes de 1000 ms', async () => {
    vi.useFakeTimers()
    try {
      const vistaFn = vi.fn(async () => vista(true, 'h9'))
      await mockApi({ vistaCierrePedido: vistaFn })
      const { boardState, auth } = await import('./app')
      auth.value = 'checking'
      initPedidosPestana()
      pedidosPestana.items = [ped({ id: A, ts: 1, sid: 's' })]
      pedidosPestana.porId = { [A]: { vista: vista(true, 'h1') } }
      boardState.value = { ...boardState.value, board: { workspaces: [] } as never }
      await nextTick()
      await vi.advanceTimersByTimeAsync(999)
      expect(vistaFn).not.toHaveBeenCalled()
      await vi.advanceTimersByTimeAsync(1)
      expect(vistaFn).toHaveBeenCalledTimes(1)
    } finally {
      vi.useRealTimers()
    }
  })
})
