import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, type Api } from '../api/types'
import { normalizeDialog } from '../lib/dialogo'
import type { SesionNotch } from '../lib/notchCeldas'

vi.hoisted(() => {
  vi.stubGlobal('window', { matchMedia: () => ({ matches: false, addEventListener() {} }), addEventListener() {} })
  vi.stubGlobal('location', { search: '', pathname: '/notch' })
})

vi.mock('../motion', () => ({ haptic: vi.fn() }))

const api = vi.hoisted(() => ({
  getDialog: vi.fn(),
  answerDialog: vi.fn(),
  decidirPermiso: vi.fn(),
  getPregunta: vi.fn(),
  responderPregunta: vi.fn(),
}))

const { init } = await import('./app')
const { enviadas } = await import('./notch')
const { activa, activar, elegirOpcion, filas, formaDe, mandarTexto, recargar, resolverPedido, resolverPermiso } = await import('./notchRespuesta')
const { dlg, resetDialog } = await import('./dialogo')
const { pedidosPestana, _resetPedidosPestana } = await import('./pedidosPestana')
const apiPedidos = vi.hoisted(() => ({ abrirPedidoPestana: vi.fn(), rechazarPedidoPestana: vi.fn() }))

function sesion(sid: string): SesionNotch {
  return {
    pane_id: sid + ':p',
    session_id: sid,
    titulo: 't',
    donde: 'Acme · 1',
    estado: 'te-toca',
    motivo: 'pregunta',
    preguntas: 0,
    desdeMs: null,
    linea: 'Te toca',
    last_activity: null,
    hue: 120,
  }
}

function fakeApi(over: Partial<Api> = {}): Api {
  return {
    getDialog: api.getDialog,
    answerDialog: api.answerDialog,
    decidirPermiso: api.decidirPermiso,
    getPregunta: api.getPregunta,
    responderPregunta: api.responderPregunta,
    ...over,
  } as unknown as Api
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.useRealTimers()
  for (const k of Object.keys(filas)) delete filas[k]
  enviadas.clear()
  resetDialog(null)
})

describe('notchRespuesta sin bandeja', () => {
  it('activar usa el diálogo aunque haya un lote de bandeja para esa sesión', async () => {
    api.getDialog.mockResolvedValue(null)
    init(fakeApi({ getBandeja: async () => ({ lotes: [{ session_id: 'a', preguntas: [] }] }) } as unknown as Partial<Api>))
    activar('a')
    expect(api.getDialog).toHaveBeenCalled()
  })

  it('state/notch y notchRespuesta no importan bandeja', () => {
    for (const f of ['./notch.ts', './notchRespuesta.ts'])
      expect(readFileSync(new URL(f, import.meta.url).pathname, 'utf8')).not.toMatch(/['"]\.\/bandeja['"]/)
  })
})

describe('notchRespuesta envío', () => {
  it('409 del diálogo deja la fila en cambio', async () => {
    const view = normalizeDialog({
      tipo: 'pregunta',
      huella: 'h1',
      pane_id: 'p1',
      pregunta: {
        preguntas: [
          {
            header: '',
            texto: '¿Seguimos?',
            multi: false,
            otro: false,
            opciones: [{ label: 'Sí' }, { label: 'No' }],
          },
        ],
      },
    })
    api.getDialog.mockResolvedValue(view)
    api.answerDialog.mockRejectedValue(new ApiError(409, 'El diálogo cambió'))
    init(fakeApi())
    activa.value = 's1'
    dlg.sessionId = 's1'
    dlg.view = view
    dlg.phase = 'idle'
    dlg.loading = false
    await elegirOpcion(sesion('s1'), 1)
    expect(filas.s1.fase).toBe('cambio')
    expect(api.answerDialog).toHaveBeenCalledTimes(1)
  })

  it('permitir un permiso de la terminal manda "si"', async () => {
    const view = normalizeDialog({
      tipo: 'permiso',
      huella: 'h1',
      pane_id: 'p1',
      permiso: {
        herramienta: 'Bash',
        detalle: 'ls',
        descripcion: '',
        completo: true,
        opciones: ['si', 'si_siempre', 'no'],
        regla: 'ls *',
        mas_en_terminal: false,
      },
    })
    api.getDialog.mockResolvedValue(view)
    api.answerDialog.mockResolvedValue({ ok: true, interrumpida: false })
    init(fakeApi())
    activar('s1')
    dlg.sessionId = 's1'
    dlg.view = view
    dlg.phase = 'idle'
    await resolverPermiso(sesion('s1'), 'permitir')
    expect(api.answerDialog).toHaveBeenCalledWith(expect.objectContaining({ permiso: 'si' }))
  })

  it('si el diálogo no está listo la fila vuelve a idle sin quedar en enviando', async () => {
    const view = normalizeDialog({
      tipo: 'pregunta',
      huella: 'h1',
      pane_id: 'p1',
      pregunta: {
        preguntas: [
          {
            header: '',
            texto: '¿Seguimos?',
            multi: false,
            otro: false,
            opciones: [{ label: 'Sí' }, { label: 'No' }],
          },
        ],
      },
    })
    init(fakeApi())
    activa.value = 's1'
    dlg.sessionId = 's1'
    dlg.view = view
    dlg.phase = 'sending'
    await elegirOpcion(sesion('s1'), 0)
    expect(filas.s1).toEqual({ fase: 'idle' })
    expect(api.answerDialog).not.toHaveBeenCalled()
  })

  it('rechazar un pedido por gancho usa decidirPermiso', async () => {
    const pedido = {
      id: 'p1',
      session_id: 's1',
      pane_id: 'w1:p1',
      herramienta: 'Bash',
      entrada: { command: 'ls' },
      estado: 'abierto' as const,
      regla: { herramienta: 'Bash', contenido: 'ls:*', archivo: '/x.json', huella: 'h' },
    }
    const view = { tipo: 'pedido' as const, pedido }
    api.getDialog.mockResolvedValue(view)
    api.decidirPermiso.mockResolvedValue({ ...pedido, estado: 'rechazado' as const })
    init(fakeApi())
    activar('s1')
    dlg.sessionId = 's1'
    dlg.view = view
    dlg.phase = 'idle'
    await resolverPermiso(sesion('s1'), 'rechazar')
    expect(api.decidirPermiso).toHaveBeenCalledWith('p1', { accion: 'rechazar' })
  })
})

describe('notchRespuesta con pregunta de sesión', () => {
  const op = (label: string) => ({ label, detalle: '', recomendada: false })
  const pregunta = (sig = 's1:a', n = 1) => ({
    sig,
    session_id: 's1',
    pane_id: 'w1:p1',
    nombre: 'Uno',
    preguntas: Array.from({ length: n }, () => ({ pregunta: '¿Cómo seguimos?', opciones: [op('Sí'), op('No')] })),
  })
  const conTarjetas = (n = 1): SesionNotch => ({ ...sesion('s1'), preguntas: n })

  async function cargar(n = 1, sig = 's1:a') {
    api.getPregunta.mockResolvedValue(pregunta(sig, n))
    init(fakeApi())
    activar('s1', conTarjetas(n))
    await vi.waitFor(() => expect(formaDe(conTarjetas(n)).tipo).not.toBe('cargando'))
  }

  it('activar carga la pregunta de la sesión y no el diálogo', async () => {
    await cargar()
    expect(api.getPregunta).toHaveBeenCalledWith('s1')
    expect(api.getDialog).not.toHaveBeenCalled()
    expect(formaDe(conTarjetas())).toMatchObject({ tipo: 'opciones', opciones: ['Sí', 'No'], via: 'sesion' })
  })

  it('con varias preguntas la forma es abrir', async () => {
    await cargar(2)
    expect(formaDe(conTarjetas(2))).toEqual({ tipo: 'abrir', motivo: 'Tiene 2 preguntas' })
  })

  it('elegir una opción manda "<n>. <label>" con la firma cargada', async () => {
    await cargar()
    api.responderPregunta.mockResolvedValue({ ok: true })
    await elegirOpcion(conTarjetas(), 1)
    expect(api.responderPregunta).toHaveBeenCalledWith('s1', { id: expect.any(String), sig: 's1:a', texto: '2. No' })
    expect(filas.s1.fase).toBe('enviado')
    expect(api.answerDialog).not.toHaveBeenCalled()
  })

  it('el texto libre manda el texto tal cual', async () => {
    await cargar()
    api.responderPregunta.mockResolvedValue({ ok: true })
    await mandarTexto(conTarjetas(), 'otra cosa')
    expect(api.responderPregunta).toHaveBeenCalledWith('s1', { id: expect.any(String), sig: 's1:a', texto: 'otra cosa' })
    expect(filas.s1.fase).toBe('enviado')
  })

  it('un 409 YA_CONTESTADA muestra "La pregunta cambió" y recarga la pregunta', async () => {
    await cargar()
    api.responderPregunta.mockRejectedValue(new ApiError(409, 'YA_CONTESTADA'))
    api.getPregunta.mockResolvedValue(pregunta('s1:a'))
    await elegirOpcion(conTarjetas(), 0)
    expect(filas.s1).toEqual({ fase: 'cambio', mensaje: 'La pregunta cambió' })
    expect(api.getPregunta).toHaveBeenCalledTimes(2)
  })

  it('un 409 de id ya enviado muestra "Ya se mandó" sin recargar', async () => {
    await cargar()
    api.responderPregunta.mockRejectedValue(new ApiError(409, 'Ya se mandó ese mensaje'))
    await elegirOpcion(conTarjetas(), 0)
    expect(filas.s1).toEqual({ fase: 'cambio', mensaje: 'Ya se mandó' })
    expect(api.getPregunta).toHaveBeenCalledTimes(1)
  })

  it('reintentar la misma respuesta reusa el id', async () => {
    await cargar()
    api.responderPregunta.mockRejectedValueOnce(new ApiError(502, 'la terminal falló')).mockResolvedValue({ ok: true })
    await elegirOpcion(conTarjetas(), 0)
    filas.s1 = { fase: 'idle' }
    await elegirOpcion(conTarjetas(), 0)
    const [a, b] = api.responderPregunta.mock.calls
    expect(a[1].id).toBe(b[1].id)
  })

  it('otra respuesta a la misma pregunta usa otro id', async () => {
    await cargar()
    api.responderPregunta.mockRejectedValueOnce(new ApiError(502, 'x')).mockResolvedValue({ ok: true })
    await elegirOpcion(conTarjetas(), 0)
    filas.s1 = { fase: 'idle' }
    await elegirOpcion(conTarjetas(), 1)
    const [a, b] = api.responderPregunta.mock.calls
    expect(a[1].id).not.toBe(b[1].id)
  })

  it('un GET en vuelo no repuebla la pregunta ya contestada', async () => {
    await cargar()
    let resolver: (p: unknown) => void = () => {}
    api.getPregunta.mockReturnValue(new Promise((r) => (resolver = r)))
    recargar('s1', conTarjetas())
    api.responderPregunta.mockResolvedValue({ ok: true })
    await elegirOpcion(conTarjetas(), 0)
    resolver(pregunta('s1:a'))
    await Promise.resolve()
    await Promise.resolve()
    expect(formaDe(conTarjetas()).tipo).toBe('abrir')
  })

  it('si el GET da 404 cae al diálogo', async () => {
    api.getPregunta.mockRejectedValue(new ApiError(404, 'SIN_PREGUNTA'))
    api.getDialog.mockResolvedValue(null)
    init(fakeApi())
    activar('s1', conTarjetas())
    await vi.waitFor(() => expect(api.getDialog).toHaveBeenCalledWith('s1'))
  })

  it('un error que no es 409 deja el detalle del servidor', async () => {
    await cargar()
    api.responderPregunta.mockRejectedValue(new ApiError(400, 'Esa sesión no admite respuestas desde acá'))
    await elegirOpcion(conTarjetas(), 0)
    expect(filas.s1).toEqual({ fase: 'error', mensaje: 'Esa sesión no admite respuestas desde acá' })
  })

  it('una sesión sin tarjetas sigue por el camino del diálogo', async () => {
    api.getDialog.mockResolvedValue(null)
    init(fakeApi())
    activar('s1', sesion('s1'))
    expect(api.getDialog).toHaveBeenCalled()
    expect(api.getPregunta).not.toHaveBeenCalled()
  })
})

describe('formaDe con pedido', () => {
  const mk = (id: string, ts: number) => ({
    id,
    carpeta: '/x',
    mensaje: '',
    accion: 'cerrar' as const,
    origen: { pane_id: 'w1:p1', nombre: 'O', session_id: 's1' },
    ts,
    vence: 4_000_000_000,
  })
  it('usa el pedido más viejo de la sesión', () => {
    _resetPedidosPestana()
    pedidosPestana.items = [mk('nuevo', 20), mk('viejo', 10)]
    expect(formaDe({ ...sesion('s1'), motivo: 'pedido' })).toMatchObject({ tipo: 'pedido', pedidoId: 'viejo' })
    _resetPedidosPestana()
  })
  it('sin pedido cae a abrir', () => {
    _resetPedidosPestana()
    expect(formaDe({ ...sesion('s1'), motivo: 'pedido' })).toEqual({ tipo: 'abrir', motivo: 'Abrila en Colmena' })
  })
})

describe('resolverPedido y recarga con pedido', () => {
  const mk = (id: string) => ({
    id,
    carpeta: '/x',
    mensaje: '',
    accion: 'cerrar' as const,
    origen: { pane_id: 'w1:p1', nombre: 'O', session_id: 's1' },
    ts: 10,
    vence: 4_000_000_000,
  })
  const conPedido = () => ({ ...sesion('s1'), motivo: 'pedido' as const })

  it('aceptar abre el pedido de la fila y rechazar lo rechaza', async () => {
    _resetPedidosPestana()
    pedidosPestana.items = [mk('A')]
    init(fakeApi({ abrirPedidoPestana: apiPedidos.abrirPedidoPestana, rechazarPedidoPestana: apiPedidos.rechazarPedidoPestana } as unknown as Partial<Api>))
    apiPedidos.abrirPedidoPestana.mockResolvedValue({ cerrado: true })
    apiPedidos.rechazarPedidoPestana.mockResolvedValue({})
    await resolverPedido(conPedido(), 'aceptar', 'A')
    expect(apiPedidos.abrirPedidoPestana.mock.calls[0][0]).toBe('A')
    pedidosPestana.items = [mk('B')]
    await resolverPedido(conPedido(), 'rechazar', 'B')
    expect(apiPedidos.rechazarPedidoPestana).toHaveBeenCalledWith('B')
    _resetPedidosPestana()
  })

  it('resuelve el pedido que se dibujó, no el que esté primero al tocar', async () => {
    _resetPedidosPestana()
    apiPedidos.abrirPedidoPestana.mockClear()
    apiPedidos.rechazarPedidoPestana.mockClear()
    init(fakeApi({ abrirPedidoPestana: apiPedidos.abrirPedidoPestana, rechazarPedidoPestana: apiPedidos.rechazarPedidoPestana } as unknown as Partial<Api>))
    // Se dibujó A; mientras tanto A se resolvió en otro lado y ahora el primero es B.
    pedidosPestana.items = [mk('B')]
    await resolverPedido(conPedido(), 'aceptar', 'A')
    await resolverPedido(conPedido(), 'rechazar', 'A')
    expect(apiPedidos.abrirPedidoPestana).not.toHaveBeenCalled()
    expect(apiPedidos.rechazarPedidoPestana).not.toHaveBeenCalled()
    _resetPedidosPestana()
  })

  it('una sesión que no es de pedido no hace nada', async () => {
    await resolverPedido(sesion('s1'), 'aceptar', 'A')
    expect(apiPedidos.abrirPedidoPestana).not.toHaveBeenCalled()
  })

  it('activar una sesión con pedido no carga el diálogo', () => {
    api.getDialog.mockResolvedValue(null)
    init(fakeApi())
    activar('s1', conPedido())
    expect(api.getDialog).not.toHaveBeenCalled()
  })
})
