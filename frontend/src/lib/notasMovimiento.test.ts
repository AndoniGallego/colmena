// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'

window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} })) as never
const mov = await import('./notasMovimiento')
const { gsap, setMotion } = await import('../motion')

const scrollerCon = (...ts: string[]) => {
  const s = document.createElement('div')
  s.getClientRects = (() => [{}]) as never
  for (const t of ts) {
    const a = document.createElement('article')
    a.dataset.ts = t
    a.scrollIntoView = vi.fn()
    s.append(a)
  }
  document.body.append(s)
  return s
}

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
  document.body.innerHTML = ''
})

describe('saltarAMensaje', () => {
  it('hace scroll al mensaje, lo resalta 1,5 s y después lo suelta', () => {
    vi.useFakeTimers()
    const s = scrollerCon('a', 'b')
    const b = s.querySelectorAll('article')[1]
    expect(mov.saltarAMensaje(s, 'b')).toBe(true)
    expect(b.scrollIntoView).toHaveBeenCalled()
    expect(b.classList.contains('resaltado')).toBe(true)
    vi.advanceTimersByTime(1400)
    expect(b.classList.contains('resaltado')).toBe(true)
    vi.advanceTimersByTime(200)
    expect(b.classList.contains('resaltado')).toBe(false)
  })
  it('un ts inexistente o vacío devuelve false y no toca nada', () => {
    const s = scrollerCon('a')
    expect(mov.saltarAMensaje(s, 'zzz')).toBe(false)
    expect(mov.saltarAMensaje(s, '')).toBe(false)
    expect(s.querySelector('.resaltado')).toBeNull()
  })
})

describe('resolverSalto', () => {
  const salto = { sid: 's1', ts: 'b' }
  it('espera si no hay scroller, no cargó o no hay mensajes renderizados', () => {
    const s = scrollerCon('b')
    expect(mov.resolverSalto(null, salto, 's1', true)).toBe('esperar')
    expect(mov.resolverSalto(s, salto, 's1', false)).toBe('esperar')
    expect(mov.resolverSalto(document.createElement('div'), salto, 's1', true)).toBe('esperar')
  })
  it('espera si el scroller está oculto (sin cajas)', () => {
    const s = scrollerCon('b')
    s.getClientRects = (() => []) as never
    expect(mov.resolverSalto(s, salto, 's1', true)).toBe('esperar')
  })
  it('espera si la sesión abierta es otra', () => {
    expect(mov.resolverSalto(scrollerCon('b'), salto, 's2', true)).toBe('esperar')
  })
  it('salta cuando el mensaje está y avisa ausente cuando no', () => {
    const s = scrollerCon('a', 'b')
    expect(mov.resolverSalto(s, salto, 's1', true)).toBe('saltado')
    expect(mov.resolverSalto(s, { sid: 's1', ts: 'nope' }, 's1', true)).toBe('ausente')
  })
})

describe('guardarEnNotas', () => {
  const origenAlto = (alto: number) => {
    const o = document.createElement('div')
    o.textContent = 'largo'
    o.getBoundingClientRect = () => ({ left: 10, top: 10, width: 300, height: alto, right: 310, bottom: 10 + alto, x: 10, y: 10, toJSON() {} })
    document.body.append(o)
    return o
  }
  const destino = () => {
    const d = document.createElement('button')
    d.getBoundingClientRect = () => ({ left: 50, top: 50, width: 40, height: 40, right: 90, bottom: 90, x: 50, y: 50, toJSON() {} })
    document.body.append(d)
    return d
  }
  it('el clon que vuela no pasa de 120px de alto', () => {
    void mov.guardarEnNotas(origenAlto(900), destino())
    const clon = document.querySelector<HTMLElement>('.nota-vuelo')!
    expect(clon).not.toBeNull()
    expect(parseInt(clon.style.height)).toBeLessThanOrEqual(120)
    expect(clon.style.overflow).toBe('hidden')
    expect(clon.classList.contains('nota-vuelo-tarjeta')).toBe(true)
    expect(clon.style.background).toContain('--surface-2')
    expect(clon.style.boxShadow).toContain('--miel')
    expect(clon.querySelector('.nota-vuelo-fade')).not.toBeNull()
  })
  it('un clon corto no lleva velo de recorte', () => {
    void mov.guardarEnNotas(origenAlto(60), destino())
    expect(document.querySelector('.nota-vuelo-fade')).toBeNull()
  })
  it('el original queda quieto: solo se mueve el clon', () => {
    const o = origenAlto(100)
    void mov.guardarEnNotas(o, destino())
    expect(document.querySelector('.nota-vuelo')).not.toBe(o)
    expect(o.style.position).toBe('')
  })
  it('si GSAP falla saca el clon y resuelve sin lanzar', async () => {
    vi.spyOn(gsap, 'timeline').mockImplementation(() => {
      throw new Error('boom')
    })
    await expect(mov.guardarEnNotas(origenAlto(100), destino())).resolves.toBeUndefined()
    expect(document.querySelector('.nota-vuelo')).toBeNull()
  })
})

describe('cascadaEntrada', () => {
  const tarjetas = (k: number) =>
    Array.from({ length: k }, () => {
      const t = document.createElement('article')
      document.body.append(t)
      return t
    })
  afterEach(() => setMotion('full'))

  it('anima solo las primeras 12 con desplazamiento, escala y escalonado', () => {
    setMotion('full')
    const fromTo = vi.spyOn(gsap, 'fromTo').mockImplementation((() => {}) as never)
    const ts = tarjetas(15)
    mov.cascadaEntrada(ts)
    const [els, desde, hasta] = fromTo.mock.calls[0] as unknown as [Element[], Record<string, number>, Record<string, number>]
    expect(els).toHaveLength(12)
    expect(els).toEqual(ts.slice(0, 12))
    expect(desde).toMatchObject({ opacity: 0, y: 12, scale: 0.96 })
    expect(hasta).toMatchObject({ opacity: 1, y: 0, scale: 1, duration: 0.32, stagger: 0.035 })
  })
  it('con movimiento suave es solo un fundido', () => {
    setMotion('soft')
    const fromTo = vi.spyOn(gsap, 'fromTo').mockImplementation((() => {}) as never)
    mov.cascadaEntrada(tarjetas(3))
    const [, desde, hasta] = fromTo.mock.calls[0] as unknown as [Element[], Record<string, number>, Record<string, number>]
    expect(desde).toEqual({ opacity: 0 })
    expect(hasta).not.toHaveProperty('y')
    expect(hasta).not.toHaveProperty('scale')
  })
  it('sin tarjetas no hace nada', () => {
    const fromTo = vi.spyOn(gsap, 'fromTo').mockImplementation((() => {}) as never)
    mov.cascadaEntrada([])
    expect(fromTo).not.toHaveBeenCalled()
  })
})

describe('rebotarContador', () => {
  it('rebota 1 a 1.12 a 1, y con movimiento suave no hace nada', () => {
    setMotion('full')
    const to = vi.spyOn(gsap, 'to').mockImplementation((() => {}) as never)
    const hex = document.createElement('span')
    mov.rebotarContador(hex)
    expect(to).toHaveBeenCalledWith(hex, expect.objectContaining({ scale: 1.12, yoyo: true, repeat: 1 }))
    to.mockClear()
    setMotion('soft')
    mov.rebotarContador(hex)
    expect(to).not.toHaveBeenCalled()
    setMotion('full')
  })
})

describe('despedir y reacomodar en el celu', () => {
  const tarjeta = () => {
    const t = document.createElement('article')
    document.body.append(t)
    return t
  }
  afterEach(() => setMotion('full'))

  it('despedir en el celu achica y funde sin girar', () => {
    setMotion('full')
    const to = vi.spyOn(gsap, 'to').mockImplementation((() => {}) as never)
    void mov.despedir([tarjeta()], true)
    const vars = to.mock.calls[0][1] as Record<string, number>
    expect(vars).toMatchObject({ opacity: 0 })
    expect(vars.scale).toBeGreaterThan(0.5)
    expect(vars).not.toHaveProperty('rotation')
  })
  it('despedir con movimiento suave solo funde', () => {
    setMotion('soft')
    const to = vi.spyOn(gsap, 'to').mockImplementation((() => {}) as never)
    void mov.despedir([tarjeta()], true)
    const vars = to.mock.calls[0][1] as Record<string, number>
    expect(vars).toMatchObject({ opacity: 0 })
    expect(vars).not.toHaveProperty('scale')
  })
  it('reacomodar en el celu usa Flip y las que entran aparecen con fundido y escala sin girar', async () => {
    setMotion('full')
    const { Flip } = await import('../motion')
    const from = vi.spyOn(Flip, 'from').mockImplementation((() => {}) as never)
    vi.spyOn(Flip, 'getState').mockImplementation((() => ({})) as never)
    const grid = document.createElement('div')
    grid.append(tarjeta())
    document.body.append(grid)
    await mov.reacomodar(grid, () => {}, true)
    const opts = from.mock.calls[0][1] as { onEnter: (els: Element[]) => void; duration: number }
    expect(opts.duration).toBeLessThan(0.6)
    const fromTo = vi.spyOn(gsap, 'fromTo').mockImplementation((() => {}) as never)
    opts.onEnter([tarjeta()])
    const desde = (fromTo.mock.calls[0] as unknown[])[1] as Record<string, number>
    expect(desde).toMatchObject({ opacity: 0 })
    expect(desde.scale).toBeGreaterThan(0.5)
    expect(desde).not.toHaveProperty('rotation')
  })
})

describe('levantarTarjeta', () => {
  const tarjeta = () => {
    const t = document.createElement('article')
    const sombra = document.createElement('i')
    sombra.className = 'nota-sombra'
    t.append(sombra)
    document.body.append(t)
    return t
  }
  afterEach(() => setMotion('full'))

  it('sube a 1.03 con sombra en 0.14 s y resuelve al terminar', async () => {
    setMotion('full')
    const to = vi.spyOn(gsap, 'to').mockImplementation(((_t: unknown, v: { onComplete?: () => void }) => v.onComplete?.()) as never)
    const t = tarjeta()
    await mov.levantarTarjeta(t)
    expect(to).toHaveBeenCalledWith(t, expect.objectContaining({ scale: 1.03, duration: 0.14 }))
    expect(to).toHaveBeenCalledWith(t.querySelector('.nota-sombra'), expect.objectContaining({ opacity: 1, duration: 0.14 }))
  })
  it('si cortan la animación (empezó a deslizar) igual resuelve', async () => {
    setMotion('full')
    const t = tarjeta()
    const p = mov.levantarTarjeta(t)
    gsap.killTweensOf(t)
    const r = await Promise.race([p.then(() => 'resolvio'), new Promise((ok) => setTimeout(() => ok('colgada'), 400))])
    expect(r).toBe('resolvio')
  })
  it('con movimiento suave resuelve sin animar', async () => {
    setMotion('soft')
    const to = vi.spyOn(gsap, 'to').mockImplementation((() => {}) as never)
    await mov.levantarTarjeta(tarjeta())
    expect(to).not.toHaveBeenCalled()
  })
  it('bajarTarjeta vuelve a 1 y apaga la sombra', () => {
    setMotion('full')
    const to = vi.spyOn(gsap, 'to').mockImplementation((() => {}) as never)
    const t = tarjeta()
    mov.bajarTarjeta(t)
    expect(to).toHaveBeenCalledWith(t, expect.objectContaining({ scale: 1 }))
    expect(to).toHaveBeenCalledWith(t.querySelector('.nota-sombra'), expect.objectContaining({ opacity: 0 }))
  })
})
