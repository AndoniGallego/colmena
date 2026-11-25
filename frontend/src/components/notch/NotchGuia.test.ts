// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  pedir: vi.fn(async (_p: string) => undefined),
  siguiente: vi.fn(async () => undefined),
  terminar: vi.fn(async () => undefined),
}))

vi.mock('../../state/guia', async () => {
  const { ref } = await import('vue')
  const real = await vi.importActual<typeof import('../../state/guia')>('../../state/guia').catch(() => null)
  return {
    guia: ref({ estado: 'vacia', guia: null, paso: 0, total: 0, texto: '', sigue: false }),
    preguntaGuia: ref(''),
    guiaActiva: real?.guiaActiva,
    seguirViva: real?.seguirViva,
    puedeSiguiente: real?.puedeSiguiente,
    textoCajita: real?.textoCajita,
    pedir: h.pedir,
    siguiente: h.siguiente,
    terminar: h.terminar,
  }
})
vi.mock('../../state/notch', () => ({ modo: { value: 'cerrado' } }))
vi.mock('../../state/reunion', () => ({ reunion: { value: {} }, enCurso: () => false }))

const { guia, preguntaGuia } = await import('../../state/guia')
const { default: NotchGuia } = await import('./NotchGuia.vue')
const fuente = (await import('./NotchGuia.vue?raw')).default as string

const poner = (p: Partial<{ estado: string; guia: number | null; paso: number; total: number; texto: string; sigue: boolean }>) => {
  guia.value = { estado: 'vacia', guia: null, paso: 0, total: 0, texto: '', sigue: false, ...p } as never
}
const botones = (w: ReturnType<typeof mount>) => w.findAll('button').map((b) => b.text())

describe('NotchGuia', () => {
  beforeEach(() => {
    h.pedir.mockClear()
    h.siguiente.mockClear()
    h.terminar.mockClear()
    poner({})
    preguntaGuia.value = ''
  })

  it('muestra lo que le mandaste mientras dura la guía', () => {
    preguntaGuia.value = 'Cómo comparto la pantalla'
    poner({ estado: 'paso', guia: 1, paso: 1, total: 2, texto: 'Tocá Compartir' })
    const w = mount(NotchGuia)
    expect(w.get('.pregunta').text()).toContain('Cómo comparto la pantalla')
  })

  it('sin pregunta no muestra la línea', () => {
    const w = mount(NotchGuia)
    expect(w.find('.pregunta').exists()).toBe(false)
  })

  it('Enter con texto llama a pedir y limpia el campo', async () => {
    const w = mount(NotchGuia, { attachTo: document.body })
    const campo = w.get('input')
    await campo.setValue('Quiero guardar el archivo')
    await campo.trigger('keydown', { key: 'Enter' })
    expect(h.pedir).toHaveBeenCalledWith('Quiero guardar el archivo')
    expect((campo.element as HTMLInputElement).value).toBe('')
    w.unmount()
  })

  it('Enter sin texto no pide', async () => {
    const w = mount(NotchGuia)
    await w.get('input').trigger('keydown', { key: 'Enter' })
    expect(h.pedir).not.toHaveBeenCalled()
  })

  it('el campo tiene tope de 300 y toma el foco al montar', () => {
    const w = mount(NotchGuia, { attachTo: document.body })
    const campo = w.get('input')
    expect(campo.attributes('maxlength')).toBe('300')
    expect(campo.attributes('aria-label')).toBe('¿Qué querés hacer?')
    expect(document.activeElement).toBe(campo.element)
    w.unmount()
  })

  it('cuando la ventana recibe el foco, el cursor vuelve al campo', () => {
    const w = mount(NotchGuia, { attachTo: document.body })
    const campo = w.get('input').element as HTMLInputElement
    campo.blur()
    expect(document.activeElement).not.toBe(campo)
    window.dispatchEvent(new Event('focus'))
    expect(document.activeElement).toBe(campo)
    w.unmount()
  })

  it('al desmontarse deja de escuchar el foco de la ventana', () => {
    const otro = document.createElement('button')
    document.body.appendChild(otro)
    const w = mount(NotchGuia, { attachTo: document.body })
    w.unmount()
    otro.focus()
    window.dispatchEvent(new Event('focus'))
    expect(document.activeElement).toBe(otro)
    otro.remove()
  })

  it('Escape oculta la cajita sin terminar la guía', async () => {
    const w = mount(NotchGuia)
    await w.get('input').trigger('keydown', { key: 'Escape' })
    expect(w.emitted('cerrar')).toHaveLength(1)
    expect(h.terminar).not.toHaveBeenCalled()
  })

  it('mirando: campo deshabilitado, texto visible y sin botones de paso', async () => {
    poner({ estado: 'mirando', guia: 1 })
    const w = mount(NotchGuia)
    expect(w.get('input').attributes('disabled')).toBeDefined()
    expect(w.get('[role=status]').text()).toBe('Mirando la ventana…')
    expect(botones(w)).toEqual(['Salir'])
  })

  it('preparando: campo deshabilitado', () => {
    poner({ estado: 'preparando' })
    const w = mount(NotchGuia)
    expect(w.get('input').attributes('disabled')).toBeDefined()
    expect(w.get('[role=status]').text()).toBe('Preparando…')
  })

  it('con un paso se ven Hecho, siguiente y Salir', async () => {
    poner({ estado: 'paso', guia: 1, paso: 1, total: 3, texto: 'Tocá Archivo' })
    const w = mount(NotchGuia)
    expect(w.get('[role=status]').text()).toBe('Paso 1 de 3: Tocá Archivo')
    expect(botones(w)).toEqual(['Hecho, siguiente', 'Salir'])
    expect(w.get('input').attributes('disabled')).toBeUndefined()
    await w.findAll('button')[0].trigger('click')
    expect(h.siguiente).toHaveBeenCalledTimes(1)
    await w.findAll('button')[1].trigger('click')
    expect(h.terminar).toHaveBeenCalledTimes(1)
  })

  it('con fin solo se ve Listo y termina', async () => {
    poner({ estado: 'fin', guia: 1, paso: 3, total: 3, texto: 'Listo' })
    const w = mount(NotchGuia)
    expect(botones(w)).toEqual(['Listo'])
    await w.get('button').trigger('click')
    expect(h.terminar).toHaveBeenCalledTimes(1)
  })

  it('con reunión muestra el aviso y deshabilita el campo', () => {
    poner({ estado: 'reunion' })
    const w = mount(NotchGuia)
    expect(w.get('[role=status]').text()).toBe('Hay una reunión en curso: usá Mostrame del notch')
    expect(w.get('input').attributes('disabled')).toBeDefined()
    expect(botones(w)).toEqual([])
  })

  it('con error que deja seguir se puede reintentar y salir', () => {
    poner({ estado: 'error', guia: 2, sigue: true, texto: 'No me respondió: tocá Hecho, siguiente de nuevo' })
    const w = mount(NotchGuia)
    expect(botones(w)).toEqual(['Hecho, siguiente', 'Salir'])
  })

  it('con error que terminó la guía no hay botones de paso', () => {
    poner({ estado: 'error', guia: 2, sigue: false, texto: 'El ayudante no arrancó, probá de nuevo' })
    const w = mount(NotchGuia)
    expect(botones(w)).toEqual([])
  })

  it('mirando respeta movimiento reducido y las zonas táctiles no se pisan', () => {
    const css = fuente.slice(fuente.indexOf('<style'))
    expect(css).toMatch(/prefers-reduced-motion: reduce[\s\S]*\.estado\.loop\s*\{[^}]*animation:\s*none/)
    expect(fuente).toMatch(/class="estado"|:class="\{[^}]*loop: ocupada/)
    expect(css).toMatch(/button:active\s*\{[^}]*scale/)
  })

  it('saliendo: la cajita anima su salida y no toma el teclado', () => {
    const w = mount(NotchGuia, { props: { saliendo: true } })
    const section = w.get('section')
    expect(section.classes()).toContain('saliendo')
    expect(section.attributes('inert')).toBeDefined()
  })

  it('sin salir la cajita se puede usar', () => {
    const w = mount(NotchGuia)
    expect(w.get('section').classes()).not.toContain('saliendo')
    expect(w.get('section').attributes('inert')).toBeUndefined()
  })

  it('la entrada y la salida usan solo transform y opacidad, y respetan movimiento reducido', () => {
    const css = fuente.slice(fuente.indexOf('<style'))
    expect(css).toMatch(/\.saliendo \.campo\s*\{[^}]*animation:\s*campo-sale/)
    expect(css).toMatch(/@keyframes campo-sale\s*\{\s*to\s*\{[^}]*opacity:\s*0;[^}]*transform:[^}]*\}/)
    expect(css).toMatch(/prefers-reduced-motion: reduce[\s\S]*\.saliendo \.campo\s*\{[^}]*animation:\s*none/)
    expect(css).not.toMatch(/transition:\s*all/)
  })

  it('el botón principal combina con la abejita (lima)', () => {
    const css = fuente.slice(fuente.indexOf('<style'))
    expect(css).toMatch(/\.primaria\s*\{[^}]*background:\s*var\(--accent\)/)
  })
})
