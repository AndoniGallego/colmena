import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as m from './reunion'
import { aplicarEvento, desdeSnapshot, inicial, LINEAS_VISIBLES, type EstadoReunionFront } from './reunion'

const activa = (extra: Partial<EstadoReunionFront> = {}): EstadoReunionFront => ({
  ...inicial(),
  reunion: 'r1',
  estado: 'escuchando',
  lector: 'escuchando',
  ...extra,
})
const linea = (id: string, texto = 'algo') => ({ reunion: 'r1', id, texto, tipo: 'pregunta' })

describe('aplicarEvento', () => {
  it('una línea nueva va arriba', () => {
    let e = aplicarEvento(activa(), 'reunion-linea', linea('l1', 'uno'))
    e = aplicarEvento(e, 'reunion-linea', linea('l2', 'dos'))
    expect(e.lineas.map((l) => l.id)).toEqual(['l2', 'l1'])
  })
  it('una línea repetida no se suma', () => {
    const e = aplicarEvento(activa(), 'reunion-linea', linea('l1'))
    expect(aplicarEvento(e, 'reunion-linea', linea('l1')).lineas).toHaveLength(1)
  })
  it('guarda como mucho las líneas visibles', () => {
    let e = activa()
    for (let i = 1; i <= LINEAS_VISIBLES + 5; i++) e = aplicarEvento(e, 'reunion-linea', linea(`l${i}`))
    expect(e.lineas).toHaveLength(LINEAS_VISIBLES)
    expect(e.lineas[0].id).toBe(`l${LINEAS_VISIBLES + 5}`)
  })
  it('reunion-respuesta actualiza la línea', () => {
    const e = aplicarEvento(activa(), 'reunion-linea', linea('l1'))
    const r = aplicarEvento(e, 'reunion-respuesta', {
      reunion: 'r1',
      linea: 'l1',
      estado: 'lista',
      texto: 'Sí, en el módulo X',
      archivos: ['a.py', 'b.py'],
    })
    expect(r.lineas[0].respuesta).toEqual({ estado: 'lista', texto: 'Sí, en el módulo X', archivos: ['a.py', 'b.py'] })
  })
  it('una respuesta para una línea desconocida o con estado raro no cambia nada', () => {
    const e = aplicarEvento(activa(), 'reunion-linea', linea('l1'))
    expect(aplicarEvento(e, 'reunion-respuesta', { reunion: 'r1', linea: 'l9', estado: 'lista', texto: '', archivos: [] })).toBe(e)
    expect(aplicarEvento(e, 'reunion-respuesta', { reunion: 'r1', linea: 'l1', estado: 'rarísimo', texto: '', archivos: [] })).toBe(e)
  })
  it('reunion-estado refleja tope, solo a mano y detecciones', () => {
    const e = aplicarEvento(activa(), 'reunion-estado', {
      reunion: 'r1',
      estado: 'escuchando',
      tope: true,
      solo_a_mano: false,
      detecciones: 12,
      tope_detecciones: 12,
      copiloto: 'listo',
    })
    expect(e).toMatchObject({ tope: true, soloAMano: false, detecciones: 12, topeDetecciones: 12, copiloto: 'listo' })
    const m = aplicarEvento(e, 'reunion-estado', { reunion: 'r1', estado: 'escuchando', tope: false, solo_a_mano: true, detecciones: 0, tope_detecciones: 0, copiloto: 'listo' })
    expect(m).toMatchObject({ tope: false, soloAMano: true })
  })
  it('reunion-estado de una reunión nueva arranca de cero', () => {
    const vieja = activa({ estado: 'guardada', biblioteca: 'b1', lineas: [{ id: 'l1', texto: 'x', tipo: 'pregunta' }] })
    const e = aplicarEvento(vieja, 'reunion-estado', { reunion: 'r2', estado: 'escuchando', tope: false, solo_a_mano: false, detecciones: 0, tope_detecciones: 10, copiloto: 'abriendo' })
    expect(e.reunion).toBe('r2')
    expect(e.lineas).toEqual([])
    expect(e.biblioteca).toBeNull()
  })
  it('eventos de otra reunión se ignoran', () => {
    const e = activa()
    expect(aplicarEvento(e, 'reunion-linea', { ...linea('l1'), reunion: 'r9' })).toBe(e)
    expect(aplicarEvento(e, 'reunion-estado', { reunion: 'r9', estado: 'pausada', tope: false, solo_a_mano: false, detecciones: 0, tope_detecciones: 1, copiloto: 'listo' })).toBe(e)
    expect(aplicarEvento(e, 'reunion-guardada', { reunion: 'r9', biblioteca: 'b' })).toBe(e)
  })
  it('reunion-guardada pasa a guardada con el id de Biblioteca', () => {
    const e = aplicarEvento(activa(), 'reunion-guardada', { reunion: 'r1', biblioteca: 'bib-7' })
    expect(e.estado).toBe('guardada')
    expect(e.biblioteca).toBe('bib-7')
  })
  it('datos rotos no cambian nada', () => {
    const e = activa()
    for (const [ev, d] of [
      ['reunion-linea', null],
      ['reunion-linea', { reunion: 'r1', id: 3, texto: 'x', tipo: 'pregunta' }],
      ['reunion-linea', { reunion: 'r1', id: 'l1', texto: 'x', tipo: 'otra' }],
      ['reunion-estado', 'nada'],
      ['reunion-estado', { reunion: 'r1', estado: 'volando' }],
      ['reunion-guardada', { reunion: 'r1' }],
      ['reunion-desconocido', {}],
    ] as const) {
      expect(aplicarEvento(e, ev, d)).toBe(e)
    }
  })
})

describe('descartar y anotar', () => {
  const dosLineas = () => aplicarEvento(aplicarEvento(activa(), 'reunion-linea', linea('l1')), 'reunion-linea', linea('l2'))
  it('reunion-descartada saca la línea', () => {
    const e = aplicarEvento(dosLineas(), 'reunion-descartada', { reunion: 'r1', linea: 'l1' })
    expect(e.lineas.map((l) => l.id)).toEqual(['l2'])
  })
  it('reunion-descartada de una línea desconocida o de otra reunión no cambia nada', () => {
    const e = dosLineas()
    expect(aplicarEvento(e, 'reunion-descartada', { reunion: 'r1', linea: 'l9' })).toBe(e)
    expect(aplicarEvento(e, 'reunion-descartada', { reunion: 'r2', linea: 'l1' })).toBe(e)
  })
  it('reunion-anotada marca la línea con su nota y la deja en la lista', () => {
    const e = aplicarEvento(dosLineas(), 'reunion-anotada', { reunion: 'r1', linea: 'l1', nota: 'n_1' })
    expect(e.lineas.map((l) => l.id)).toEqual(['l2', 'l1'])
    expect(e.lineas.find((l) => l.id === 'l1')?.nota).toBe('n_1')
    expect(e.lineas.find((l) => l.id === 'l2')?.nota).toBeUndefined()
  })
  it('reunion-anotada sin nota válida no cambia nada', () => {
    const e = dosLineas()
    expect(aplicarEvento(e, 'reunion-anotada', { reunion: 'r1', linea: 'l1' })).toBe(e)
  })
  it('el snapshot trae la nota de las líneas anotadas', () => {
    const e = desdeSnapshot(
      { reunion: 'r1', estado: 'escuchando', lineas: [{ id: 'l1', texto: 'a', tipo: 'pregunta', nota: 'n_1' }, { id: 'l2', texto: 'b', tipo: 'pregunta', nota: null }] },
      'escuchando',
    )
    expect(e.lineas.find((l) => l.id === 'l1')?.nota).toBe('n_1')
    expect(e.lineas.find((l) => l.id === 'l2')?.nota).toBeUndefined()
  })
})

describe('desdeSnapshot', () => {
  it('sin reunión deja el estado inactivo conservando el lector', () => {
    const e = desdeSnapshot(null, 'pausado')
    expect(e.estado).toBe('inactiva')
    expect(e.lector).toBe('pausado')
    expect(desdeSnapshot({}, 'apagado').reunion).toBeNull()
  })
  it('un snapshot con líneas y respuestas se normaliza', () => {
    const e = desdeSnapshot(
      {
        reunion: 'r1',
        estado: 'pausada',
        tope: false,
        solo_a_mano: false,
        detecciones: 2,
        tope_detecciones: 10,
        copiloto: 'listo',
        lineas: [
          { id: 'l1', texto: 'a', tipo: 'pregunta', respuesta: { estado: 'lista', texto: 'ok', archivos: ['x'] } },
          { id: 'l2', texto: 'b', tipo: 'manual', respuesta: null },
          { id: 7, texto: 'roto' },
        ],
      },
      'escuchando',
    )
    expect(e.reunion).toBe('r1')
    expect(e.estado).toBe('pausada')
    expect(e.lineas.map((l) => l.id)).toEqual(['l2', 'l1'])
    expect(e.lineas[1].respuesta?.texto).toBe('ok')
  })
})

describe('acciones', () => {
  const orden: string[] = []
  const falsoLector = (extra: Record<string, unknown> = {}) =>
    Object.assign(() => {}, {
      vaciar: async () => {
        orden.push('vaciar')
      },
      descartar: () => {
        orden.push('descartar')
      },
      ...extra,
    })
  const stubFetch = (respuesta: (url: string) => unknown = () => ({}), status = 202) =>
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        orden.push(url)
        return { ok: true, status, json: async () => respuesta(url) }
      }),
    )
  const stubTauri = (devuelve = 'apagado') =>
    vi.stubGlobal('window', { __TAURI__: { core: { invoke: async (c: string) => { orden.push(c); return devuelve } } } })

  beforeEach(() => {
    orden.length = 0
    m.reunion.value = inicial()
    m.errorReunion.value = null
    m.fijarLector(null)
    m.fijarDevice('')
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('escuchar: primero empezar en el back y recién después el lector', async () => {
    stubFetch(() => ({ reunion: 'r1', estado: 'escuchando' }), 200)
    stubTauri('escuchando')
    await m.escuchar([], true)
    expect(orden).toEqual(['/api/reunion/empezar', 'reunion_escuchar'])
    expect(m.reunion.value.reunion).toBe('r1')
    expect(m.reunion.value.lector).toBe('escuchando')
  })
  it('terminar: el lector vuelca, la cola sale, lo que sobra se descarta y recién después se cierra en el back', async () => {
    stubFetch()
    stubTauri()
    m.reunion.value = { ...inicial(), reunion: 'r1', estado: 'escuchando' }
    m.fijarLector(falsoLector())
    await m.terminar()
    expect(orden).toEqual(['reunion_terminar', 'vaciar', 'descartar', '/api/reunion/terminar'])
    orden.length = 0
    await m.terminar(true)
    expect(orden).toEqual(['vaciar', 'descartar', '/api/reunion/terminar'])
  })
  it('terminar desde la ventana Reunión le pide el cierre al notch y no toca el back', async () => {
    stubFetch()
    const emit = vi.fn(async () => undefined)
    vi.stubGlobal('window', { __TAURI__: { core: { invoke: async (c: string) => { orden.push(c) } }, event: { emit } } })
    m.reunion.value = { ...inicial(), reunion: 'r1', estado: 'escuchando' }
    m.fijarEnVentana(true)
    try {
      await m.terminar()
    } finally {
      m.fijarEnVentana(false)
    }
    expect(emit).toHaveBeenCalledWith('reunion-terminar-pedido')
    expect(orden).toEqual([])
  })
  it('un lector apagado por la bandeja termina sin invocar al lector', async () => {
    stubFetch()
    stubTauri()
    m.reunion.value = { ...inicial(), reunion: 'r1', estado: 'escuchando' }
    m.fijarLector(falsoLector())
    m.alLector('apagado', 'bandeja')
    await new Promise((r) => setTimeout(r, 0))
    expect(orden).toEqual(['vaciar', 'descartar', '/api/reunion/terminar'])
  })
  it('una reunión llena también termina cuando la bandeja apaga el lector', async () => {
    stubFetch()
    stubTauri()
    m.reunion.value = { ...inicial(), reunion: 'r1', estado: 'llena' }
    m.alLector('apagado', 'bandeja')
    await new Promise((r) => setTimeout(r, 0))
    expect(orden).toContain('/api/reunion/terminar')
  })
  it('un doble toque en Terminar cierra una sola vez', async () => {
    stubFetch()
    stubTauri()
    m.reunion.value = { ...inicial(), reunion: 'r1', estado: 'escuchando' }
    await Promise.all([m.terminar(), m.terminar()])
    expect(orden.filter((u) => u === '/api/reunion/terminar')).toHaveLength(1)
    orden.length = 0
    await m.terminar()
    expect(orden).toContain('/api/reunion/terminar')
  })
  it('idParaTexto: escuchando y sin_pc sí; pausada, llena y sin reunión no', () => {
    const con = (estado: EstadoReunionFront['estado']) => {
      m.reunion.value = { ...inicial(), reunion: 'r1', estado }
      return m.idParaTexto()
    }
    expect(con('escuchando')).toBe('r1')
    expect(con('sin_pc')).toBe('r1')
    expect(con('pausada')).toBeNull()
    expect(con('llena')).toBeNull()
    expect(con('terminando')).toBeNull()
    m.reunion.value = inicial()
    expect(m.idParaTexto()).toBeNull()
  })
  it('nueva reunión vuelve a pedir los repos', async () => {
    stubFetch(() => ({ repos: [{ ruta: '/r/a', nombre: 'a' }], todos: '/r' }), 200)
    m.nuevaReunion()
    await new Promise((r) => setTimeout(r, 0))
    expect(orden).toContain('/api/reunion/repos')
  })
  it('tocar desde error muestra buscando… otra vez', async () => {
    stubFetch(() => ({ estado: 'buscando' }))
    m.reunion.value = {
      ...inicial(),
      reunion: 'r1',
      estado: 'escuchando',
      lineas: [{ id: 'l1', texto: 'x', tipo: 'pregunta', respuesta: { estado: 'error', texto: '', archivos: [] } }],
    }
    await m.tocar('l1')
    expect(m.reunion.value.lineas[0].respuesta?.estado).toBe('buscando')
  })
  it('tocar usa el estado que devuelve el back: en_cola se muestra en cola', async () => {
    stubFetch(() => ({ estado: 'en_cola' }))
    m.reunion.value = { ...inicial(), reunion: 'r1', estado: 'escuchando', lineas: [{ id: 'l1', texto: 'x', tipo: 'pregunta' }] }
    await m.tocar('l1')
    expect(m.reunion.value.lineas[0].respuesta?.estado).toBe('en_cola')
  })
})

describe('acciones descartar y anotar', () => {
  const lineasBase = () => [
    { id: 'l1', texto: 'x', tipo: 'pregunta' as const },
    { id: 'l2', texto: 'y', tipo: 'requerimiento' as const },
  ]
  const preparar = () => {
    m.reunion.value = { ...inicial(), reunion: 'r1', estado: 'escuchando', lineas: lineasBase() }
    m.errorReunion.value = null
  }
  const fetchFalso = (status: number, cuerpo: unknown, llamadas: unknown[] = []) =>
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        llamadas.push([url, init?.body])
        return { ok: status < 400, status, json: async () => cuerpo }
      }),
    )
  it('descartar pide al back y saca la línea', async () => {
    const llamadas: unknown[] = []
    fetchFalso(202, { estado: 'descartada' }, llamadas)
    preparar()
    await m.descartar('l1')
    expect(llamadas[0]).toEqual(['/api/reunion/descartar', JSON.stringify({ reunion: 'r1', linea: 'l1' })])
    expect(m.reunion.value.lineas.map((l) => l.id)).toEqual(['l2'])
  })
  it('descartar con 409 deja la línea y avisa que el Copiloto está buscando', async () => {
    fetchFalso(409, { detail: 'x' })
    preparar()
    await m.descartar('l1')
    expect(m.reunion.value.lineas).toHaveLength(2)
    expect(m.errorReunion.value).toBe('El Copiloto está buscando esa línea. Esperá que termine para descartarla.')
  })
  it('anotar marca la línea con la nota que devuelve el back', async () => {
    const llamadas: unknown[] = []
    fetchFalso(202, { nota: 'n_7' }, llamadas)
    preparar()
    await m.anotar('l2')
    expect(llamadas[0]).toEqual(['/api/reunion/anotar', JSON.stringify({ reunion: 'r1', linea: 'l2' })])
    expect(m.reunion.value.lineas.find((l) => l.id === 'l2')?.nota).toBe('n_7')
  })
  it('anotar que falla muestra un aviso y no marca la línea', async () => {
    fetchFalso(503, {})
    preparar()
    await m.anotar('l2')
    expect(m.reunion.value.lineas.find((l) => l.id === 'l2')?.nota).toBeUndefined()
    expect(m.errorReunion.value).toBe('No pude anotar la línea.')
  })
})

describe('Mostrame: estado', () => {
  it('acepta una línea tipo mostrar y ocupado: true', () => {
    let e = aplicarEvento(activa(), 'reunion-linea', { reunion: 'r1', id: 'l1', texto: 'Mostrame', tipo: 'mostrar' })
    expect(e.lineas[0].tipo).toBe('mostrar')
    e = aplicarEvento(e, 'reunion-estado', { reunion: 'r1', estado: 'escuchando', tope: false, solo_a_mano: false, detecciones: 0, tope_detecciones: 1, copiloto: 'listo', ocupado: true })
    expect(e.ocupado).toBe(true)
    expect(desdeSnapshot({ reunion: 'r1', estado: 'escuchando', ocupado: true, lineas: [] }, 'escuchando').ocupado).toBe(true)
    expect(inicial().ocupado).toBe(false)
  })

  describe('puedeMostrar', () => {
    const listo = (extra: Partial<EstadoReunionFront> = {}) => activa({ copiloto: 'listo', ...extra })
    it('todo bien', () => {
      expect(m.puedeMostrar(listo(), true, null)).toEqual({ ok: true })
      expect(m.puedeMostrar(listo({ estado: 'pausada' }), null, null).ok).toBe(true)
    })
    it('nudo apagado', () => {
      expect(m.puedeMostrar(listo(), false, null)).toEqual({ ok: false, motivo: 'Prendé el nudo en la bandeja' })
    })
    it('ocupado', () => {
      expect(m.puedeMostrar(listo({ ocupado: true }), true, null)).toEqual({ ok: false, motivo: 'El Copiloto está ocupado' })
    })
    it('línea buscando o en cola', () => {
      for (const estado of ['buscando', 'en_cola'] as const) {
        const l = [{ id: 'l1', texto: 'x', tipo: 'pregunta' as const, respuesta: { estado, texto: '', archivos: [] } }]
        expect(m.puedeMostrar(listo({ lineas: l }), true, null).ok).toBe(false)
      }
    })
    it('copiloto abriendo', () => {
      expect(m.puedeMostrar(activa({ copiloto: 'abriendo' }), true, null)).toEqual({ ok: false, motivo: 'El Copiloto todavía no está listo' })
    })
    it('en espera', () => {
      expect(m.puedeMostrar(listo(), true, 'l3').ok).toBe(false)
      expect(m.puedeMostrar(listo(), true, 'capturando').ok).toBe(false)
    })
    it('estado no activo da motivo', () => {
      expect(m.puedeMostrar(listo({ estado: 'llena' }), true, null)).toEqual({ ok: false, motivo: 'La reunión está llena: tocá Terminar' })
      expect(m.puedeMostrar(listo({ estado: 'sin_pc' }), true, null)).toEqual({ ok: false, motivo: 'Perdí la conexión con la PC' })
      expect(m.puedeMostrar(listo({ estado: 'terminando' }), true, null).motivo).toBe('La reunión se está guardando')
    })
  })

  describe('mirando', () => {
    beforeEach(() => {
      m.reunion.value = activa({ lineas: [{ id: 'l7', texto: 'x', tipo: 'mostrar' }, { id: 'l8', texto: 'y', tipo: 'pregunta' }] })
      m.mirando.value = 'l7'
    })
    afterEach(() => {
      m.mirando.value = null
      m.reunion.value = inicial()
    })
    it('lista o error de la línea en espera limpia mirando', () => {
      m.aplicarServidor('reunion-respuesta', { reunion: 'r1', linea: 'l7', estado: 'lista', texto: 'ok', archivos: [] })
      expect(m.mirando.value).toBeNull()
      m.mirando.value = 'l7'
      m.aplicarServidor('reunion-respuesta', { reunion: 'r1', linea: 'l7', estado: 'error', texto: '', archivos: [] })
      expect(m.mirando.value).toBeNull()
    })
    it('carrera: la respuesta llega antes del 202 y no queda trabado', async () => {
      m.mirando.value = null
      vi.stubGlobal('fetch', vi.fn(async () => {
        // La respuesta lista llega mientras el POST sigue en vuelo.
        m.aplicarServidor('reunion-respuesta', { reunion: 'r1', linea: 'l9', estado: 'lista', texto: 'ok', archivos: [] })
        return { ok: true, status: 202, json: async () => ({ linea: 'l9', estado: 'buscando' }) }
      }))
      vi.stubGlobal('window', {
        __TAURI__: {
          core: {
            invoke: async () => ({
              foto: 1,
              ventana: { titulo: 't', proceso: 'p' },
              controles: [],
              imagen: { tipo: 'png', ancho: 10, alto: 10, b64: 'AAAA' },
            }),
          },
        },
      })
      await m.mostrarAhora('x')
      vi.unstubAllGlobals()
      expect(m.mirando.value).toBeNull()
    })
    it('se limpia al terminar la reunión o cambiar de id', () => {
      m.aplicarServidor('reunion-estado', { reunion: 'r1', estado: 'terminando', tope: false, solo_a_mano: false, detecciones: 0, tope_detecciones: 1, copiloto: 'listo' })
      expect(m.mirando.value).toBeNull()
    })
    it('se limpia si el snapshot no tiene la línea pendiente', async () => {
      vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ reunion: 'r1', estado: 'escuchando', copiloto: 'listo', lineas: [{ id: 'l7', texto: 'x', tipo: 'mostrar' }] }) })))
      await m.cargarEstado()
      vi.unstubAllGlobals()
      expect(m.mirando.value).toBeNull()
    })
    it('el snapshot con la línea todavía buscando la conserva', async () => {
      vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ reunion: 'r1', estado: 'escuchando', copiloto: 'listo', lineas: [{ id: 'l7', texto: 'x', tipo: 'mostrar', respuesta: { estado: 'buscando', texto: '', archivos: [] } }] }) })))
      await m.cargarEstado()
      vi.unstubAllGlobals()
      expect(m.mirando.value).toBe('l7')
    })
    it('otra línea o un estado intermedio no lo limpian', () => {
      m.aplicarServidor('reunion-respuesta', { reunion: 'r1', linea: 'l8', estado: 'lista', texto: 'ok', archivos: [] })
      m.aplicarServidor('reunion-respuesta', { reunion: 'r1', linea: 'l7', estado: 'buscando', texto: '', archivos: [] })
      expect(m.mirando.value).toBe('l7')
    })
  })
})

describe('enCurso', () => {
  it('cuenta como en curso desde escuchando hasta terminando', () => {
    for (const estado of ['escuchando', 'pausada', 'sin_pc', 'llena', 'terminando'] as const) {
      expect(m.enCurso({ ...inicial(), reunion: 'r1', estado })).toBe(true)
    }
    for (const estado of ['inactiva', 'guardada'] as const) {
      expect(m.enCurso({ ...inicial(), reunion: 'r1', estado })).toBe(false)
    }
    expect(m.enCurso({ ...inicial(), reunion: null, estado: 'escuchando' })).toBe(false)
  })
})
