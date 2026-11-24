// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  pedirGuia: vi.fn(),
  siguienteGuia: vi.fn(),
  salirGuia: vi.fn(async () => undefined),
  reunion: { value: { reunion: null as string | null, estado: 'inactiva' } },
  modo: { value: 'cerrado' as string },
}))

vi.mock('../lib/guiaPuente', async (orig) => ({
  ...(await orig<typeof import('../lib/guiaPuente')>()),
  pedirGuia: h.pedirGuia,
  siguienteGuia: h.siguienteGuia,
  salirGuia: h.salirGuia,
}))
vi.mock('./reunion', () => ({
  reunion: h.reunion,
  enCurso: (e: { reunion: string | null; estado: string }) => !!e.reunion && e.estado === 'escuchando',
}))
vi.mock('./notch', () => ({ modo: h.modo }))

const g = await import('./guia')
const { MENSAJE_GUIA } = await import('../lib/guiaPuente')

type Tauri = NonNullable<Window['__TAURI__']>
const invoke = vi.fn(async (_c: string, _a?: Record<string, unknown>) => 'ok')

const con = (p: Partial<import('./guia').EstadoGuiaFront>) => ({ ...g.inicialGuia(), ...p })

beforeEach(() => {
  invoke.mockClear()
  h.pedirGuia.mockReset()
  h.siguienteGuia.mockReset()
  h.salirGuia.mockClear()
  h.reunion.value = { reunion: null, estado: 'inactiva' }
  h.modo.value = 'cerrado'
  g.guia.value = g.inicialGuia()
  g.fijarDevice('pc-1')
  ;(window as { __TAURI__?: Tauri }).__TAURI__ = { core: { invoke } }
})

describe('aplicarEventoGuia', () => {
  it('ignora una guía anterior', () => {
    const e = con({ estado: 'paso', guia: 2, paso: 1, total: 3, texto: 'Tocá Archivo' })
    expect(g.aplicarEventoGuia(e, { guia: 1, estado: 'paso', paso: 5, total: 5, texto: 'viejo' })).toEqual(e)
  })

  it('acepta preparando antes del 202 (guia null)', () => {
    const r = g.aplicarEventoGuia(g.inicialGuia(), { guia: 4, estado: 'preparando', paso: 0, total: 0, texto: '' })
    expect(r).toMatchObject({ estado: 'preparando', guia: 4 })
  })

  it('toma estado, paso, total y texto de la misma guía o una más nueva', () => {
    const e = con({ estado: 'mirando', guia: 2 })
    expect(g.aplicarEventoGuia(e, { guia: 2, estado: 'paso', paso: 2, total: 3, texto: 'Tocá Guardar' })).toEqual({
      estado: 'paso',
      guia: 2,
      paso: 2,
      total: 3,
      texto: 'Tocá Guardar',
      sigue: false,
    })
  })

  it('una forma rota no cambia nada', () => {
    const e = con({ estado: 'paso', guia: 2, paso: 1, total: 2, texto: 'x' })
    expect(g.aplicarEventoGuia(e, null)).toEqual(e)
    expect(g.aplicarEventoGuia(e, { guia: 'x', estado: 'paso' })).toEqual(e)
    expect(g.aplicarEventoGuia(e, { guia: 3, estado: 'raro', paso: 0, total: 0, texto: '' })).toEqual(e)
  })
})

describe('textoCajita', () => {
  it('usa los textos exactos de cada estado', () => {
    expect(g.textoCajita(con({ estado: 'vacia' }))).toBe('')
    expect(g.textoCajita(con({ estado: 'preparando' }))).toBe('Preparando…')
    expect(g.textoCajita(con({ estado: 'mirando' }))).toBe('Mirando la ventana…')
    expect(g.textoCajita(con({ estado: 'paso', paso: 2, total: 3, texto: 'Tocá Archivo' }))).toBe('Paso 2 de 3: Tocá Archivo')
    expect(g.textoCajita(con({ estado: 'fin', paso: 3, total: 3, texto: 'Listo el archivo' }))).toBe('Paso 3 de 3: Listo el archivo')
    expect(g.textoCajita(con({ estado: 'no_encontrado', texto: 'No lo veo en pantalla' }))).toBe('No lo veo en pantalla')
    expect(g.textoCajita(con({ estado: 'error', texto: 'El ayudante no arrancó, probá de nuevo' }))).toBe('El ayudante no arrancó, probá de nuevo')
    expect(g.textoCajita(con({ estado: 'terminado' }))).toBe('Terminado')
    expect(g.textoCajita(con({ estado: 'reunion' }))).toBe('Hay una reunión en curso: usá Mostrame del notch')
  })
})

describe('guiaActiva y puedeSiguiente', () => {
  it('guiaActiva', () => {
    for (const estado of ['preparando', 'mirando', 'paso', 'fin', 'no_encontrado'] as const) expect(g.guiaActiva(con({ estado }))).toBe(true)
    for (const estado of ['vacia', 'error', 'terminado', 'reunion'] as const) expect(g.guiaActiva(con({ estado }))).toBe(false)
  })

  it('puedeSiguiente: paso, no_encontrado, o error con guía', () => {
    expect(g.puedeSiguiente(con({ estado: 'paso' }))).toBe(true)
    expect(g.puedeSiguiente(con({ estado: 'no_encontrado' }))).toBe(true)
    expect(g.puedeSiguiente(con({ estado: 'error', guia: 3, sigue: true }))).toBe(true)
    expect(g.puedeSiguiente(con({ estado: 'error', guia: 3, sigue: false }))).toBe(false)
    expect(g.puedeSiguiente(con({ estado: 'error', guia: null }))).toBe(false)
    expect(g.puedeSiguiente(con({ estado: 'mirando' }))).toBe(false)
    expect(g.puedeSiguiente(con({ estado: 'fin' }))).toBe(false)
  })
})

describe('aplicarServidorGuia', () => {
  it('con fin invoca nudo_guia_paso con fin: true', async () => {
    await g.aplicarServidorGuia({ guia: 1, estado: 'fin', paso: 3, total: 3, texto: 'Listo' })
    expect(invoke).toHaveBeenCalledWith('nudo_guia_paso', { paso: 3, total: 3, fin: true })
    expect(g.guia.value.estado).toBe('fin')
  })

  it('con paso invoca con fin: false', async () => {
    await g.aplicarServidorGuia({ guia: 1, estado: 'paso', paso: 1, total: 3, texto: 'Tocá' })
    expect(invoke).toHaveBeenCalledWith('nudo_guia_paso', { paso: 1, total: 3, fin: false })
  })

  it('no invoca con otros estados ni con una guía vieja, y ignora errores del invoke', async () => {
    await g.aplicarServidorGuia({ guia: 5, estado: 'mirando', paso: 0, total: 0, texto: '' })
    expect(invoke).not.toHaveBeenCalled()
    await g.aplicarServidorGuia({ guia: 4, estado: 'paso', paso: 1, total: 2, texto: 'viejo' })
    expect(invoke).not.toHaveBeenCalled()
    invoke.mockRejectedValueOnce(new Error('sin globo'))
    await expect(g.aplicarServidorGuia({ guia: 6, estado: 'paso', paso: 1, total: 2, texto: 'ok' })).resolves.toBeUndefined()
  })
})

describe('abrirCajita', () => {
  it('abre en modo guia', () => {
    g.abrirCajita()
    expect(h.modo.value).toBe('guia')
  })

  it('con reunión en curso muestra el aviso', () => {
    h.reunion.value = { reunion: 'r1', estado: 'escuchando' }
    g.abrirCajita()
    expect(h.modo.value).toBe('guia')
    expect(g.guia.value.estado).toBe('reunion')
  })
})

describe('alAtajo', () => {
  it('mientras mira no captura: solo abre la cajita', async () => {
    g.guia.value = con({ estado: 'mirando', guia: 1 })
    await g.alAtajo()
    expect(h.modo.value).toBe('guia')
    expect(invoke).not.toHaveBeenCalledWith('nudo_mostrar')
    expect(h.siguienteGuia).not.toHaveBeenCalled()
    expect(h.pedirGuia).not.toHaveBeenCalled()
  })

  it('mientras prepara tampoco captura', async () => {
    g.guia.value = con({ estado: 'preparando', guia: null })
    await g.alAtajo()
    expect(h.modo.value).toBe('guia')
    expect(h.siguienteGuia).not.toHaveBeenCalled()
  })

  it('con un paso a la vista hace siguiente', async () => {
    g.guia.value = con({ estado: 'paso', guia: 1, paso: 1, total: 3, texto: 'Tocá' })
    h.siguienteGuia.mockResolvedValue({ ok: true, guia: 1, estado: 'mirando' })
    await g.alAtajo()
    expect(h.siguienteGuia).toHaveBeenCalledTimes(1)
    expect(h.siguienteGuia.mock.calls[0][0]).toMatchObject({ device: 'pc-1' })
    expect(g.guia.value.estado).toBe('mirando')
  })

  it('al avanzar con el atajo no abre la cajita: abrirla le pediría el foco a Windows', async () => {
    g.guia.value = con({ estado: 'paso', guia: 1, paso: 1, total: 3, texto: 'Tocá' })
    h.siguienteGuia.mockResolvedValue({ ok: true, guia: 1, estado: 'mirando' })
    await g.alAtajo()
    expect(h.siguienteGuia).toHaveBeenCalledTimes(1)
    expect(h.modo.value).toBe('cerrado')
  })

  it('sin guía abre la cajita sin capturar', async () => {
    await g.alAtajo()
    expect(h.modo.value).toBe('guia')
    expect(h.siguienteGuia).not.toHaveBeenCalled()
    expect(h.pedirGuia).not.toHaveBeenCalled()
  })
})

describe('pedir y siguiente', () => {
  it('pedir pasa a preparando/mirando con el número de guía', async () => {
    h.pedirGuia.mockResolvedValue({ ok: true, guia: 7, estado: 'preparando' })
    await g.pedir('Quiero guardar')
    expect(h.pedirGuia.mock.calls[0][0]).toMatchObject({ device: 'pc-1', pregunta: 'Quiero guardar' })
    expect(g.guia.value).toMatchObject({ estado: 'preparando', guia: 7 })
  })

  it('un error de pedir deja estado error con el mensaje', async () => {
    h.pedirGuia.mockResolvedValue({ ok: false, error: 'otra_pc' })
    await g.pedir('x')
    expect(g.guia.value).toMatchObject({ estado: 'error', texto: MENSAJE_GUIA.otra_pc })
  })

  it('un 409 mirando en siguiente deja el error con el número de guía', async () => {
    h.siguienteGuia.mockResolvedValue({ ok: false, error: 'mirando' })
    g.guia.value = con({ estado: 'paso', guia: 1 })
    await g.siguiente()
    expect(g.guia.value).toMatchObject({ estado: 'error', guia: 1, texto: 'Todavía estoy mirando', sigue: true })
  })

  it('el SSE que llega antes del 202 no lo pisa el 202', async () => {
    h.pedirGuia.mockImplementation(async () => {
      await g.aplicarServidorGuia({ guia: 7, estado: 'mirando', paso: 0, total: 0, texto: '' })
      return { ok: true, guia: 7, estado: 'preparando' }
    })
    await g.pedir('x')
    expect(g.guia.value.estado).toBe('mirando')
  })

  it('pedir con pregunta vacía no captura', async () => {
    await g.pedir('   ')
    expect(h.pedirGuia).not.toHaveBeenCalled()
  })
})

describe('terminar', () => {
  it('postea salir y limpia el nudo', async () => {
    g.guia.value = con({ estado: 'fin', guia: 3, paso: 3, total: 3, texto: 'x' })
    await g.terminar()
    expect(h.salirGuia).toHaveBeenCalledWith(expect.objectContaining({ device: 'pc-1' }))
    expect(invoke).toHaveBeenCalledWith('nudo_limpiar')
    expect(g.guia.value.estado).toBe('terminado')
  })
})

describe('siguiente del globo mientras mira', () => {
  const paso = (guia: number, n = 2) => ({ guia, estado: 'paso', paso: n, total: 3, texto: 'x' })

  it('se recuerda y se dispara cuando llega el paso de la misma guía', async () => {
    g.guia.value = con({ estado: 'mirando', guia: 1 })
    h.siguienteGuia.mockResolvedValue({ ok: true, guia: 1, estado: 'mirando' })
    await g.siguienteDelGlobo()
    expect(h.siguienteGuia).not.toHaveBeenCalled()
    await g.aplicarServidorGuia(paso(1))
    expect(h.siguienteGuia).toHaveBeenCalledTimes(1)
    expect(g.guia.value.estado).toBe('mirando')
    await g.aplicarServidorGuia(paso(1, 3))
    expect(h.siguienteGuia).toHaveBeenCalledTimes(1)
  })

  it('con un paso a la vista hace siguiente directo', async () => {
    g.guia.value = con({ estado: 'paso', guia: 1, paso: 1, total: 3 })
    h.siguienteGuia.mockResolvedValue({ ok: true, guia: 1, estado: 'mirando' })
    await g.siguienteDelGlobo()
    expect(h.siguienteGuia).toHaveBeenCalledTimes(1)
  })

  it('se descarta si llega fin, error o una guía nueva', async () => {
    for (const ev of [
      { guia: 1, estado: 'fin', paso: 1, total: 1, texto: 'x' },
      { guia: 1, estado: 'error', paso: 0, total: 0, texto: 'x', sigue: false },
      { guia: 2, estado: 'paso', paso: 1, total: 2, texto: 'nueva' },
    ]) {
      g.guia.value = con({ estado: 'mirando', guia: 1 })
      await g.siguienteDelGlobo()
      await g.aplicarServidorGuia(ev)
      await g.aplicarServidorGuia(paso(2, 2))
      expect(h.siguienteGuia).not.toHaveBeenCalled()
    }
  })

  it('un pedido nuevo lo descarta', async () => {
    g.guia.value = con({ estado: 'mirando', guia: 1 })
    await g.siguienteDelGlobo()
    h.pedirGuia.mockResolvedValue({ ok: true, guia: 1, estado: 'mirando' })
    g.guia.value = con({ estado: 'paso', guia: 1, paso: 1, total: 2 })
    await g.pedir('otra cosa')
    await g.aplicarServidorGuia(paso(1))
    expect(h.siguienteGuia).not.toHaveBeenCalled()
  })
})

describe('errores que terminan la guía', () => {
  it('un error sin sigue limpia el nudo, no permite siguiente y el atajo abre la cajita', async () => {
    g.guia.value = con({ estado: 'mirando', guia: 4 })
    await g.aplicarServidorGuia({ guia: 4, estado: 'error', paso: 0, total: 0, texto: 'No arrancó', sigue: false })
    expect(invoke).toHaveBeenCalledWith('nudo_limpiar')
    expect(g.guia.value).toMatchObject({ estado: 'error', guia: 4, sigue: false })
    expect(g.puedeSiguiente(g.guia.value)).toBe(false)
    await g.alAtajo()
    expect(h.siguienteGuia).not.toHaveBeenCalled()
    expect(h.modo.value).toBe('guia')
    await g.aplicarServidorGuia({ guia: 3, estado: 'paso', paso: 1, total: 2, texto: 'tarde' })
    expect(g.guia.value.estado).toBe('error')
  })

  it('un error con sigue true deja seguir y no limpia', async () => {
    g.guia.value = con({ estado: 'mirando', guia: 4 })
    await g.aplicarServidorGuia({ guia: 4, estado: 'error', paso: 0, total: 0, texto: 'No me respondió', sigue: true })
    expect(invoke).not.toHaveBeenCalledWith('nudo_limpiar')
    expect(g.puedeSiguiente(g.guia.value)).toBe(true)
    expect(g.seguirViva(g.guia.value)).toBe(true)
  })

  it('un error de pedir no deja seguir', async () => {
    h.pedirGuia.mockResolvedValue({ ok: false, error: 'fallo' })
    await g.pedir('x')
    expect(g.guia.value.sigue).toBe(false)
  })

  it('409 sin_guia en siguiente deja la cajita vacía con el mensaje', async () => {
    h.siguienteGuia.mockResolvedValue({ ok: false, error: 'sin_guia' })
    g.guia.value = con({ estado: 'paso', guia: 5, paso: 2, total: 3, texto: 'x' })
    await g.siguiente()
    expect(g.guia.value).toMatchObject({ estado: 'error', paso: 0, total: 0, sigue: false, texto: MENSAJE_GUIA.sin_guia })
    expect(g.puedeSiguiente(g.guia.value)).toBe(false)
  })

  it('terminar sin guía activa no pisa un error con Terminado', async () => {
    g.guia.value = con({ estado: 'error', guia: 5, texto: 'No arrancó', sigue: false })
    await g.terminar()
    expect(g.guia.value.estado).toBe('error')
    expect(h.salirGuia).not.toHaveBeenCalled()
  })
})
