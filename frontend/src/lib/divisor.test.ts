import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { anchoPorTecla, cargarAncho, clampAncho, guardarAncho, limitesDe, useAncho } from './divisor'

function fakeStorage() {
  const m = new Map<string, string>()
  return {
    getItem: (k: string) => (m.has(k) ? m.get(k)! : null),
    setItem: (k: string, v: string) => void m.set(k, v),
    removeItem: (k: string) => void m.delete(k),
    clear: () => m.clear(),
    m,
  }
}

let store: ReturnType<typeof fakeStorage>
beforeEach(() => {
  store = fakeStorage()
  vi.stubGlobal('localStorage', store)
})
afterEach(() => vi.unstubAllGlobals())

const opts = { clave: 'orq.anchoTablero', min: 320, minResto: 440, porDefecto: (c: number) => c * 0.4 }

describe('límites y clamp', () => {
  it('el máximo deja lugar al otro panel', () => {
    expect(limitesDe(1440, 320, 440)).toEqual({ min: 320, max: 1000 })
  })
  it('si no entra nada, el máximo nunca baja del mínimo', () => {
    expect(limitesDe(500, 320, 440)).toEqual({ min: 320, max: 320 })
  })
  it('clampa y redondea', () => {
    const lim = { min: 320, max: 1000 }
    expect(clampAncho(100, lim)).toBe(320)
    expect(clampAncho(5000, lim)).toBe(1000)
    expect(clampAncho(480.6, lim)).toBe(481)
  })
})

describe('teclado', () => {
  const lim = { min: 320, max: 1000 }
  it('las flechas mueven de a 24px', () => {
    expect(anchoPorTecla('ArrowRight', 500, lim)).toBe(524)
    expect(anchoPorTecla('ArrowLeft', 500, lim)).toBe(476)
  })
  it('con el panel a la derecha las flechas se invierten', () => {
    expect(anchoPorTecla('ArrowRight', 500, lim, 24, -1)).toBe(476)
  })
  it('Home y End van a los extremos', () => {
    expect(anchoPorTecla('Home', 500, lim)).toBe(320)
    expect(anchoPorTecla('End', 500, lim)).toBe(1000)
  })
  it('no se pasa de los extremos', () => {
    expect(anchoPorTecla('ArrowLeft', 330, lim)).toBe(320)
    expect(anchoPorTecla('ArrowRight', 990, lim)).toBe(1000)
  })
  it('otras teclas no le corresponden', () => {
    expect(anchoPorTecla('Enter', 500, lim)).toBeNull()
  })
})

describe('persistencia', () => {
  it('guarda, lee y borra', () => {
    guardarAncho('k', 512.4)
    expect(store.m.get('k')).toBe('512')
    expect(cargarAncho('k')).toBe(512)
    guardarAncho('k', null)
    expect(cargarAncho('k')).toBeNull()
  })
  it('ignora basura', () => {
    store.setItem('k', 'abc')
    expect(cargarAncho('k')).toBeNull()
    store.setItem('k', '-4')
    expect(cargarAncho('k')).toBeNull()
  })
  it('sin storage no rompe', () => {
    vi.stubGlobal('localStorage', {
      getItem: () => {
        throw new Error('bloqueado')
      },
      setItem: () => {
        throw new Error('bloqueado')
      },
      removeItem: () => {
        throw new Error('bloqueado')
      },
    })
    expect(cargarAncho('k')).toBeNull()
    expect(() => guardarAncho('k', 400)).not.toThrow()
    const a = useAncho(opts)
    a.contenedor.value = 1440
    a.fijar(600)
    expect(a.ancho.value).toBe(600)
  })
})

describe('useAncho', () => {
  it('sin nada guardado sigue la proporción del contenedor', () => {
    const a = useAncho(opts)
    a.contenedor.value = 1440
    expect(a.ancho.value).toBe(576)
    a.contenedor.value = 1920
    expect(a.ancho.value).toBe(768)
  })
  it('arrastrar no guarda hasta fijar', () => {
    const a = useAncho(opts)
    a.contenedor.value = 1440
    a.ver(700)
    expect(a.ancho.value).toBe(700)
    expect(store.m.has('orq.anchoTablero')).toBe(false)
    a.fijar()
    expect(store.m.get('orq.anchoTablero')).toBe('700')
  })
  it('levanta lo guardado y lo clampa al achicar la ventana', () => {
    store.setItem('orq.anchoTablero', '900')
    const a = useAncho(opts)
    a.contenedor.value = 1920
    expect(a.ancho.value).toBe(900)
    a.contenedor.value = 1200
    expect(a.ancho.value).toBe(760)
    a.contenedor.value = 1920
    expect(a.ancho.value).toBe(900)
  })
  it('restablecer olvida lo guardado', () => {
    const a = useAncho(opts)
    a.contenedor.value = 1440
    a.fijar(800)
    a.restablecer()
    expect(a.ancho.value).toBe(576)
    expect(store.m.has('orq.anchoTablero')).toBe(false)
  })
  it('el teclado mueve, guarda y respeta los extremos', () => {
    const a = useAncho(opts)
    a.contenedor.value = 1440
    expect(a.teclado('ArrowRight')).toBe(true)
    expect(a.ancho.value).toBe(600)
    expect(store.m.get('orq.anchoTablero')).toBe('600')
    a.teclado('End')
    expect(a.ancho.value).toBe(1000)
    a.teclado('Home')
    expect(a.ancho.value).toBe(320)
    expect(a.teclado('a')).toBe(false)
  })
})
