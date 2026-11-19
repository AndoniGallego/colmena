// @vitest-environment jsdom
import { createApp, h, nextTick, shallowRef } from 'vue'
import { describe, expect, it, vi } from 'vitest'

vi.hoisted(() => {
  ;(window as any).matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} })
})
vi.mock('./Icon.vue', () => ({ default: { render: () => null } }))

import TerminalOutput from './TerminalOutput.vue'
import { nuevoCacheAnsi, parseAnsiLineas } from '../lib/ansi'

const texto = (a: number, n = 8) => Array.from({ length: n }, (_, k) => `\x1b[32mlinea ${a + k}\x1b[0m`).join('\n')

describe('TerminalOutput: claves por contenido', () => {
  it('al correr la salida, las líneas que siguen conservan su nodo del DOM', async () => {
    const cache = nuevoCacheAnsi()
    const lines = shallowRef(parseAnsiLineas(texto(0), cache))
    const el = document.createElement('div')
    document.body.appendChild(el)
    createApp({ render: () => h(TerminalOutput, { lines: lines.value, truncado: false }) }).mount(el)
    await nextTick()
    const nodo = [...el.querySelectorAll('span.sp')].find((s) => s.textContent === 'linea 3')!
    lines.value = parseAnsiLineas(texto(3), cache)
    await nextTick()
    expect(nodo.isConnected).toBe(true)
    expect(nodo.textContent).toBe('linea 3')
    expect(el.querySelector('pre')!.textContent).toBe(Array.from({ length: 8 }, (_, k) => `linea ${3 + k}\n`).join(''))
  })

  it('las líneas repetidas se dibujan todas', async () => {
    const lines = shallowRef(parseAnsiLineas('igual\nigual\nigual', nuevoCacheAnsi()))
    const el = document.createElement('div')
    createApp({ render: () => h(TerminalOutput, { lines: lines.value, truncado: false }) }).mount(el)
    await nextTick()
    expect(el.querySelector('pre')!.textContent).toBe('igual\nigual\nigual\n')
  })

  it('si se reemplaza toda la salida, los nodos se parchean en lugar de montarse de nuevo', async () => {
    const cache = nuevoCacheAnsi()
    const lines = shallowRef(parseAnsiLineas(texto(0), cache))
    const el = document.createElement('div')
    document.body.appendChild(el)
    createApp({ render: () => h(TerminalOutput, { lines: lines.value, truncado: false }) }).mount(el)
    await nextTick()
    const antes = [...el.querySelectorAll('span.ln')]
    lines.value = parseAnsiLineas(texto(1000), cache)
    await nextTick()
    const despues = [...el.querySelectorAll('span.ln')]
    expect(despues).toHaveLength(8)
    expect(despues.every((n) => antes.includes(n))).toBe(true)
    expect(el.querySelector('pre')!.textContent).toBe(Array.from({ length: 8 }, (_, k) => `linea ${1000 + k}\n`).join(''))
  })
})
