// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, defineComponent, ref } from 'vue'

const modo = ref<'cerrado' | 'panel' | 'aviso' | 'notas'>('cerrado')
const cerrarNotas = vi.fn(() => {
  if (modo.value === 'notas') modo.value = 'cerrado'
})

vi.mock('../../motion', async () => {
  const { ref: r } = await import('vue')
  return {
    gsap: { set() {}, to() {}, fromTo() {}, from() {}, killTweensOf() {} },
    isSoft: () => true,
    soft: r(true),
    useGsap: () => ({ run: (fn: () => void) => fn() }),
  }
})
vi.mock('../logo/LogoPanal.vue', () => ({ default: { name: 'LogoPanal', template: '<span />' } }))
vi.mock('./NotchPill.vue', () => ({
  default: defineComponent({
    name: 'NotchPill',
    template: '<div><div class="cara"><slot name="cara" /></div><div class="cuerpo"><slot name="cuerpo" /></div></div>',
  }),
}))
vi.mock('./NotchPanel.vue', () => ({ default: { name: 'NotchPanel', template: '<div class="panel-stub" />' } }))
vi.mock('./NotchAviso.vue', () => ({ default: { name: 'NotchAviso', template: '<div />' } }))
vi.mock('./NotchLogin.vue', () => ({ default: { name: 'NotchLogin', template: '<div />' } }))
vi.mock('./NotchCaptura.vue', () => ({
  default: {
    name: 'NotchCaptura',
    emits: ['guardada', 'cerrar'],
    template: '<div class="captura-stub" />',
  },
}))
vi.mock('../../state/app', async () => {
  const { ref: r } = await import('vue')
  return { auth: r('ready') }
})
const lista = vi.hoisted(() => ({ ref: null as null | { value: unknown[] } }))
vi.mock('../../state/notas', async () => {
  const { ref: r, shallowRef: sr } = await import('vue')
  lista.ref = sr<unknown[]>([])
  return { crearNota: vi.fn(), pendientes: r(0), notas: lista.ref, marcarHecha: vi.fn() }
})
vi.mock('../../lib/notasCola', () => ({ vaciarCola: vi.fn() }))
vi.mock('../../state/notch', () => ({
  modo,
  celdas: computed(() => []),
  enVivo: ref(false),
  grupos: computed(() => ({ teToca: [], trabajando: [], termino: [], otras: [], fuera: 0 })),
  sesiones: computed(() => []),
  alternarPanel: vi.fn(),
  cerrarPanel: vi.fn(),
  cerrarNotas,
  abrirSesion: vi.fn(),
  abrirColmena: vi.fn(),
  abrirNotas: vi.fn(),
  setPuente: vi.fn(),
  iniciarEscuchaNotas: vi.fn(),
}))
vi.mock('../../state/notchAvisos', () => ({ avisoActual: ref(null), cerrarAviso: vi.fn(), iniciarAvisosNotch: vi.fn() }))
vi.mock('../../state/notchResumen', () => ({
  resumenVisible: ref({ teToca: 0, trabajando: 0, termino: 0 }),
  iniciarResumenVisible: vi.fn(),
}))
vi.mock('../../state/pedidosPestana', () => ({ initPedidosPestana: vi.fn() }))
vi.mock('../../lib/notchPuente', () => ({ crearPuente: () => ({}) }))

const { default: NotchApp } = await import('./NotchApp.vue')

describe('NotchApp en modo notas', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    modo.value = 'cerrado'
    cerrarNotas.mockClear()
    lista.ref!.value = []
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('muestra la lista con el campo adentro, sin sesiones ni "Anotar"', async () => {
    const w = mount(NotchApp)
    modo.value = 'notas'
    await flushPromises()
    expect(w.find('.panel-stub').exists()).toBe(false)
    const notas = w.get('section.notas')
    expect(notas.find('.captura-stub').exists()).toBe(true)
    expect(notas.find('button.anotar').exists()).toBe(false)
    w.unmount()
  })

  it('al guardar deja ver el renglón nuevo y cierra ~700 ms después con "Guardada · …"', async () => {
    const w = mount(NotchApp)
    modo.value = 'notas'
    await flushPromises()
    lista.ref!.value = [
      {
        id: 'nueva',
        tipo: 'apunte',
        texto: 'Comprar yerba',
        hecha_at: null,
        creada_at: '2026-11-19T10:00:00Z',
        editada_at: '2026-11-19T10:00:00Z',
        origen: null,
      },
    ]
    w.getComponent({ name: 'NotchCaptura' }).vm.$emit('guardada', { tipo: 'apunte', sinConexion: false })
    await flushPromises()
    expect(cerrarNotas).not.toHaveBeenCalled()
    expect(w.get('li.nota[data-id="nueva"]').text()).toContain('Comprar yerba')
    vi.advanceTimersByTime(700)
    await flushPromises()
    expect(cerrarNotas).toHaveBeenCalledTimes(1)
    expect(w.get('.cara').text()).toContain('Guardada · Apunte')
    w.unmount()
  })

  it('Enter y enseguida Esc: la confirmación sale en el acto, sin esperar el cierre', async () => {
    const w = mount(NotchApp)
    modo.value = 'notas'
    await flushPromises()
    w.getComponent({ name: 'NotchCaptura' }).vm.$emit('guardada', { tipo: 'recordatorio', sinConexion: false })
    modo.value = 'cerrado'
    await flushPromises()
    expect(w.get('.cara').text()).toContain('Guardada · Para hacer')
    vi.advanceTimersByTime(700)
    await flushPromises()
    expect(cerrarNotas).not.toHaveBeenCalled()
    w.unmount()
  })

  it('si cambia a otro modo antes de tiempo, el aviso sin conexión no se pierde ni cambia el modo', async () => {
    const w = mount(NotchApp)
    modo.value = 'notas'
    await flushPromises()
    w.getComponent({ name: 'NotchCaptura' }).vm.$emit('guardada', { tipo: 'apunte', sinConexion: true })
    modo.value = 'panel'
    await flushPromises()
    expect(w.get('.cara').text()).toContain('sin conexión, la guardo cuando vuelva')
    vi.advanceTimersByTime(700)
    await flushPromises()
    expect(modo.value).toBe('panel')
    w.unmount()
  })
})
