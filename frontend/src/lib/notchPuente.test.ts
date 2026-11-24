import { describe, expect, it, vi } from 'vitest'
import { anchoVentanaFijo } from './notchMovimiento'
import { crearPuente, escuchar, esRutaNotch, esVistaReunion, formaPara, pasosVentana, ventanaPara } from './notchPuente'

describe('notchPuente', () => {
  it('reconoce la ruta del notch', () => {
    expect([esRutaNotch('/notch'), esRutaNotch('/notch/'), esRutaNotch('/'), esRutaNotch('/notchx')]).toEqual([true, true, false, false])
  })

  it('reconoce la vista de reunión por el parámetro vista', () => {
    expect([esVistaReunion('?vista=reunion'), esVistaReunion('?x=1&vista=reunion'), esVistaReunion(''), esVistaReunion('?vista=otra')]).toEqual([true, true, false, false])
  })

  it('mostrarReunion trae la ventana en el programa y no hace nada fuera', () => {
    const invoke = vi.fn().mockResolvedValue(undefined)
    crearPuente({ __TAURI__: { core: { invoke } } } as unknown as Window).mostrarReunion()
    expect(invoke).toHaveBeenCalledWith('reunion_mostrar_ventana')
    expect(() => crearPuente({} as unknown as Window).mostrarReunion()).not.toThrow()
  })

  it('en el programa usa los comandos del notch', () => {
    const invoke = vi.fn().mockResolvedValue(undefined)
    const p = crearPuente({ __TAURI__: { core: { invoke } } } as unknown as Window)
    p.tamano(300, 60, true)
    p.forma(10, 5, 200, 48, 22)
    p.arrastrar()
    p.abrirColmena('abc-1')
    p.aviso('te-toca')
    expect(invoke.mock.calls).toEqual([
      ['notch_tamano', { ancho: 300, alto: 60, foco: true }],
      ['notch_forma', { x: 10, y: 5, ancho: 200, alto: 48, radio: 22 }],
      ['notch_arrastrar'],
      ['abrir_colmena', { sesion: 'abc-1' }],
      ['mostrar_aviso', { tipo: 'te-toca' }],
    ])
  })

  it('un id inválido abre Colmena sin sesión', () => {
    const invoke = vi.fn().mockResolvedValue(undefined)
    crearPuente({ __TAURI__: { core: { invoke } } } as unknown as Window).abrirColmena('../x y')
    expect(invoke).toHaveBeenCalledWith('abrir_colmena', { sesion: null })
  })

  it('abrirBiblioteca invoca el comando con el ítem y un id inválido abre Colmena sin ítem', () => {
    const invoke = vi.fn().mockResolvedValue(undefined)
    const p = crearPuente({ __TAURI__: { core: { invoke } } } as unknown as Window)
    const id = '0123456789abcdef0123456789abcdef'
    p.abrirBiblioteca(id)
    p.abrirBiblioteca('../x')
    expect(invoke.mock.calls).toEqual([
      ['abrir_biblioteca', { item: id }],
      ['abrir_colmena', { sesion: null }],
    ])
  })

  it('abrirBiblioteca en el navegador abre la pestaña de Colmena en ese ítem', () => {
    const open = vi.fn()
    const id = '0123456789abcdef0123456789abcdef'
    crearPuente({ open } as unknown as Window).abrirBiblioteca(id)
    expect(open).toHaveBeenCalledWith('/?biblioteca=' + id, 'colmena')
  })

  it('en el navegador abre una pestaña de Colmena', () => {
    const open = vi.fn()
    const p = crearPuente({ open } as unknown as Window)
    p.abrirColmena('s:1')
    p.abrirColmena()
    p.tamano(1, 1, false)
    expect(open.mock.calls).toEqual([
      ['/?session=s%3A1', 'colmena'],
      ['/', 'colmena'],
    ])
    expect(p.enPrograma).toBe(false)
  })

  it('la ventana deja margen para la sombra y respeta los límites', () => {
    expect(ventanaPara({ ancho: 200.2, alto: 46 })).toEqual({ ancho: 233, alto: 62 })
    expect(ventanaPara({ ancho: 5000, alto: 1 })).toEqual({ ancho: 800, alto: 40 })
  })

  it('con ancho fijo de pastilla el ancho de ventana no cambia entre cerrado y abierto', () => {
    const pantalla = 1920
    const anchoPastilla = anchoVentanaFijo(pantalla)
    const cerrado = ventanaPara({ ancho: anchoPastilla, alto: 44 })
    const panel = ventanaPara({ ancho: anchoPastilla, alto: 600 })
    expect(cerrado.ancho).toBe(panel.ancho)
    expect(cerrado.ancho).toBe(472)
  })
})

describe('formaPara', () => {
  it('devuelve copia si no hay segundo rect', () => {
    const a = { x: 1, y: 2, ancho: 100, alto: 40, radio: 20 }
    const u = formaPara(a)
    expect(u).toEqual(a)
    expect(u).not.toBe(a)
  })

  it('une dos rectángulos y toma el radio mayor', () => {
    const a = { x: 10, y: 5, ancho: 30, alto: 20, radio: 10 }
    const b = { x: 25, y: 12, ancho: 40, alto: 25, radio: 18 }
    expect(formaPara(a, b)).toEqual({ x: 10, y: 5, ancho: 55, alto: 32, radio: 18 })
  })
})

describe('pasosVentana', () => {
  it('sin tamaño actual pide el destino antes de animar', () => {
    expect(pasosVentana(null, { ancho: 300, alto: 80 })).toEqual({
      antes: { ancho: 300, alto: 80 },
      despues: null,
    })
  })

  it('si el destino es igual no pide resize', () => {
    expect(pasosVentana({ ancho: 300, alto: 80 }, { ancho: 300, alto: 80 })).toEqual({
      antes: null,
      despues: null,
    })
  })

  it('si crece en ambas dimensiones agranda antes', () => {
    expect(pasosVentana({ ancho: 200, alto: 60 }, { ancho: 400, alto: 120 })).toEqual({
      antes: { ancho: 400, alto: 120 },
      despues: null,
    })
  })

  it('si achica en ambas dimensiones agranda después', () => {
    expect(pasosVentana({ ancho: 400, alto: 120 }, { ancho: 200, alto: 60 })).toEqual({
      antes: null,
      despues: { ancho: 200, alto: 60 },
    })
  })

  it('si crece en una y achica en otra usa el máximo antes y el destino después', () => {
    expect(pasosVentana({ ancho: 300, alto: 100 }, { ancho: 250, alto: 150 })).toEqual({
      antes: { ancho: 300, alto: 150 },
      despues: { ancho: 250, alto: 150 },
    })
  })

  it('escuchar registra el evento y llama al callback al dispararse', async () => {
    let handler: ((e: unknown) => void) | null = null
    const listen = vi.fn().mockImplementation(async (_ev: string, h: (e: unknown) => void) => {
      handler = h
      return () => undefined
    })
    const cb = vi.fn()
    escuchar('notas-abrir', cb, { __TAURI__: { event: { listen } } } as unknown as Window)
    expect(listen).toHaveBeenCalledWith('notas-abrir', expect.any(Function))
    handler!({ payload: null })
    expect(cb).toHaveBeenCalledTimes(1)
  })

  it('escuchar sin Tauri no tira error ni llama al callback', () => {
    const cb = vi.fn()
    expect(() => escuchar('notas-abrir', cb, {} as unknown as Window)).not.toThrow()
    expect(cb).not.toHaveBeenCalled()
  })
})
