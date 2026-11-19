// @vitest-environment jsdom
import { h } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { kit, cargarKit, arreglar, abrirRegla, cerrarRegla, closeKit } = await vi.hoisted(async () => {
  const { reactive: rx } = await import('vue')
  const { vi: v } = await import('vitest')
  return {
    kit: rx({ data: null as unknown, cargando: false, error: '', arreglando: false, errorArreglo: '', regla: null as unknown }),
    cargarKit: v.fn(),
    arreglar: v.fn(),
    abrirRegla: v.fn(),
    cerrarRegla: v.fn(),
    closeKit: v.fn(),
  }
})

vi.mock('../state/kit', () => ({ kit, cargarKit, arreglar, abrirRegla, cerrarRegla, closeKit }))
vi.mock('../lib/viewport', async () => ({ desktop: (await import('vue')).ref(false) }))
vi.mock('./Icon.vue', () => ({ default: { props: ['name'], render() { return h('i', { class: 'icon' }) } } }))
vi.mock('./ViewFrame.vue', () => ({ default: { template: '<div><slot name="back" /><slot /></div>' } }))

import KitView from './KitView.vue'

const datos = (al_dia: boolean) => ({
  estado: { al_dia, problemas: al_dia ? [] : ['Falta instalar la regla «estado-sesion».', 'Sobra el hook «viejo.sh».'] },
  reglas: [{ id: 'estado-sesion', titulo: 'Estado de la sesión', proposito: 'Al terminar, cierra con tres líneas.' }],
  skills: [{ id: 'diagramas', nombre: 'diagramas', que_hace: 'Dibuja diagramas.' }],
  hooks: [{ id: 'a.sh', nombre: 'a.sh', que_hace: 'Pide el bloque estado.' }],
})

beforeEach(() => {
  ;[cargarKit, arreglar, abrirRegla, cerrarRegla, closeKit].forEach((f) => f.mockReset())
  kit.data = null
  kit.cargando = false
  kit.error = ''
  kit.arreglando = false
  kit.errorArreglo = ''
  kit.regla = null
})

const montar = () => mount(KitView)

describe('KitView', () => {
  it('carga el kit al abrir', () => {
    montar()
    expect(cargarKit).toHaveBeenCalled()
  })

  it('al día muestra la tilde y no ofrece Arreglar', () => {
    kit.data = datos(true)
    const w = montar()
    expect(w.find('[data-test="estado"]').text()).toContain('Kit al día')
    expect(w.find('[data-test="arreglar"]').exists()).toBe(false)
  })

  it('con problemas los lista en castellano y ofrece Arreglar', async () => {
    kit.data = datos(false)
    const w = montar()
    const txt = w.find('[data-test="estado"]').text()
    expect(txt).toContain('Falta instalar la regla «estado-sesion».')
    expect(txt).toContain('Sobra el hook «viejo.sh».')
    await w.find('[data-test="arreglar"]').trigger('click')
    expect(arreglar).toHaveBeenCalled()
  })

  it('mientras arregla el botón queda deshabilitado', () => {
    kit.data = datos(false)
    kit.arreglando = true
    const w = montar()
    const b = w.find('[data-test="arreglar"]')
    expect(b.attributes('disabled')).toBeDefined()
    expect(b.text()).toContain('Arreglando')
  })

  it('muestra el error de arreglar', () => {
    kit.data = datos(false)
    kit.errorArreglo = 'No pude respaldar el archivo'
    expect(montar().text()).toContain('No pude respaldar el archivo')
  })

  it('lista reglas con propósito, skills y hooks con qué hacen', () => {
    kit.data = datos(true)
    const t = montar().text()
    expect(t).toContain('Reglas')
    expect(t).toContain('Al terminar, cierra con tres líneas.')
    expect(t).toContain('Skills')
    expect(t).toContain('Dibuja diagramas.')
    expect(t).toContain('Hooks')
    expect(t).toContain('Pide el bloque estado.')
  })

  it('tocar una regla la abre', async () => {
    kit.data = datos(true)
    const w = montar()
    await w.find('[data-test="regla"]').trigger('click')
    expect(abrirRegla).toHaveBeenCalledWith(expect.objectContaining({ id: 'estado-sesion' }))
  })

  it('la regla abierta se ve como markdown y se puede volver', async () => {
    kit.data = datos(true)
    kit.regla = { id: 'estado-sesion', titulo: 'Estado de la sesión', texto: '# Hola\n\nUn **texto**.', cargando: false, error: '' }
    const w = montar()
    expect(w.find('[data-test="regla-texto"] strong').text()).toBe('texto')
    expect(w.find('[data-test="regla"]').exists()).toBe(false)
    await w.find('[data-test="volver-regla"]').trigger('click')
    expect(cerrarRegla).toHaveBeenCalled()
  })

  it('error al cargar el kit con reintento', async () => {
    kit.error = 'No llego a Colmena.'
    const w = montar()
    expect(w.text()).toContain('No llego a Colmena.')
    cargarKit.mockClear()
    await w.find('[data-test="reintentar"]').trigger('click')
    expect(cargarKit).toHaveBeenCalled()
    await flushPromises()
  })
})
