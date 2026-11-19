// @vitest-environment jsdom
import { readFileSync } from 'node:fs'
import { h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const m = await vi.hoisted(async () => {
  const { reactive: rx } = await import('vue')
  const { vi: v } = await import('vitest')
  return {
    tareas: rx({ errorForm: '', guardando: false }),
    guardar: v.fn(async () => true),
    getCarpetasRepo: v.fn(async () => [{ ruta: '/r/a', nombre: 'a' }]),
  }
})

vi.mock('../state/tareas', () => ({ guardar: m.guardar, tareas: m.tareas }))
vi.mock('../api/programadasApi', () => ({ getCarpetasRepo: m.getCarpetasRepo }))
vi.mock('../motion', () => ({
  gsap: { fromTo() {}, to() {}, timeline: () => ({ fromTo() {}, to() {} }) },
  isSoft: () => true,
  useGsap: () => ({ run: (fn: () => void) => fn() }),
}))
vi.mock('../lib/useSheetSwipe', () => ({ useSheetSwipe: () => {} }))
vi.mock('./Icon.vue', () => ({ default: { props: ['name'], render() { return h('i') } } }))

import TareaForm from './TareaForm.vue'

const montar = (props: object = {}) =>
  mount(TareaForm, { props: { open: true, programa: null, cursorDisponible: true, ...props }, global: { stubs: { teleport: true, transition: false } } })

beforeEach(() => {
  m.guardar.mockClear()
  m.tareas.errorForm = ''
})

describe('TareaForm', () => {
  it('sin repo ni pedido no guarda y explica qué falta', async () => {
    const w = await (async () => { const x = montar(); await flushPromises(); return x })()
    await w.find('[data-test="nombre"]').setValue('Revisar')
    await w.find('form').trigger('submit')
    expect(m.guardar).not.toHaveBeenCalled()
    expect(w.find('[role="alert"]').text()).toMatch(/repo/i)
  })

  it('con todo completo guarda el cuerpo de una tarea diaria', async () => {
    const w = montar()
    await flushPromises()
    await w.find('[data-test="nombre"]').setValue('Revisar')
    await w.find('.carp').trigger('click')
    await w.find('[data-test="pedido"]').setValue('Mirá los MRs')
    await w.find('[data-test="hora"]').setValue('08:15')
    await w.find('form').trigger('submit')
    expect(m.guardar).toHaveBeenCalledWith(
      { nombre: 'Revisar', repo: '/r/a', pedido: 'Mirá los MRs', agente: 'claude', modelo: '', cuando: { tipo: 'diaria', hora: '08:15' } },
      undefined,
    )
  })

  it('hora inválida o vacía se rechaza', async () => {
    const w = montar()
    await flushPromises()
    await w.find('[data-test="nombre"]').setValue('X')
    await w.find('.carp').trigger('click')
    await w.find('[data-test="pedido"]').setValue('p')
    await w.find('[data-test="hora"]').setValue('')
    await w.find('form').trigger('submit')
    expect(m.guardar).not.toHaveBeenCalled()
    expect(w.find('[role="alert"]').text()).toMatch(/hora/i)
  })

  it('Cursor queda deshabilitado si no está disponible y avisa', async () => {
    const w = montar({ cursorDisponible: false })
    await flushPromises()
    const botones = w.findAll('button').filter((b) => b.text() === 'Cursor')
    expect(botones.length).toBe(1)
    expect(botones[0].attributes('disabled')).toBeDefined()
    expect(w.text()).toContain('Cursor no está disponible')
  })

  it('al editar carga los datos de la tarea y manda el id', async () => {
    const programa = { id: 'a'.repeat(32), nombre: 'Vieja', repo: '/r/a', pedido: 'p', agente: 'claude', modelo: '', cuando: { tipo: 'semanal', hora: '18:00', dia: 4 }, pausada: true, proxima: null }
    const w = montar({ programa })
    await flushPromises()
    expect((w.find('[data-test="nombre"]').element as HTMLInputElement).value).toBe('Vieja')
    await w.find('form').trigger('submit')
    expect(m.guardar).toHaveBeenCalledWith(expect.objectContaining({ cuando: { tipo: 'semanal', hora: '18:00', dia: 4 } }), 'a'.repeat(32))
  })

  it('los campos de texto usan 16px para que iOS no haga zoom', () => {
    const css = readFileSync('src/components/TareaForm.vue', 'utf8')
    const regla = css.match(/input,\n\.sel,\n\.pedido \{[^}]*\}/)?.[0] ?? ''
    expect(regla).toContain('font-size: 16px')
  })
})
