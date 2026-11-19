// @vitest-environment jsdom
import { createSSRApp, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../motion', () => ({
  gsap: { fromTo: vi.fn(), to: vi.fn(), set: vi.fn(), killTweensOf: vi.fn() },
  haptic: vi.fn(),
  isSoft: () => true,
  useGsap: () => ({ run: (fn: () => void) => fn() }),
}))
vi.mock('../state/biblioteca', () => ({
  cachedLibItem: vi.fn(async () => null),
  fresh: vi.fn(),
  openInLibrary: vi.fn(),
}))
vi.mock('./Icon.vue', () => ({ default: { name: 'Icon', render: () => null } }))
vi.mock('./BibImage.vue', () => ({ default: { name: 'BibImage', template: '<div class="zoom" />' } }))

const { default: FotoCarrusel } = await import('./FotoCarrusel.vue')

describe('FotoCarrusel estructura', () => {
  it('con 1 foto, .fc-stage tiene .fc-pic como hijo con área central y slots laterales', async () => {
    const ctx: { teleports?: Record<string, string> } = {}
    const app = createSSRApp({
      render: () =>
        h(FotoCarrusel, {
          fotos: [{ id: 'f1' }],
          start: 0,
          from: null,
        }),
    })
    await renderToString(app, ctx)
    const html = ctx.teleports?.body ?? ''
    expect(html).toContain('class="fc-stage"')
    expect(html).toContain('class="fc-pic"')
    expect(html).toContain('class="fc-slot fc-start"')
    expect(html).toContain('class="fc-slot fc-end"')
    expect(html).toContain('No pude cargar la captura')
  })

  it('con varias fotos incluye botones de navegación', async () => {
    const ctx: { teleports?: Record<string, string> } = {}
    const app = createSSRApp({
      render: () =>
        h(FotoCarrusel, {
          fotos: [{ id: 'a' }, { id: 'b' }],
          start: 0,
          from: null,
        }),
    })
    await renderToString(app, ctx)
    const html = ctx.teleports?.body ?? ''
    expect(html).toContain('aria-label="Anterior"')
    expect(html).toContain('aria-label="Siguiente"')
  })
})

describe('FotoCarrusel teclado', () => {
  it('con foco en body ArrowRight en window avanza la foto', async () => {
    const w = mount(FotoCarrusel, {
      props: { fotos: [{ id: 'a' }, { id: 'b' }], start: 0, from: null },
      attachTo: document.body,
    })
    await flushPromises()
    ;(document.body as HTMLElement).focus()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }))
    await flushPromises()
    const count = document.body.querySelector('.fc-count')
    expect(count?.textContent).toBe('2 / 2')
    w.unmount()
  })

  it('las flechas no cambian la foto si se escribe en otra hoja abierta encima', async () => {
    const w = mount(FotoCarrusel, {
      props: { fotos: [{ id: 'a' }, { id: 'b' }], start: 0, from: null },
      attachTo: document.body,
    })
    await flushPromises()
    const otra = document.createElement('div')
    otra.setAttribute('aria-modal', 'true')
    const input = document.createElement('input')
    otra.appendChild(input)
    document.body.appendChild(otra)
    input.focus()
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }))
    await flushPromises()
    expect(document.body.querySelector('.fc-count')?.textContent).toBe('1 / 2')
    otra.remove()
    w.unmount()
  })

  it('las flechas ya manejadas por otro (defaultPrevented) no cambian la foto', async () => {
    const w = mount(FotoCarrusel, {
      props: { fotos: [{ id: 'a' }, { id: 'b' }], start: 0, from: null },
      attachTo: document.body,
    })
    await flushPromises()
    const ev = new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true, cancelable: true })
    ev.preventDefault()
    window.dispatchEvent(ev)
    await flushPromises()
    expect(document.body.querySelector('.fc-count')?.textContent).toBe('1 / 2')
    w.unmount()
  })
})

function ptr(type: string, target: Element, x: number, y: number, t: number, id = 1, pointerType = 'touch') {
  const e = new Event(type, { bubbles: true }) as Event & Record<string, unknown>
  Object.assign(e, { pointerId: id, clientX: x, clientY: y, pointerType, isPrimary: id === 1 })
  Object.defineProperty(e, 'timeStamp', { value: t })
  target.dispatchEvent(e)
}

async function montar(start = 0) {
  const w = mount(FotoCarrusel, {
    props: { fotos: [{ id: 'a' }, { id: 'b' }, { id: 'c' }], start, from: null },
    attachTo: document.body,
  })
  await flushPromises()
  return { w, sheet: document.body.querySelector('.fc-sheet') as HTMLElement, pic: document.body.querySelector('.fc-pic') as HTMLElement }
}
const tx = (el: HTMLElement) => parseFloat(/translate\((-?[\d.]+)px/.exec(el.style.transform)?.[1] ?? 'NaN')
const cuenta = () => document.body.querySelector('.fc-count')?.textContent

describe('FotoCarrusel gestos', () => {
  it('un swipe horizontal largo cambia de foto', async () => {
    const { w, sheet, pic } = await montar()
    ptr('pointerdown', pic, 200, 300, 0)
    ptr('pointermove', pic, 150, 302, 100)
    ptr('pointermove', pic, 90, 304, 200)
    ptr('pointerup', pic, 90, 304, 300)
    await flushPromises()
    expect(cuenta()).toBe('2 / 3')
    expect(sheet.classList.contains('fc-sheet')).toBe(true)
    w.unmount()
  })

  it('un swipe corto y lento vuelve y no cambia', async () => {
    const { w, pic } = await montar()
    ptr('pointerdown', pic, 200, 300, 0)
    ptr('pointermove', pic, 170, 300, 1000)
    expect(tx(pic)).toBe(-30)
    ptr('pointerup', pic, 170, 300, 2000)
    await flushPromises()
    expect(cuenta()).toBe('1 / 3')
    w.unmount()
  })

  it('en la primera foto el tirón hacia atrás tiene resistencia y no cambia', async () => {
    const { w, pic } = await montar()
    ptr('pointerdown', pic, 100, 300, 0)
    ptr('pointermove', pic, 300, 300, 100)
    expect(tx(pic)).toBeGreaterThan(0)
    expect(tx(pic)).toBeLessThan(100)
    ptr('pointerup', pic, 300, 300, 200)
    await flushPromises()
    expect(cuenta()).toBe('1 / 3')
    w.unmount()
  })

  it('con dos punteros no cambia de foto ni cierra', async () => {
    const { w, pic } = await montar()
    ptr('pointerdown', pic, 200, 300, 0)
    ptr('pointerdown', pic, 260, 300, 10, 2)
    ptr('pointermove', pic, 50, 300, 100)
    ptr('pointerup', pic, 50, 300, 200)
    ptr('pointerup', pic, 260, 300, 210, 2)
    await flushPromises()
    expect(cuenta()).toBe('1 / 3')
    expect(w.emitted('close')).toBeUndefined()
    w.unmount()
  })

  it('con la imagen ampliada el gesto no cambia de foto', async () => {
    const { w, pic } = await montar()
    const z = document.createElement('div')
    z.className = 'zoom zoomed'
    pic.appendChild(z)
    ptr('pointerdown', pic, 200, 300, 0)
    ptr('pointermove', pic, 50, 300, 100)
    ptr('pointerup', pic, 50, 300, 200)
    await flushPromises()
    expect(cuenta()).toBe('1 / 3')
    w.unmount()
  })

  it('un swipe vertical hacia abajo de más de 90px cierra', async () => {
    const { w, pic } = await montar()
    ptr('pointerdown', pic, 200, 100, 0)
    ptr('pointermove', pic, 205, 150, 100)
    ptr('pointermove', pic, 205, 230, 200)
    ptr('pointerup', pic, 205, 230, 300)
    expect(w.emitted('close')).toHaveLength(1)
    w.unmount()
  })

  it('un gesto que empieza sobre la imagen no le quita la captura a BibImage', async () => {
    const { w, sheet, pic } = await montar()
    const cap = vi.fn()
    sheet.setPointerCapture = cap
    const zoom = document.createElement('div')
    zoom.className = 'zoom'
    pic.appendChild(zoom)
    ptr('pointerdown', zoom, 200, 300, 0)
    ptr('pointermove', zoom, 150, 302, 100)
    ptr('pointermove', zoom, 90, 304, 200)
    expect(cap).not.toHaveBeenCalled()
    ptr('pointerup', zoom, 90, 304, 300)
    await flushPromises()
    expect(cuenta()).toBe('2 / 3')
    w.unmount()
  })

  it('fuera de la imagen el gesto sí captura en la hoja', async () => {
    const { w, sheet, pic } = await montar()
    const cap = vi.fn()
    sheet.setPointerCapture = cap
    ptr('pointerdown', pic, 200, 300, 0)
    ptr('pointermove', pic, 150, 302, 100)
    expect(cap).toHaveBeenCalledWith(1)
    ptr('pointerup', pic, 150, 302, 200)
    w.unmount()
  })

  it('con mouse arrastrar no cambia de foto ni cierra', async () => {
    const { w, pic } = await montar()
    ptr('pointerdown', pic, 200, 100, 0, 1, 'mouse')
    ptr('pointermove', pic, 50, 102, 100, 1, 'mouse')
    expect(pic.style.transform).toBe('')
    ptr('pointerup', pic, 50, 102, 200, 1, 'mouse')
    ptr('pointerdown', pic, 200, 100, 300, 1, 'mouse')
    ptr('pointermove', pic, 202, 300, 400, 1, 'mouse')
    ptr('pointerup', pic, 202, 300, 500, 1, 'mouse')
    await flushPromises()
    expect(cuenta()).toBe('1 / 3')
    expect(w.emitted('close')).toBeUndefined()
    w.unmount()
  })

  it('un flick que se frena antes de soltar no cambia de foto', async () => {
    const { w, pic } = await montar()
    ptr('pointerdown', pic, 200, 300, 0)
    ptr('pointermove', pic, 190, 300, 10)
    ptr('pointermove', pic, 170, 300, 20)
    ptr('pointerup', pic, 170, 300, 500)
    await flushPromises()
    expect(cuenta()).toBe('1 / 3')
    w.unmount()
  })
})
