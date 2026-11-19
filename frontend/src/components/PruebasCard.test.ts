// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import PruebasCard from './PruebasCard.vue'
import type { Pruebas } from '../lib/pruebas'

vi.mock('../state/biblioteca', () => ({ cachedLibItem: vi.fn(async () => null), fresh: vi.fn(async (i: unknown) => i) }))

const data: Pruebas = {
  titulo: 'Login',
  resumen: 'Resumen',
  casos: [
    { nombre: 'A', resultado: 'ok' },
    { nombre: 'B', resultado: 'falla', detalle: 'Se rompe', evidencia: '/x/y/foto.png' },
    { nombre: 'C', resultado: 'omitida' },
  ],
}

describe('PruebasCard', () => {
  it('muestra título, contador sin ceros, resumen y casos', () => {
    const w = mount(PruebasCard, { props: { data: { ...data, casos: data.casos.slice(0, 2) } } })
    expect(w.text()).toContain('🧪')
    expect(w.text()).toContain('1 ok · 1 falla')
    expect(w.text()).not.toContain('omitida')
    expect(w.text()).toContain('Resumen')
    expect(w.text()).toContain('Se rompe')
  })
  it('sin mapa muestra solo el nombre del archivo', () => {
    const w = mount(PruebasCard, { props: { data } })
    expect(w.find('.ruta').text()).toBe('foto.png')
    expect(w.find('.captura').exists()).toBe(false)
  })
  it('con evidencia resuelta muestra el botón captura', () => {
    const w = mount(PruebasCard, { props: { data, evidencias: { '/x/y/foto.png': 'abc' } } })
    expect(w.find('.captura').exists()).toBe(true)
    expect(w.find('.ruta').exists()).toBe(false)
  })
  it('con un ID de captura sin resolver muestra el ID y con mapa muestra la captura', () => {
    const d = { ...data, casos: [{ nombre: 'C', resultado: 'ok' as const, evidencia: 'ss_abc123' }] }
    const sin = mount(PruebasCard, { props: { data: d } })
    expect(sin.find('.ruta').text()).toBe('ss_abc123')
    const con = mount(PruebasCard, { props: { data: d, evidencias: { ss_abc123: 'iid' } } })
    expect(con.find('.captura').exists()).toBe(true)
    expect(con.find('.ruta').exists()).toBe(false)
  })
})
