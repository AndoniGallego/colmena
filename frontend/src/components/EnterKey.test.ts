import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it, vi } from 'vitest'
import { enterKeyState, keyShapes, lPath } from '../lib/enterKey'
import EnterKey from './EnterKey.vue'

vi.mock('../motion', () => ({ gsap: {}, haptic: () => {}, isSoft: () => true, ring: () => {}, useGsap: () => ({ run: (f: () => void) => f() }) }))

const render = (props: Record<string, unknown>, slot?: string) =>
  renderToString(createSSRApp({ render: () => h(EnterKey, props, slot ? { default: () => h('i', { class: 'in-hole' }, slot) } : undefined) }))

describe('enterKeyState', () => {
  it('envía por submit con label Enviar', () => {
    expect(enterKeyState({ mode: 'send' })).toEqual({ type: 'submit', label: 'Enviar', disabled: false, glyph: 'enter' })
  })
  it('stop es un button con su label', () => {
    const s = enterKeyState({ mode: 'stop', stopLabel: 'Frenar la sesión' })
    expect([s.type, s.label, s.glyph]).toEqual(['button', 'Frenar la sesión', 'stop'])
  })
  it('busy muestra spinner y disabled se respeta', () => {
    const s = enterKeyState({ mode: 'send', busy: true, disabled: true, label: 'Subiendo archivos' })
    expect([s.glyph, s.disabled, s.label]).toEqual(['spin', true, 'Subiendo archivos'])
  })
})

describe('geometría de la tecla', () => {
  const g = { w: 69, h: 82, wing: 32, stem: 52, r: 10, depth: 3, bevel: 3 }
  const nums = (d: string) => d.match(/-?\d+(\.\d+)?/g)!.map(Number)

  it('la L arranca y cierra en el mismo punto, con la esquina cóncava en el tallo', () => {
    const d = lPath({ x0: 0, y0: 0, x1: 69, y1: 79, wingY: 32, stemX: 17, r: 10, rc: 7 })
    expect(d.startsWith('M10 0H59')).toBe(true)
    expect(d).toContain('A7 7 0 0 0 10 32')
    expect(d.endsWith('Z')).toBe(true)
  })
  it('al crecer solo se estira el tallo: ala, radios y bisel quedan iguales', () => {
    const a = keyShapes(g)
    const b = keyShapes({ ...g, h: 200 })
    const wingPart = (d: string) => d.split('V')[0]
    expect(wingPart(b.body)).toBe(wingPart(a.body))
    expect(wingPart(b.face)).toBe(wingPart(a.face))
    const arcs = (d: string) => (d.match(/A[\d.]+ [\d.]+/g) ?? []).join()
    expect(arcs(b.body)).toBe(arcs(a.body))
    expect(arcs(b.face)).toBe(arcs(a.face))
    expect(b.glyph.x).toBe(a.glyph.x)
  })
  it('la cara queda dentro del cuerpo y el bisel de abajo es más grueso', () => {
    const s = keyShapes(g)
    const body = nums(s.body)
    const face = nums(s.face)
    expect(Math.max(...face)).toBeLessThan(Math.max(...body))
    expect(face[1]).toBeGreaterThan(body[1])
  })
})

describe('EnterKey', () => {
  it('render de envío', async () => {
    const html = await render({})
    expect(html).toContain('type="submit"')
    expect(html).toContain('aria-label="Enviar"')
    expect(html).not.toContain('disabled')
    expect(html).toContain('class="body"')
    expect(html).toContain('class="face"')
    expect(html).not.toMatch(/>\s*(enter|esc)\s*</)
    expect(html).not.toContain('preserveAspectRatio')
  })
  it('deshabilitado sin texto', async () => {
    expect(await render({ disabled: true })).toContain('disabled')
  })
  it('stop: type button, clase stop y label', async () => {
    const html = await render({ mode: 'stop', stopLabel: 'Detener', tone: 'neutral' })
    expect(html).toContain('type="button"')
    expect(html).toContain('aria-label="Detener"')
    expect(html).toContain('class="stop enter"')
    expect(html).toContain('tone-neutral')
  })
  it('el slot va en el hueco', async () => {
    const html = await render({}, 'mic')
    expect(html).toMatch(/class="hole"[^>]*>(<!--\[-->)?<i class="in-hole">mic<\/i>/)
  })
})
