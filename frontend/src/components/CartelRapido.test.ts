// @vitest-environment jsdom
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CartelRapido from './CartelRapido.vue'
import { vCartel } from '../lib/vCartel'
import { cartel, reiniciarCartel } from '../state/cartel'

const Arnes = defineComponent({
  components: { CartelRapido },
  directives: { cartel: vCartel },
  template: `
    <div>
      <button id="a" aria-label="Ajustes" v-cartel="{ nombre: 'Ajustes', desc: 'Apariencia y avisos' }">A</button>
      <button id="b" aria-label="Kit" v-cartel="{ nombre: 'Kit', desc: 'Reglas y skills' }">B</button>
      <CartelRapido />
    </div>`,
})

const texto = () => document.body.querySelector('.cartel')?.textContent ?? ''

function montar() {
  return mount(Arnes, { attachTo: document.body })
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal('matchMedia', (q: string) => ({ matches: q.includes('hover'), addEventListener() {}, removeEventListener() {} }))
  reiniciarCartel()
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('cartel rápido', () => {
  it('con el mouse aparece tras ~150 ms con nombre y descripción', async () => {
    const w = montar()
    const a = w.get('#a')
    await a.trigger('pointerenter', { pointerType: 'mouse' })
    vi.advanceTimersByTime(100)
    await w.vm.$nextTick()
    expect(texto()).toBe('')
    vi.advanceTimersByTime(60)
    await w.vm.$nextTick()
    expect(texto()).toContain('Ajustes')
    expect(texto()).toContain('Apariencia y avisos')
    await a.trigger('pointerleave')
    await w.vm.$nextTick()
    expect(cartel.visible).toBe(false)
    w.unmount()
  })

  it('con el teclado aparece enseguida y Esc lo cierra', async () => {
    const w = montar()
    const a = w.get('#a')
    await a.trigger('focus')
    await w.vm.$nextTick()
    expect(texto()).toContain('Apariencia y avisos')
    await a.trigger('keydown', { key: 'Escape' })
    await w.vm.$nextTick()
    expect(cartel.visible).toBe(false)
    w.unmount()
  })

  it('el foco que viene de un clic con el mouse no lo abre', async () => {
    const w = montar()
    const a = w.get('#a')
    await a.trigger('pointerdown')
    await a.trigger('focus')
    expect(cartel.visible).toBe(false)
    w.unmount()
  })

  it('si ya hay uno abierto, el siguiente sale sin demora', async () => {
    const w = montar()
    await w.get('#a').trigger('pointerenter', { pointerType: 'mouse' })
    vi.advanceTimersByTime(160)
    await w.get('#a').trigger('pointerleave')
    await w.get('#b').trigger('pointerenter', { pointerType: 'mouse' })
    await w.vm.$nextTick()
    expect(texto()).toContain('Reglas y skills')
    w.unmount()
  })

  it('con puntero táctil el hover no lo abre', async () => {
    vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener() {}, removeEventListener() {} }))
    const w = montar()
    await w.get('#a').trigger('pointerenter', { pointerType: 'touch' })
    vi.advanceTimersByTime(500)
    expect(cartel.visible).toBe(false)
    w.unmount()
  })

  it('deja la descripción como texto accesible, sin title', () => {
    const w = montar()
    expect(w.get('#a').attributes('aria-description')).toBe('Apariencia y avisos')
    expect(w.get('#a').attributes('title')).toBeUndefined()
    w.unmount()
  })
})
