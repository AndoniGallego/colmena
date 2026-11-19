// @vitest-environment jsdom
import { h } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const m = await vi.hoisted(async () => {
  const { reactive: rx } = await import('vue')
  const { vi: v } = await import('vitest')
  return {
    tareas: rx({ data: null as unknown, historial: [] as unknown[], cargando: false, error: '', errorAccion: '', errorForm: '', guardando: false, ocupados: {} as Record<string, boolean>, pinBusy: false, pinError: '', pinBloqueadoHasta: 0 }),
    cargarTareas: v.fn(), alternarPausa: v.fn(), borrar: v.fn(), correr: v.fn(), interruptor: v.fn(async () => true), closeTareas: v.fn(), soltarTareas: v.fn(),
    openTerminal: v.fn(),
  }
})

vi.mock('../state/tareas', () => ({ ...m }))
vi.mock('../state/terminales', () => ({ openTerminal: m.openTerminal }))
vi.mock('../lib/viewport', async () => ({ desktop: (await import('vue')).ref(false) }))
vi.mock('./Icon.vue', () => ({ default: { props: ['name'], render() { return h('i', { class: 'icon' }) } } }))
vi.mock('./ViewFrame.vue', () => ({ default: { template: '<div><slot name="back" /><slot /></div>' } }))
vi.mock('./TrabajadoresCursor.vue', () => ({ default: { template: '<div class="trab" />' } }))
vi.mock('./TareaForm.vue', () => ({ default: { props: ['open', 'programa'], template: '<div class="form" :data-open="open" />' } }))
vi.mock('./TerminalPinSheet.vue', () => ({ default: { props: ['open'], emits: ['submit', 'close'], template: '<div class="pin" :data-open="open"><button class="pin-ok" @click="$emit(\'submit\', \'1234\')" /></div>' } }))
vi.mock('./ConfirmSheet.vue', () => ({ default: { props: ['open'], emits: ['confirm', 'cancel'], template: '<div class="conf" :data-open="open"><button class="conf-ok" @click="$emit(\'confirm\')" /></div>' } }))

import TareasView from './TareasView.vue'

const ID = 'a'.repeat(32)
const prog = (o: object = {}) => ({ id: ID, nombre: 'Revisar MRs', repo: '/r/a', pedido: 'p', agente: 'claude', modelo: '', cuando: { tipo: 'diaria', hora: '09:00' }, pausada: true, proxima: null, ...o })
const datos = (o: object = {}) => ({ habilitado: false, programas: [prog()], cursor_disponible: true, ...o })

beforeEach(() => {
  Object.values(m).forEach((f) => typeof f === 'function' && 'mockClear' in f && (f as ReturnType<typeof vi.fn>).mockClear())
  m.tareas.data = null
  m.tareas.historial = []
  m.tareas.error = ''
  m.tareas.errorAccion = ''
  m.tareas.ocupados = {}
})

describe('TareasView', () => {
  it('carga al abrir y muestra el estado de carga', () => {
    const w = mount(TareasView)
    expect(m.cargarTareas).toHaveBeenCalled()
    expect(w.text()).toContain('Leyendo')
  })

  it('apagado de fábrica: lo dice y prender abre el PIN sin llamar al servidor', async () => {
    m.tareas.data = datos()
    const w = mount(TareasView)
    expect(w.find('[data-test="global"]').text()).toContain('apagadas')
    await w.find('[data-test="interruptor"]').trigger('click')
    expect(w.find('.pin').attributes('data-open')).toBe('true')
    expect(m.interruptor).not.toHaveBeenCalled()
    await w.find('.pin-ok').trigger('click')
    expect(m.interruptor).toHaveBeenCalledWith(true, '1234')
  })

  it('prendido: apagar no pide PIN', async () => {
    m.tareas.data = datos({ habilitado: true })
    const w = mount(TareasView)
    await w.find('[data-test="interruptor"]').trigger('click')
    expect(m.interruptor).toHaveBeenCalledWith(false)
    expect(w.find('.pin').attributes('data-open')).toBe('false')
  })

  it('lista la tarea con su horario y los botones llaman a sus acciones', async () => {
    m.tareas.data = datos()
    const w = mount(TareasView)
    const t = w.find('[data-test="programa"]').text()
    expect(t).toContain('Revisar MRs')
    expect(t).toContain('Todos los días a las 09:00')
    expect(t).toContain('Pausada')
    await w.find('[data-test="correr"]').trigger('click')
    expect(m.correr).toHaveBeenCalled()
    await w.find('[data-test="pausa"]').trigger('click')
    expect(m.alternarPausa).toHaveBeenCalled()
    expect(w.find('[data-test="pausa"]').text()).toContain('Reanudar')
  })

  it('borrar pide confirmación antes de llamar', async () => {
    m.tareas.data = datos()
    const w = mount(TareasView)
    await w.find('[data-test="borrar"]').trigger('click')
    expect(m.borrar).not.toHaveBeenCalled()
    expect(w.find('.conf').attributes('data-open')).toBe('true')
    await w.find('.conf-ok').trigger('click')
    expect(m.borrar).toHaveBeenCalled()
  })

  it('Nueva y Editar abren el formulario', async () => {
    m.tareas.data = datos()
    const w = mount(TareasView)
    expect(w.find('.form').attributes('data-open')).toBe('false')
    await w.find('[data-test="nueva"]').trigger('click')
    expect(w.find('.form').attributes('data-open')).toBe('true')
  })

  it('historial: icono por estado, motivo y link a la sesión', async () => {
    m.tareas.data = datos()
    m.tareas.historial = [
      { id: 'c1', programa_id: ID, nombre: 'Revisar MRs', previsto: 1, inicio: 1, estado: 'ok', motivo: '', agente: 'claude', manual: true, pane_id: 'w1:p2' },
      { id: 'c2', programa_id: ID, nombre: 'Revisar MRs', previsto: 1, inicio: null, estado: 'salteada', motivo: 'la notebook estaba apagada o suspendida', agente: 'claude', manual: false, pane_id: '' },
    ]
    const w = mount(TareasView)
    const filas = w.findAll('[data-test="corrida"]')
    expect(filas).toHaveLength(2)
    expect(filas[1].text()).toContain('la notebook estaba apagada')
    expect(filas[0].find('[data-test="sesion"]').exists()).toBe(true)
    expect(filas[1].find('[data-test="sesion"]').exists()).toBe(false)
    await filas[0].find('[data-test="sesion"]').trigger('click')
    expect(m.openTerminal).toHaveBeenCalledWith('w1:p2')
  })

  it('avisa si hay tareas de Cursor y Cursor no está', () => {
    m.tareas.data = datos({ cursor_disponible: false, programas: [prog({ agente: 'cursor' })] })
    const w = mount(TareasView)
    expect(w.find('[data-test="sin-cursor"]').exists()).toBe(true)
  })

  it('con Cursor disponible monta los trabajadores de Cursor', () => {
    m.tareas.data = datos()
    expect(mount(TareasView).find('.trab').exists()).toBe(true)
    m.tareas.data = datos({ cursor_disponible: false })
    expect(mount(TareasView).find('.trab').exists()).toBe(false)
  })

  it('el título de los trabajadores de Cursor aparece una sola vez', () => {
    m.tareas.data = datos()
    const txt = mount(TareasView).text()
    expect(txt.match(/Trabajadores (de )?Cursor/g)).toHaveLength(1)
  })

  it('vacío: dice que no hay tareas', () => {
    m.tareas.data = datos({ programas: [] })
    expect(mount(TareasView).find('[data-test="vacio"]').exists()).toBe(true)
  })
})
