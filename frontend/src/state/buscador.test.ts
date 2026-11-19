import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Api } from '../api/types'

vi.mock('../motion', () => ({ isSoft: () => true, haptic: () => {} }))

vi.hoisted(() => {
  vi.stubGlobal('window', { matchMedia: () => ({ matches: false, addEventListener() {} }), addEventListener() {} })
  vi.stubGlobal('location', { search: '', pathname: '/' })
  vi.stubGlobal('history', { state: null, pushState() {}, replaceState() {}, back() {} })
})

const demo = vi.hoisted(() => ({ correr: vi.fn() }))
vi.mock('../piezas', async () => {
  const { ref } = await import('vue')
  const seccion = { titulo: 'Demo', icono: 'clock', vista: {}, visible: ref(false) }
  return {
    piezas: () => [
      {
        id: 'demo',
        seccion,
        buscador: {
          seccion: { titulo: 'Demo', sub: 'Sección de prueba', icono: 'calendar', claves: 'demo' },
          acciones: [{ id: 'abrirdemo', titulo: 'Abrir demo', sub: '', icono: 'calendar', claves: '', correr: demo.correr }],
        },
      },
    ],
  }
})

const { abrirPaleta, cerrarPaleta, ejecutar, elegir, paleta, recientes, resultados } = await import('./buscador')
const { auth, init, viewRequest, highlight } = await import('./app')
const { piezas } = await import('../piezas')
const demoVisible = piezas()[0].seccion!.visible
const { libVisible } = await import('./biblioteca')
const { openSessionId } = await import('./session')
const { openTerminalId } = await import('./terminales')
const { construirCatalogo } = await import('../lib/buscador')

beforeEach(() => {
  paleta.value = false
  recientes.value = []
  demoVisible.value = libVisible.value = false
  openSessionId.value = null
  openTerminalId.value = null
  viewRequest.value = null
  highlight.value = null
  demo.correr.mockClear()
  init({ getAvisos: vi.fn(async () => ({ items: [], hayMas: false, noLeidos: 0, leidosHasta: 0 })) } as unknown as Api)
  vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => undefined })
})

describe('buscador', () => {
  it('solo abre con la sesión lista', () => {
    auth.value = 'login'
    abrirPaleta()
    expect(paleta.value).toBe(false)
    auth.value = 'ready'
    abrirPaleta()
    expect(paleta.value).toBe(true)
    cerrarPaleta()
    expect(paleta.value).toBe(false)
  })

  it('navega a las secciones sin tocar nada remoto', () => {
    ejecutar({ t: 'seccion', s: 'demo' })
    expect([demoVisible.value, libVisible.value]).toEqual([true, false])
    ejecutar({ t: 'seccion', s: 'biblioteca' })
    expect([demoVisible.value, libVisible.value]).toEqual([false, true])
    ejecutar({ t: 'seccion', s: 'board' })
    expect(viewRequest.value?.view).toBe('board')
  })

  it('un pane se muestra en el tablero y resalta', () => {
    ejecutar({ t: 'pane', id: 'p1' })
    expect(viewRequest.value?.view).toBe('board')
    expect(highlight.value?.paneId).toBe('p1')
  })

  it('una acción de pieza corre lo que la pieza define', () => {
    ejecutar({ t: 'accion', a: 'abrirdemo' })
    expect(demo.correr).toHaveBeenCalledOnce()
    ejecutar({ t: 'accion', a: 'inexistente' })
    expect(demo.correr).toHaveBeenCalledOnce()
  })

  it('el catálogo suma la sección y la acción de la pieza', () => {
    const ids = resultados('demo').flatMap((g) => g.items).map((r) => r.entrada.id)
    expect(ids).toEqual(expect.arrayContaining(['sec:demo', 'acc:abrirdemo']))
  })

  it('abrir una sesión y una terminal usa la navegación existente', () => {
    ejecutar({ t: 'sesion', id: 's1' })
    expect(openSessionId.value).toBe('s1')
    ejecutar({ t: 'terminal', id: 'p9' })
    expect(openTerminalId.value).toBe('p9')
  })

  it('al elegir cierra, guarda el reciente y lo guarda aunque el storage falle', () => {
    vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => { throw new Error('lleno') } })
    paleta.value = true
    const e = construirCatalogo({ board: null, items: [], avisos: [], tema: 'dark' }).find((x) => x.id === 'sec:biblioteca')!
    expect(() => elegir(e)).not.toThrow()
    expect(paleta.value).toBe(false)
    expect(recientes.value).toEqual(['sec:biblioteca'])
    expect(libVisible.value).toBe(true)
  })

  it('con el input vacío muestra recientes y con texto filtra', () => {
    recientes.value = ['sec:biblioteca']
    expect(resultados('')[0].grupo).toBe('reciente')
    expect(resultados('ajus').flatMap((g) => g.items).map((r) => r.entrada.id)).toContain('sec:ajustes')
  })
})
