// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Nota } from '../api/types'

const h = vi.hoisted(() => ({ soft: { value: false }, to: vi.fn() }))
vi.mock('../motion', () => ({
  gsap: { to: h.to, set() {}, killTweensOf() {} },
  isSoft: () => h.soft.value,
}))

const { default: NotaTarjeta } = await import('./NotaTarjeta.vue')

const nota: Nota = {
  id: 'a',
  tipo: 'recordatorio',
  texto: 'Pendiente',
  hecha_at: null,
  creada_at: '2026-11-18T10:00:00Z',
  editada_at: '2026-11-18T10:00:00Z',
  origen: null,
}
const ANCHO = 300

function montar(props: { deslizable?: boolean } = { deslizable: true }) {
  const w = mount(NotaTarjeta, { props: { nota, sesionViva: false, ...props }, attachTo: document.body })
  const el = w.find('.nota').element as HTMLElement
  el.getBoundingClientRect = () => ({ left: 0, top: 0, width: ANCHO, height: 80, right: ANCHO, bottom: 80, x: 0, y: 0, toJSON() {} })
  return w
}
const ptr = (w: ReturnType<typeof montar>, tipo: 'pointerdown' | 'pointermove' | 'pointerup', x: number, y = 0) => {
  const Ev = (window as unknown as { PointerEvent?: typeof MouseEvent }).PointerEvent ?? MouseEvent
  w.find('.nota').element.dispatchEvent(new Ev(tipo, { clientX: x, clientY: y, bubbles: true }))
}
const arrastrar = (w: ReturnType<typeof montar>, dx: number, dy = 0) => {
  ptr(w, 'pointerdown', 20, 20)
  ptr(w, 'pointermove', 20 + dx, 20 + dy)
  ptr(w, 'pointerup', 20 + dx, 20 + dy)
}

beforeEach(() => {
  document.body.innerHTML = ''
  h.soft.value = false
  h.to.mockReset()
})

describe('NotaTarjeta: deslizar para completar', () => {
  it('soltar pasada la mitad completa la nota', () => {
    const w = montar()
    arrastrar(w, ANCHO * 0.6)
    expect(w.emitted('completar')).toEqual([[true]])
  })

  it('soltar antes de la mitad no completa y vuelve a 0 en 0,25 s', () => {
    const w = montar()
    arrastrar(w, ANCHO * 0.3)
    expect(w.emitted('completar')).toBeUndefined()
    expect(h.to).toHaveBeenCalledWith(w.find('.nota').element, expect.objectContaining({ x: 0, duration: 0.25 }))
  })

  it('mientras arrastra se mueve la tarjeta y crece la capa de miel', () => {
    const w = montar()
    ptr(w, 'pointerdown', 20, 20)
    ptr(w, 'pointermove', 20 + ANCHO / 2, 20)
    expect((w.find('.nota').element as HTMLElement).style.transform).toContain(`translateX(${ANCHO / 2}px)`)
    expect((w.find('.nota-deslizar').element as HTMLElement).style.transform).toContain('scaleX(0.5)')
  })

  it('solo se mueve a la derecha', () => {
    const w = montar()
    ptr(w, 'pointerdown', 100, 20)
    ptr(w, 'pointermove', 40, 20)
    expect((w.find('.nota').element as HTMLElement).style.transform).toBe('')
  })

  it('un arrastre mayormente vertical no mueve ni completa, aunque después se desvíe', () => {
    const w = montar()
    ptr(w, 'pointerdown', 20, 20)
    ptr(w, 'pointermove', 25, 70)
    ptr(w, 'pointermove', 20 + ANCHO, 75)
    ptr(w, 'pointerup', 20 + ANCHO, 75)
    expect((w.find('.nota').element as HTMLElement).style.transform).toBe('')
    expect(w.emitted('completar')).toBeUndefined()
  })

  it('un arrastre no abre la hoja, un toque sí', async () => {
    const w = montar()
    arrastrar(w, ANCHO * 0.3)
    await w.find('button.nota-abrir').trigger('click')
    expect(w.emitted('seleccionar')).toBeUndefined()
    ptr(w, 'pointerdown', 20, 20)
    ptr(w, 'pointerup', 20, 20)
    await w.find('button.nota-abrir').trigger('click')
    expect(w.emitted('seleccionar')).toHaveLength(1)
  })

  it('una vez tomado el gesto, el arrastre no le llega al deslizar entre pestañas de la app', () => {
    const w = montar()
    const padre = vi.fn()
    document.body.addEventListener('pointermove', padre)
    ptr(w, 'pointerdown', 20, 20)
    ptr(w, 'pointermove', 20 + ANCHO * 0.3, 20)
    ptr(w, 'pointermove', 20 + ANCHO * 0.4, 20)
    document.body.removeEventListener('pointermove', padre)
    expect(padre).not.toHaveBeenCalled()
  })

  it('deslizar a la izquierda no mueve la tarjeta y le deja el gesto a la app', () => {
    const w = montar()
    const abajo = vi.fn()
    const mueve = vi.fn()
    document.body.addEventListener('pointerdown', abajo)
    document.body.addEventListener('pointermove', mueve)
    ptr(w, 'pointerdown', 200, 20)
    ptr(w, 'pointermove', 200 - ANCHO * 0.3, 20)
    ptr(w, 'pointermove', 200 - ANCHO * 0.4, 20)
    document.body.removeEventListener('pointerdown', abajo)
    document.body.removeEventListener('pointermove', mueve)
    expect(abajo).toHaveBeenCalledTimes(1)
    expect(mueve).toHaveBeenCalledTimes(2)
    expect((w.find('.nota').element as HTMLElement).style.transform).toBe('')
  })

  it('un segundo dedo no traba el gesto del primero', () => {
    const w = montar()
    const Ev = (window as unknown as { PointerEvent?: typeof MouseEvent }).PointerEvent ?? MouseEvent
    const el = w.find('.nota').element
    const ev = (tipo: string, x: number, id: number, primario: boolean) => {
      const e = new Ev(tipo, { clientX: x, clientY: 20, bubbles: true })
      Object.defineProperty(e, 'pointerId', { value: id })
      Object.defineProperty(e, 'isPrimary', { value: primario })
      el.dispatchEvent(e)
    }
    ev('pointerdown', 20, 1, true)
    ev('pointermove', 20 + ANCHO * 0.3, 1, true)
    ev('pointerdown', 100, 2, false)
    ev('pointermove', 20 + ANCHO * 0.7, 1, true)
    ev('pointerup', 20 + ANCHO * 0.7, 1, true)
    expect(w.emitted('completar')).toEqual([[true]])
    expect(w.find('.nota').classes()).not.toContain('arrastrando')
  })

  it('mientras se arrastra pasa por encima de las vecinas y al completar deja de hacerlo', () => {
    const w = montar()
    ptr(w, 'pointerdown', 20, 20)
    ptr(w, 'pointermove', 20 + ANCHO * 0.3, 20)
    expect(w.find('.nota').classes()).toContain('arrastrando')
    ptr(w, 'pointermove', 20 + ANCHO * 0.7, 20)
    ptr(w, 'pointerup', 20 + ANCHO * 0.7, 20)
    expect(w.find('.nota').classes()).not.toContain('arrastrando')
  })

  it('sin deslizable el toque sigue llegando a la app', () => {
    const w = montar({ deslizable: false })
    const padre = vi.fn()
    document.body.addEventListener('pointerdown', padre)
    ptr(w, 'pointerdown', 20, 20)
    document.body.removeEventListener('pointerdown', padre)
    expect(padre).toHaveBeenCalledTimes(1)
  })

  it('sin deslizable el gesto no hace nada', () => {
    const w = montar({ deslizable: false })
    arrastrar(w, ANCHO * 0.8)
    expect(w.emitted('completar')).toBeUndefined()
    expect((w.find('.nota').element as HTMLElement).style.transform).toBe('')
  })

  it('con movimiento suave el gesto anda y la vuelta no rebota', () => {
    h.soft.value = true
    const w = montar()
    arrastrar(w, ANCHO * 0.8)
    expect(w.emitted('completar')).toEqual([[true]])
    h.to.mockReset()
    const w2 = montar()
    arrastrar(w2, ANCHO * 0.2)
    const vars = h.to.mock.calls[0][1] as { ease: string }
    expect(vars.ease).not.toMatch(/back|elastic/)
  })

  it('el botón de completar sigue andando', async () => {
    const w = montar()
    await w.find('button.nota-tilde').trigger('click')
    expect(w.emitted('completar')).toEqual([[true]])
  })
})
