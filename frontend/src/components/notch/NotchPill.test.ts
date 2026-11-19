import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it, vi } from 'vitest'
import type { ModoNotch } from '../../lib/notchMovimiento'
import { BRILLO_AVISO_KIND } from '../../lib/notchAvisos'
import { RADIO_ABIERTO, RADIO_CERRADO } from '../../lib/notchMovimiento'
import { rectFormaDesdeCaja } from '../../lib/notchFormaPastilla'
import { formaPara } from '../../lib/notchPuente'

vi.hoisted(() => {
  vi.stubGlobal('window', {
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    addEventListener() {},
    screen: { availWidth: 800, availHeight: 600 },
  })
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    disconnect() {}
  })
})

vi.mock('../../motion', async () => {
  const { ref } = await import('vue')
  return {
    gsap: { set() {}, to() {}, fromTo() {}, killTweensOf() {} },
    isSoft: () => true,
    soft: ref(true),
    useGsap: () => ({ run: (fn: () => void) => fn() }),
  }
})

vi.mock('../../state/notch', () => ({
  puente: () => ({ enPrograma: false, tamano() {}, forma() {}, arrastrar() {}, abrirColmena() {}, aviso() {} }),
}))

const renderPill = async (props: { modo: ModoNotch; foco: boolean; brillo?: string | null; pendientes?: number }) => {
  const { default: NotchPill } = await import('./NotchPill.vue')
  return renderToString(
    createSSRApp({
      render: () =>
        h(NotchPill, props, {
          cara: () => h('span', 'cara'),
          cuerpo: () => h('span', 'cuerpo'),
        }),
    }),
  )
}

describe('NotchPill forma (rect lógico)', () => {
  it('al abrir la unión previa cubre el rect destino y usa el radio mayor', () => {
    const innerW = 800
    const caraH = 28
    const cuerpoH = 80
    const bodyPad = 12
    const cerradoW = 120
    const curLeft = innerW / 2 - cerradoW / 2
    const cur = rectFormaDesdeCaja({ left: curLeft, top: 0 }, cerradoW, caraH, RADIO_CERRADO, 0, 0)

    const destinoW = 440
    const destinoH = caraH + cuerpoH + bodyPad
    const destLeft = innerW / 2 - destinoW / 2
    const dest = rectFormaDesdeCaja({ left: destLeft, top: 0 }, destinoW, destinoH, RADIO_ABIERTO, 0, 0)

    const union = formaPara(dest, cur)
    expect(union.radio).toBe(RADIO_ABIERTO)
    expect(union.x).toBeLessThanOrEqual(dest.x + 0.5)
    expect(union.y).toBeLessThanOrEqual(dest.y + 0.5)
    expect(union.x + union.ancho + 0.5).toBeGreaterThanOrEqual(dest.x + dest.ancho)
    expect(union.y + union.alto + 0.5).toBeGreaterThanOrEqual(dest.y + dest.alto)
    expect(union.alto).toBe(destinoH)
  })

  it('el rect final de apertura coincide con la caja de la pastilla', () => {
    const innerW = 1920
    const destinoW = 440
    const destinoH = 200
    const destLeft = innerW / 2 - destinoW / 2
    const fin = rectFormaDesdeCaja({ left: destLeft, top: 0 }, destinoW, destinoH, RADIO_ABIERTO, 0, 0)
    expect(fin).toEqual({
      x: destLeft,
      y: 0,
      ancho: destinoW,
      alto: destinoH,
      radio: RADIO_ABIERTO,
    })
  })
})

describe('NotchPill brillo', () => {
  it('con brillo done muestra la capa decorativa con el color de done', async () => {
    const html = await renderPill({
      modo: 'aviso',
      foco: false,
      brillo: BRILLO_AVISO_KIND.done,
    })
    expect(html).toContain('pill-brillo')
    expect(html).toContain(BRILLO_AVISO_KIND.done)
  })

  it('sin brillo no muestra la capa decorativa', async () => {
    const html = await renderPill({ modo: 'panel', foco: false, brillo: null })
    expect(html).not.toContain('pill-brillo')
  })
})

describe('NotchPill insignia de pendientes', () => {
  it('con pendientes=3 muestra la insignia 3', async () => {
    const html = await renderPill({ modo: 'cerrado', foco: false, pendientes: 3 })
    expect(html).toMatch(/class="insignia"[^>]*>3</)
  })
  it('con 0 no la muestra', async () => {
    const html = await renderPill({ modo: 'cerrado', foco: false, pendientes: 0 })
    expect(html).not.toContain('insignia')
  })
})
