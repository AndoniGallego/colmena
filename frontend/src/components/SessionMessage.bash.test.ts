// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} })) as never
const { default: SessionMessage } = await import('./SessionMessage.vue')

const item = (text: string) => ({ kind: 'user', text, ts: '', idx: 1 }) as never

describe('SessionMessage con comandos corridos con !', () => {
  it('muestra el comando como línea de terminal, sin etiquetas', () => {
    const w = mount(SessionMessage, { props: { item: item('<bash-input>git status</bash-input>'), quiet: true } })
    expect(w.text()).not.toContain('<bash-input>')
    expect(w.find('.bash .prompt').text()).toBe('$')
    expect(w.find('.bash code').text()).toBe('git status')
  })
  it('muestra la salida y el error, sin etiquetas', () => {
    const w = mount(SessionMessage, { props: { item: item('<bash-stdout>a\nb</bash-stdout><bash-stderr>uy</bash-stderr>'), quiet: true } })
    expect(w.text()).not.toContain('bash-stdout')
    expect(w.find('.bash .salida').text()).toBe('a\nb')
    expect(w.find('.bash .error').text()).toBe('uy')
  })
  it('salida vacía dice que no hubo salida', () => {
    const w = mount(SessionMessage, { props: { item: item('<bash-stdout></bash-stdout><bash-stderr></bash-stderr>'), quiet: true } })
    expect(w.find('.bash').text()).toContain('Sin salida')
  })
  it('un mensaje normal sigue en burbuja', () => {
    const w = mount(SessionMessage, { props: { item: item('hola'), quiet: true } })
    expect(w.find('.bash').exists()).toBe(false)
    expect(w.find('.bubble').text()).toBe('hola')
  })
})
