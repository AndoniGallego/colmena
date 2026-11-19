// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { h as hv } from 'vue'
import type { Nota } from '../../api/types'

const h = vi.hoisted(() => ({
  marcarHecha: vi.fn(async (_id: string, _hecha: boolean) => undefined),
  abrirColmena: vi.fn(),
  abrirNotas: vi.fn(),
}))
const lista = vi.hoisted(() => ({ ref: null as null | { value: Nota[] } }))
const motion = vi.hoisted(() => ({ soft: null as null | { value: boolean } }))

vi.mock('../../state/notas', async () => {
  const { shallowRef: sr } = await import('vue')
  lista.ref = sr<Nota[]>([])
  return { notas: lista.ref, marcarHecha: h.marcarHecha }
})
vi.mock('../../state/notch', () => ({ abrirColmena: h.abrirColmena, abrirNotas: h.abrirNotas }))
vi.mock('../../motion', async () => {
  const { ref } = await import('vue')
  motion.soft = ref(false)
  return { soft: motion.soft, isSoft: () => motion.soft!.value }
})

const { default: NotchNotas } = await import('./NotchNotas.vue')
const fuente = (await import('./NotchNotas.vue?raw')).default as string

const conTransiciones = { global: { stubs: { 'transition-group': false } } }

function nota(i: number, tipo: Nota['tipo'] = 'recordatorio'): Nota {
  return {
    id: `n${i}`,
    tipo,
    texto: `Nota ${i}`,
    hecha_at: null,
    creada_at: `2026-11-18T10:00:${String(i).padStart(2, '0')}Z`,
    editada_at: `2026-11-18T10:00:${String(i).padStart(2, '0')}Z`,
    origen: null,
  }
}

function poner(l: Nota[]) {
  lista.ref!.value = l
}

describe('NotchNotas', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    h.marcarHecha.mockReset()
    h.marcarHecha.mockResolvedValue(undefined)
    h.abrirColmena.mockReset()
    h.abrirNotas.mockReset()
    if (motion.soft) motion.soft.value = false
    poner([])
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('la cabecera dice Notas y cuántas hay para hacer, con un separador que se lee', () => {
    poner([nota(1), nota(2), nota(3, 'apunte')])
    const w = mount(NotchNotas)
    expect(w.get('.notas-cab h3').text()).toBe('Notas · 2 para hacer')
  })

  it('"Notas" se ve en mayúsculas por CSS, no escrito así', () => {
    const css = fuente.slice(fuente.indexOf('<style'))
    expect(css).toMatch(/\.notas-cab h3 \{[^}]*text-transform:\s*uppercase/)
    expect(fuente).not.toMatch(/>NOTAS</)
  })

  it('las zonas táctiles no pisan al primer renglón y "Ver las N" mide 44 px', () => {
    const css = fuente.slice(fuente.indexOf('<style'))
    const regla = (sel: string) => css.match(new RegExp(`${sel.replace(/[.]/g, '\\.')}\\s*\\{([^}]*)\\}`))?.[1] ?? ''
    const abajoCab = Number(regla('.notas-cab').match(/padding:\s*\d+px \d+px (\d+)px/)?.[1])
    const insetY = Math.abs(Number(regla('.anotar::before').match(/inset:\s*(-?\d+)px/)?.[1]))
    expect(insetY).toBeLessThanOrEqual(abajoCab)
    expect(regla('.ver-todas')).toMatch(/min-height:\s*44px/)
  })

  it('sin nada para hacer no muestra el contador', () => {
    poner([nota(1, 'apunte')])
    const w = mount(NotchNotas)
    expect(w.get('.notas-cab').text()).not.toContain('para hacer')
  })

  it('"Anotar" abre el modo notas', async () => {
    const w = mount(NotchNotas)
    await w.get('button.anotar').trigger('click')
    expect(h.abrirNotas).toHaveBeenCalledTimes(1)
  })

  it('muestra hasta 4 renglones, las más nuevas primero', () => {
    poner(Array.from({ length: 6 }, (_, i) => nota(i)))
    const w = mount(NotchNotas)
    expect(w.findAll('li.nota').map((li) => li.get('.txt').text())).toEqual(['Nota 5', 'Nota 4', 'Nota 3', 'Nota 2'])
  })

  it('con más de 4 ofrece "Ver las N notas", que abre Colmena', async () => {
    poner(Array.from({ length: 6 }, (_, i) => nota(i)))
    const w = mount(NotchNotas)
    const ver = w.get('.ver-todas')
    expect(ver.text()).toBe('Ver las 6 notas')
    await ver.trigger('click')
    expect(h.abrirColmena).toHaveBeenCalledTimes(1)
  })

  it('con 4 o menos no ofrece "Ver las notas"', () => {
    poner(Array.from({ length: 4 }, (_, i) => nota(i)))
    const w = mount(NotchNotas)
    expect(w.find('.ver-todas').exists()).toBe(false)
  })

  it('sin notas invita a anotar', () => {
    const w = mount(NotchNotas)
    expect(w.text()).toContain('Sin notas. Anotá lo que no te querés olvidar.')
    expect(w.findAll('li.nota')).toHaveLength(0)
  })

  it('el marcador distingue apunte de para hacer', () => {
    poner([nota(1), nota(2, 'apunte')])
    const w = mount(NotchNotas)
    const [ap, rec] = w.findAll('li.nota')
    expect(ap.classes()).toContain('apunte')
    expect(rec.classes()).not.toContain('apunte')
    expect(rec.find('svg.hex').exists()).toBe(true)
  })

  it('solo los para hacer tienen el botón "Marcar hecha"', () => {
    poner([nota(1), nota(2, 'apunte')])
    const w = mount(NotchNotas)
    const [ap, rec] = w.findAll('li.nota')
    expect(ap.find('button.accion').exists()).toBe(false)
    expect(rec.get('button.accion').attributes('aria-label')).toBe('Marcar hecha')
  })

  it('marcar hecha la pinta de miel, ofrece Deshacer 5 s y después sale', async () => {
    poner([nota(1)])
    const w = mount(NotchNotas)
    await w.get('button.accion').trigger('click')
    await flushPromises()
    expect(h.marcarHecha).toHaveBeenCalledWith('n1', true)
    expect(w.get('li.nota').classes()).toContain('hecha')
    expect(w.get('button.deshacer').text()).toBe('Deshacer')
    poner([])
    await flushPromises()
    expect(w.find('button.deshacer').exists()).toBe(true)
    vi.advanceTimersByTime(5000)
    await flushPromises()
    expect(w.findAll('li.nota')).toHaveLength(0)
  })

  it('Deshacer la vuelve a dejar para hacer', async () => {
    poner([nota(1)])
    const w = mount(NotchNotas)
    await w.get('button.accion').trigger('click')
    await flushPromises()
    await w.get('button.deshacer').trigger('click')
    await flushPromises()
    expect(h.marcarHecha).toHaveBeenLastCalledWith('n1', false)
    expect(w.get('li.nota').classes()).not.toContain('hecha')
    expect(w.find('button.accion').exists()).toBe(true)
  })

  it('con el teclado, al marcar hecha el foco pasa a Deshacer y se anuncia', async () => {
    poner([nota(1), nota(2)])
    const w = mount(NotchNotas, { attachTo: document.body })
    const accion = w.get('li[data-id="n1"] button.accion')
    ;(accion.element as HTMLElement).focus()
    await accion.trigger('click')
    await flushPromises()
    expect(document.activeElement).toBe(w.get('li[data-id="n1"] button.deshacer').element)
    expect(w.get('[aria-live="polite"]').text()).toBe('Nota hecha')
    w.unmount()
  })

  it('al deshacer el foco vuelve al ✓ de ese renglón y se anuncia', async () => {
    poner([nota(1), nota(2)])
    const w = mount(NotchNotas, { attachTo: document.body })
    await w.get('li[data-id="n1"] button.accion').trigger('click')
    await flushPromises()
    await w.get('li[data-id="n1"] button.deshacer').trigger('click')
    await flushPromises()
    expect(document.activeElement).toBe(w.get('li[data-id="n1"] button.accion').element)
    expect(w.get('[aria-live="polite"]').text()).toBe('Nota restaurada')
    w.unmount()
  })

  it('si falla marcar, el foco vuelve al ✓ y no anuncia "hecha"', async () => {
    h.marcarHecha.mockRejectedValueOnce(new Error('boom'))
    poner([nota(1)])
    const w = mount(NotchNotas, { attachTo: document.body })
    await w.get('button.accion').trigger('click')
    await flushPromises()
    expect(document.activeElement).toBe(w.get('button.accion').element)
    expect(w.get('[aria-live="polite"]').text()).toBe('')
    w.unmount()
  })

  it('si falla marcar avisa en castellano', async () => {
    h.marcarHecha.mockRejectedValueOnce(new Error('boom'))
    poner([nota(1)])
    const w = mount(NotchNotas)
    await w.get('button.accion').trigger('click')
    await flushPromises()
    expect(w.get('[role="alert"]').text()).toBe('No pude marcarla. Probá de nuevo.')
    expect(w.find('button.deshacer').exists()).toBe(false)
  })

  it('tocar el texto abre Colmena y no marca nada', async () => {
    poner([nota(1), nota(2, 'apunte')])
    const w = mount(NotchNotas)
    for (const b of w.findAll('button.txt')) await b.trigger('click')
    expect(h.abrirColmena).toHaveBeenCalledTimes(2)
    expect(h.marcarHecha).not.toHaveBeenCalled()
  })

  it('el nombre accesible del texto recorta notas largas', () => {
    poner([{ ...nota(1), texto: 'y'.repeat(4000) }])
    const w = mount(NotchNotas)
    const l = w.get('button.txt').attributes('aria-label')!
    expect(l.length).toBeLessThan(200)
    expect(l).toContain('…')
  })

  it('puede ocultar "Anotar" o toda la cabecera', () => {
    poner([nota(1)])
    expect(mount(NotchNotas, { props: { anotar: false } }).find('button.anotar').exists()).toBe(false)
    const sinCab = mount(NotchNotas, { props: { cabecera: false } })
    expect(sinCab.find('.notas-cab').exists()).toBe(false)
    expect(sinCab.findAll('li.nota')).toHaveLength(1)
  })

  it('lo que va en el slot queda entre la cabecera y la lista', () => {
    poner([nota(1)])
    const w = mount(NotchNotas, { slots: { default: () => hv('div', { class: 'campo-stub' }) } })
    const html = w.html()
    expect(html.indexOf('notas-cab')).toBeLessThan(html.indexOf('campo-stub'))
    expect(html.indexOf('campo-stub')).toBeLessThan(html.indexOf('class="lista"'))
  })

  describe('movimiento', () => {
    it('las notas que ya estaban no entran animadas', () => {
      poner([nota(1)])
      const w = mount(NotchNotas, conTransiciones)
      expect(w.get('li.nota').classes().some((c) => c.includes('enter'))).toBe(false)
    })

    it('una nota nueva entra con la transición de renglón', async () => {
      poner([nota(1)])
      const w = mount(NotchNotas, conTransiciones)
      poner([nota(2), nota(1)])
      await w.vm.$nextTick()
      const nueva = w.get('li[data-id="n2"]')
      expect(nueva.classes()).toContain('fila-enter-active')
      expect(w.get('li[data-id="n1"]').classes()).not.toContain('fila-enter-active')
    })

    it('solo late el marcador de la nota recién guardada, no el que sube a ocupar un lugar', async () => {
      poner([nota(1), nota(2), nota(3), nota(4), nota(5)])
      const w = mount(NotchNotas, conTransiciones)
      poner([nota(6), nota(1), nota(2), nota(3), nota(4), nota(5)])
      await w.vm.$nextTick()
      expect(w.get('li[data-id="n6"]').classes()).toContain('recien')
      poner([nota(1), nota(2), nota(3), nota(4), nota(5)])
      await w.vm.$nextTick()
      const sube = w.get('li[data-id="n2"]')
      expect(sube.classes()).toContain('fila-enter-active')
      expect(sube.classes()).not.toContain('recien')
    })

    it('en modo suave la nota nueva solo se funde', async () => {
      motion.soft!.value = true
      poner([nota(1)])
      const w = mount(NotchNotas, conTransiciones)
      poner([nota(2), nota(1)])
      await w.vm.$nextTick()
      const clases = w.get('li[data-id="n2"]').classes()
      expect(clases).toContain('fila-suave-enter-active')
      expect(clases).not.toContain('fila-enter-active')
    })

    it('al vencer el Deshacer el renglón sale fijando su alto para colapsarlo', async () => {
      poner([nota(1), nota(2)])
      const w = mount(NotchNotas, conTransiciones)
      await w.get('li[data-id="n1"] button.accion').trigger('click')
      await flushPromises()
      poner([nota(2)])
      vi.advanceTimersByTime(5000)
      await flushPromises()
      const sale = w.get('li[data-id="n1"]')
      expect(sale.classes()).toContain('fila-leave-active')
      expect((sale.element as HTMLElement).style.height).toMatch(/px$/)
    })

    it('los valores de movimiento son los del diseño y el modo suave no mueve nada', () => {
      const css = fuente.slice(fuente.indexOf('<style'))
      const regla = (sel: string) => css.match(new RegExp(`${sel.replace(/[.]/g, '\\.')}[^{]*\\{([^}]*)\\}`))?.[1] ?? ''
      expect(regla('.fila-enter-from')).toMatch(/translateY\(-4px\)/)
      expect(regla('.fila-enter-active')).toMatch(/200ms/)
      expect(css).toMatch(/@keyframes latido\s*\{\s*50%\s*\{\s*transform:\s*scale\(1\.18\)/)
      expect(regla('.fila-enter-active.recien .hex')).toMatch(/320ms/)
      expect(regla('.fila-leave-active')).toMatch(/opacity 200ms/)
      expect(regla('.fila-leave-active')).toMatch(/height 200ms/)
      expect(regla('.fila-move')).toMatch(/transform 200ms/)
      const suave = [...css.matchAll(/\.fila-suave[^{]*\{([^}]*)\}/g)].map((m) => m[1]).join('\n')
      expect(suave).not.toMatch(/transform|translate|scale|height/)
      expect(suave).toMatch(/150ms/)
      expect(css).not.toMatch(/transition:\s*all/)
    })
  })
})
