// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick, ref, shallowRef } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Nota } from '../api/types'

const h = vi.hoisted(() => ({
  crearNota: vi.fn(async () => undefined),
  editarNota: vi.fn(async () => undefined),
  borrarNota: vi.fn(async () => undefined),
  marcarHecha: vi.fn(async () => undefined),
  openSessionChat: vi.fn(),
  entrarNota: vi.fn(),
  cascadaEntrada: vi.fn(),
  rebotarContador: vi.fn(),
  levantarTarjeta: vi.fn(async (_el: Element) => {}),
  soft: { value: true },
  despedir: vi.fn(async () => {}),
  reacomodar: vi.fn(async (_c: Element, cambio: () => void | Promise<void>, _celu?: boolean) => {
    await cambio()
    await nextTick()
  }),
}))

const notas = shallowRef<Nota[]>([])
const saltoMensaje = ref<{ sid: string; ts: string } | null>(null)
const boardState = shallowRef<{ board: unknown }>({ board: null })
const desktop = ref(true)

vi.mock('../state/notas', () => ({
  notas,
  pendientes: ref(0),
  notasVisible: ref(true),
  saltoMensaje,
  crearNota: h.crearNota,
  editarNota: h.editarNota,
  borrarNota: h.borrarNota,
  marcarHecha: h.marcarHecha,
}))
vi.mock('../state/app', () => ({ boardState }))
vi.mock('../state/session', () => ({ openSessionChat: h.openSessionChat }))
vi.mock('../lib/viewport', () => ({ desktop }))
vi.mock('../lib/notasMovimiento', () => ({
  entrarNota: h.entrarNota,
  cascadaEntrada: h.cascadaEntrada,
  rebotarContador: h.rebotarContador,
  levantarTarjeta: h.levantarTarjeta,
  bajarTarjeta: vi.fn(),
  completarNota: async () => {},
  despedir: h.despedir,
  reacomodar: h.reacomodar,
}))
vi.mock('../motion', () => ({
  gsap: { from() {}, fromTo() {}, to() {}, set() {}, killTweensOf() {} },
  isSoft: () => h.soft.value,
  useGsap: () => ({ run: (fn: () => void) => fn() }),
}))
vi.mock('./Icon.vue', () => ({ default: { name: 'Icon', render: () => null } }))
vi.mock('./ViewFrame.vue', () => ({
  default: { name: 'ViewFrame', template: '<div><slot name="actions" /><slot name="toolbar" /><slot /></div>' },
}))

const { default: NotasView } = await import('./NotasView.vue')

const n = (id: string, p: Partial<Nota>): Nota => ({
  id,
  tipo: 'apunte',
  texto: id,
  hecha_at: null,
  creada_at: '2026-11-18T10:00:00Z',
  editada_at: '2026-11-18T10:00:00Z',
  origen: null,
  ...p,
})

const montados: { unmount: () => void }[] = []
function montar() {
  const w = mount(NotasView, { props: { visible: true }, attachTo: document.body })
  montados.push(w)
  return w
}
afterEach(() => {
  for (const w of montados.splice(0)) {
    try {
      w.unmount()
    } catch {
      // ya desmontado por el test
    }
  }
})
const tarjetas = (w: ReturnType<typeof montar>) => w.findAll('.nota')

beforeEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
  desktop.value = true
  h.soft.value = true
  saltoMensaje.value = null
  boardState.value = { board: null }
  notas.value = [
    n('a', { tipo: 'recordatorio', texto: 'Pendiente uno' }),
    n('b', { tipo: 'recordatorio', texto: 'Ya hecha', hecha_at: '2026-11-18T11:00:00Z' }),
    n('c', { texto: 'Un apunte' }),
  ]
})

describe('NotasView', () => {
  it('muestra una tarjeta por nota', () => {
    const w = montar()
    expect(tarjetas(w)).toHaveLength(3)
  })

  it('el filtro Hechas deja solo los recordatorios hechos', async () => {
    const w = montar()
    const hechas = w.findAll('[role="radio"]').find((b) => b.text() === 'Hechas')!
    await hechas.trigger('click')
    await flushPromises()
    expect(tarjetas(w)).toHaveLength(1)
    expect(tarjetas(w)[0].text()).toContain('Ya hecha')
  })

  it('Enter en el campo crea un apunte y limpia el campo', async () => {
    const w = montar()
    const campo = w.find('input.notas-campo')
    await campo.setValue('  Llamar a Bruno  ')
    await campo.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(h.crearNota).toHaveBeenCalledWith({ tipo: 'apunte', texto: 'Llamar a Bruno' })
    expect((campo.element as HTMLInputElement).value).toBe('')
  })

  it('Enter con solo espacios no crea nada', async () => {
    const w = montar()
    const campo = w.find('input.notas-campo')
    await campo.setValue('    ')
    await campo.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(h.crearNota).not.toHaveBeenCalled()
  })

  it('si guardar falla, muestra un error corto y no pierde el texto', async () => {
    h.crearNota.mockRejectedValueOnce(new Error('503'))
    const w = montar()
    const campo = w.find('input.notas-campo')
    await campo.setValue('Algo')
    await campo.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(w.find('[role="alert"]').text()).toContain('No pude guardar la nota')
    expect((campo.element as HTMLInputElement).value).toBe('Algo')
  })

  it('un texto con <b> se muestra literal', () => {
    notas.value = [n('x', { texto: 'ojo <b>esto</b>' })]
    const w = montar()
    expect(tarjetas(w)[0].text()).toContain('ojo <b>esto</b>')
    expect(w.find('.nota b').exists()).toBe(false)
  })

  describe('detalle', () => {
    const origen = { sid: 's1', nombre: 'Sesión viva', ts: '2026-11-18T09:00:00Z' }
    const vivaS1 = () => {
      boardState.value = { board: { workspaces: [{ tabs: [{ agents: [{ session_id: 's1' }] }] }] } }
    }
    const boton = (txt: string) => [...document.querySelectorAll<HTMLButtonElement>('.detalle button')].find((b) => b.textContent?.includes(txt))!
    const abrir = async (w: ReturnType<typeof montar>, i = 0) => {
      const b = tarjetas(w)[i].find('button.nota-abrir')
      ;(b.element as HTMLElement).focus()
      await b.trigger('click')
      await flushPromises()
      return b.element as HTMLElement
    }

    it('en el celu, "Ir a la sesión" salta al mensaje y cierra la hoja', async () => {
      desktop.value = false
      vivaS1()
      notas.value = [n('a', { texto: 'Con origen', origen })]
      const w = montar()
      await abrir(w)
      expect(document.querySelector('.sheet-panel')).not.toBeNull()
      boton('Ir a la sesión').click()
      await flushPromises()
      expect(saltoMensaje.value).toEqual({ sid: 's1', ts: origen.ts })
      expect(h.openSessionChat).toHaveBeenCalledWith('s1')
      expect(document.querySelector('.sheet-panel')).toBeNull()
    })

    it('si el origen no tiene nombre el detalle dice "de una sesión"', async () => {
      desktop.value = false
      notas.value = [n('a', { texto: 'Sin nombre', origen: { sid: 's1', nombre: '', ts: origen.ts } })]
      const w = montar()
      await abrir(w)
      const dm = document.querySelector('.detalle .dm')!.textContent!.replace(/\s+/g, ' ')
      expect(dm).toContain('de una sesión')
    })

    it('si editar falla, el error se ve dentro del detalle', async () => {
      h.editarNota.mockRejectedValueOnce(new Error('x'))
      const w = montar()
      await abrir(w)
      boton('Editar').click()
      await flushPromises()
      const ta = document.querySelector<HTMLTextAreaElement>('.detalle textarea')!
      ta.value = 'Otro texto'
      ta.dispatchEvent(new Event('input'))
      await flushPromises()
      boton('Guardar').click()
      await flushPromises()
      expect(document.querySelector('.detalle [role="alert"]')?.textContent).toContain('No pude guardar el cambio')
    })

    it('si borrar falla, el error se ve dentro del detalle', async () => {
      h.borrarNota.mockRejectedValueOnce(new Error('x'))
      const w = montar()
      await abrir(w)
      boton('Borrar').click()
      await flushPromises()
      boton('Borrar').click()
      await flushPromises()
      expect(document.querySelector('.detalle [role="alert"]')?.textContent).toContain('No pude borrar la nota')
    })

    it('en el celu la hoja toma el foco y Esc lo devuelve a la tarjeta', async () => {
      desktop.value = false
      const w = montar()
      const opener = await abrir(w)
      const panel = document.querySelector('.sheet-panel')!
      expect(panel.contains(document.activeElement)).toBe(true)
      document.activeElement!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
      await flushPromises()
      expect(document.querySelector('.sheet-panel')).toBeNull()
      expect(document.activeElement).toBe(opener)
    })
  })

  it('las notas que llegan al cargar no hacen la entrada, las nuevas sí', async () => {
    notas.value = []
    montar()
    notas.value = [n('a', {}), n('b', {})]
    await flushPromises()
    expect(h.entrarNota).not.toHaveBeenCalled()
    notas.value = [n('c', {}), n('a', {}), n('b', {})]
    await flushPromises()
    expect(h.entrarNota).toHaveBeenCalledTimes(1)
  })

  it('al montar, las tarjetas entran en cascada y rebota el contador', async () => {
    const w = montar()
    await flushPromises()
    expect(h.cascadaEntrada).toHaveBeenCalledTimes(1)
    const [els] = h.cascadaEntrada.mock.calls[0] as unknown as [Element[]]
    expect(els).toHaveLength(3)
    expect(els.every((e) => e.classList.contains('nota'))).toBe(true)
    expect(h.rebotarContador).toHaveBeenCalledTimes(1)
    expect((h.rebotarContador.mock.calls[0] as unknown as [Element])[0]).toBe(w.find('.frasco-hex').element)
  })

  it('si las notas llegan después de montar, la primera carga también entra en cascada', async () => {
    notas.value = []
    montar()
    await flushPromises()
    expect(h.cascadaEntrada).not.toHaveBeenCalled()
    notas.value = [n('a', {}), n('b', {})]
    await flushPromises()
    expect(h.cascadaEntrada).toHaveBeenCalledTimes(1)
    expect((h.cascadaEntrada.mock.calls[0] as unknown as [Element[]])[0]).toHaveLength(2)
    notas.value = [n('c', {}), n('a', {}), n('b', {})]
    await flushPromises()
    expect(h.cascadaEntrada).toHaveBeenCalledTimes(1)
  })

  describe('filtros en el celu', () => {
    const radio = (w: ReturnType<typeof montar>, t: string) => w.findAll('[role="radio"]').find((b) => b.text() === t)!

    it('cambiar de filtro mueve el indicador a la pestaña elegida y reacomoda las tarjetas', async () => {
      desktop.value = false
      const w = montar()
      await flushPromises()
      const seg = () => (w.find('.seg').element as HTMLElement).style
      expect(seg().getPropertyValue('--i')).toBe('0')
      h.reacomodar.mockClear()
      h.despedir.mockClear()
      await radio(w, 'Apuntes').trigger('click')
      await flushPromises()
      expect(seg().getPropertyValue('--i')).toBe('2')
      expect(radio(w, 'Apuntes').attributes('aria-checked')).toBe('true')
      expect(h.despedir).toHaveBeenCalledTimes(1)
      expect((h.despedir.mock.calls[0] as unknown[])[1]).toBe(true)
      expect(h.reacomodar).toHaveBeenCalledTimes(1)
      expect((h.reacomodar.mock.calls[0] as unknown[])[2]).toBe(true)
      expect(tarjetas(w)).toHaveLength(1)
    })

    it('en escritorio el reacomodo mantiene su animación de siempre', async () => {
      const w = montar()
      await flushPromises()
      h.reacomodar.mockClear()
      await radio(w, 'Apuntes').trigger('click')
      await flushPromises()
      expect((h.reacomodar.mock.calls[0] as unknown[])[2]).toBe(false)
    })
  })

  describe('tocar una tarjeta en el celu', () => {
    const tocar = (w: ReturnType<typeof montar>) => w.find('button.nota-abrir').trigger('click')

    it('la tarjeta se levanta y recién después abre la hoja', async () => {
      desktop.value = false
      h.soft.value = false
      let listo!: () => void
      h.levantarTarjeta.mockImplementationOnce(() => new Promise<void>((ok) => (listo = ok)))
      const w = montar()
      await tocar(w)
      expect(h.levantarTarjeta).toHaveBeenCalledTimes(1)
      expect((h.levantarTarjeta.mock.calls[0] as unknown[])[0]).toBe(tarjetas(w)[0].element)
      expect(document.querySelector('.sheet-panel')).toBeNull()
      listo()
      await flushPromises()
      expect(document.querySelector('.sheet-panel')).not.toBeNull()
    })

    it('con movimiento suave abre directo, sin levantar', async () => {
      desktop.value = false
      const w = montar()
      await tocar(w)
      await flushPromises()
      expect(h.levantarTarjeta).not.toHaveBeenCalled()
      expect(document.querySelector('.sheet-panel')).not.toBeNull()
    })

    it('en escritorio no se levanta', async () => {
      h.soft.value = false
      const w = montar()
      await tocar(w)
      await flushPromises()
      expect(h.levantarTarjeta).not.toHaveBeenCalled()
    })
  })

  describe('deslizar una nota en el celu', () => {
    const ptr = (el: Element, tipo: string, x: number) => {
      const Ev = (window as unknown as { PointerEvent?: typeof MouseEvent }).PointerEvent ?? MouseEvent
      el.dispatchEvent(new Ev(tipo, { clientX: x, clientY: 10, bubbles: true }))
    }
    const deslizar = (el: Element, dx: number) => {
      ptr(el, 'pointerdown', 10)
      ptr(el, 'pointermove', 10 + dx)
      ptr(el, 'pointerup', 10 + dx)
    }

    it('soltar pasada la mitad completa la nota sin abrir la hoja', async () => {
      desktop.value = false
      const w = montar()
      const el = tarjetas(w)[0]
      el.element.getBoundingClientRect = () => ({ width: 200, height: 80, left: 0, top: 0, right: 200, bottom: 80, x: 0, y: 0, toJSON() {} })
      deslizar(el.element, 150)
      await w.find('button.nota-abrir').trigger('click')
      await flushPromises()
      expect(h.marcarHecha).toHaveBeenCalledWith('a', true)
      expect(document.querySelector('.sheet-panel')).toBeNull()
    })

    it('las tarjetas hechas y los apuntes no se deslizan; en escritorio tampoco', async () => {
      desktop.value = false
      const w = montar()
      deslizar(tarjetas(w)[1].element, 300)
      deslizar(tarjetas(w)[2].element, 300)
      await flushPromises()
      expect(h.marcarHecha).not.toHaveBeenCalled()
      desktop.value = true
      await flushPromises()
      deslizar(tarjetas(w)[0].element, 300)
      await flushPromises()
      expect(h.marcarHecha).not.toHaveBeenCalled()
    })
  })

  it('al desmontar saca el clon que estaba volando', () => {
    const w = montar()
    const clon = document.createElement('div')
    clon.className = 'nota-vuelo'
    document.body.append(clon)
    w.unmount()
    expect(document.querySelector('.nota-vuelo')).toBeNull()
  })
})
