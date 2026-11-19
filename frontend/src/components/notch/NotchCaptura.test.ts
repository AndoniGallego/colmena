// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../api/types'

const h = vi.hoisted(() => ({
  crearNota: vi.fn(async (_b: unknown) => undefined),
  encolar: vi.fn(),
}))

vi.mock('../../state/notas', () => ({ crearNota: h.crearNota }))
vi.mock('../../lib/notasCola', async (orig) => {
  const real = await orig<typeof import('../../lib/notasCola')>()
  return { ...real, encolar: h.encolar }
})
const motion = vi.hoisted(() => ({ soft: true }))

/** Simula el efecto de GSAP en el DOM: aplica el estado final y corre onComplete. */
function aplicar(target: unknown, vars: Record<string, unknown>) {
  const els = (Array.isArray(target) ? target : [target]) as HTMLElement[]
  for (const el of els) {
    if (!(el instanceof HTMLElement)) continue
    if ('autoAlpha' in vars) {
      el.style.opacity = String(vars.autoAlpha)
      el.style.visibility = vars.autoAlpha === 0 ? 'hidden' : 'inherit'
      if (vars.autoAlpha === 0 && document.activeElement === el) el.blur()
    }
    if ('opacity' in vars) el.style.opacity = String(vars.opacity)
  }
}

vi.mock('../../motion', () => ({
  gsap: {
    set(t: unknown, v: Record<string, unknown>) {
      aplicar(t, v)
    },
    to(t: unknown, v: Record<string, unknown>) {
      aplicar(t, v)
      ;(v.onComplete as (() => void) | undefined)?.()
    },
    fromTo(t: unknown, desde: Record<string, unknown>, hasta: Record<string, unknown>) {
      aplicar(t, desde)
      aplicar(t, hasta)
      ;(hasta.onComplete as (() => void) | undefined)?.()
    },
    killTweensOf() {},
    timeline: () => ({ to() { return this }, fromTo() { return this }, set() { return this }, kill() {} }),
  },
  isSoft: () => motion.soft,
}))

const { default: NotchCaptura } = await import('./NotchCaptura.vue')
const fuente = (await import('./NotchCaptura.vue?raw')).default as string

function montar() {
  return mount(NotchCaptura, { attachTo: document.body })
}

async function tipear(w: ReturnType<typeof montar>, texto: string) {
  await w.get('textarea').setValue(texto)
}

const presionado = (w: ReturnType<typeof montar>) => w.get('.tipos button[aria-pressed="true"]').text()

const enter = (w: ReturnType<typeof montar>) => w.get('textarea').trigger('keydown', { key: 'Enter' })

describe('NotchCaptura', () => {
  beforeEach(() => {
    h.crearNota.mockReset()
    h.crearNota.mockResolvedValue(undefined)
    h.encolar.mockReset()
  })
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('arranca con el foco en el texto', async () => {
    const w = montar()
    await flushPromises()
    expect(document.activeElement).toBe(w.get('textarea').element)
    w.unmount()
  })

  it('con movimiento completo, al terminar de entrar el foco sigue en el texto', async () => {
    motion.soft = false
    try {
      const w = montar()
      await flushPromises()
      const campo = w.get('textarea').element as HTMLTextAreaElement
      expect(campo.style.visibility).not.toBe('hidden')
      expect(document.activeElement).toBe(campo)
      w.unmount()
    } finally {
      motion.soft = true
    }
  })

  it('Tab alterna entre Para hacer y Apunte en el segmentado', async () => {
    const w = montar()
    expect(presionado(w)).toBe('Para hacer')
    await w.get('textarea').trigger('keydown', { key: 'Tab' })
    expect(presionado(w)).toBe('Apunte')
    await w.get('textarea').trigger('keydown', { key: 'Tab' })
    expect(presionado(w)).toBe('Para hacer')
    w.unmount()
  })

  it('Shift+Tab no alterna: queda libre para salir del campo con el teclado', async () => {
    const w = montar()
    const ev = new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, cancelable: true, bubbles: true })
    w.get('textarea').element.dispatchEvent(ev)
    await w.vm.$nextTick()
    expect(presionado(w)).toBe('Para hacer')
    expect(ev.defaultPrevented).toBe(false)
    w.unmount()
  })

  it('el segmentado "Apunte | Para hacer" elige el tipo y no alterna al tocar el elegido', async () => {
    const w = montar()
    const [apunte, paraHacer] = w.findAll('.tipos button')
    expect(apunte.text()).toBe('Apunte')
    expect(paraHacer.text()).toBe('Para hacer')
    expect(w.get('.tipos').attributes('role')).toBe('group')
    await apunte.trigger('click')
    expect(apunte.attributes('aria-pressed')).toBe('true')
    expect(paraHacer.attributes('aria-pressed')).toBe('false')
    await apunte.trigger('click')
    expect(presionado(w)).toBe('Apunte')
    await tipear(w, 'Idea')
    await enter(w)
    await flushPromises()
    expect(h.crearNota).toHaveBeenCalledWith({ tipo: 'apunte', texto: 'Idea' })
    w.unmount()
  })

  it('el campo es un rectángulo con textarea y el pie explica las teclas', () => {
    const w = montar()
    expect(w.find('.cap-celda').exists()).toBe(false)
    expect(w.find('.cap-sello').exists()).toBe(false)
    expect(w.get('.campo-pie').text()).toBe('Enter guarda · Esc cierra')
    w.unmount()
  })

  it('Enter con texto guarda y avisa que se guardó', async () => {
    const w = montar()
    await tipear(w, '  Preguntar en la daily  ')
    await w.get('textarea').trigger('keydown', { key: 'Tab' })
    await enter(w)
    await flushPromises()
    expect(h.crearNota).toHaveBeenCalledWith({ tipo: 'apunte', texto: 'Preguntar en la daily' })
    expect(w.emitted('guardada')).toEqual([[{ tipo: 'apunte', sinConexion: false }]])
    w.unmount()
  })

  it('Enter con solo espacios no hace nada y conserva el texto', async () => {
    const w = montar()
    await tipear(w, '   ')
    await enter(w)
    await flushPromises()
    expect(h.crearNota).not.toHaveBeenCalled()
    expect(w.emitted('guardada')).toBeUndefined()
    expect((w.get('textarea').element as HTMLTextAreaElement).value).toBe('   ')
    w.unmount()
  })

  it('sin red la encola, lo dice y cierra igual', async () => {
    h.crearNota.mockRejectedValue(new TypeError('Failed to fetch'))
    const w = montar()
    await tipear(w, 'Llamar al banco')
    await enter(w)
    await flushPromises()
    expect(h.encolar).toHaveBeenCalledWith({ tipo: 'recordatorio', texto: 'Llamar al banco' })
    expect(w.text()).toContain('sin conexión, la guardo cuando vuelva')
    expect(w.emitted('guardada')).toEqual([[{ tipo: 'recordatorio', sinConexion: true }]])
    w.unmount()
  })

  it('con un 422 muestra el error y conserva el texto', async () => {
    h.crearNota.mockRejectedValue(new ApiError(422, 'El texto es demasiado largo'))
    const w = montar()
    await tipear(w, 'Algo')
    await enter(w)
    await flushPromises()
    expect(h.encolar).not.toHaveBeenCalled()
    expect(w.get('[role="alert"]').text()).toBe('El texto es demasiado largo')
    expect((w.get('textarea').element as HTMLTextAreaElement).value).toBe('Algo')
    expect(w.emitted('guardada')).toBeUndefined()
    w.unmount()
  })

  it('Esc cierra sin guardar', async () => {
    const w = montar()
    await tipear(w, 'borrador')
    await w.get('textarea').trigger('keydown', { key: 'Escape' })
    expect(w.emitted('cerrar')).toHaveLength(1)
    expect(h.crearNota).not.toHaveBeenCalled()
    w.unmount()
  })

  it('el campo entra con opacity y 4 px en 180 ms; en modo suave solo se funde', () => {
    const css = fuente.slice(fuente.indexOf('<style'))
    expect(css).toMatch(/\.campo\s*\{[^}]*animation:\s*campo-entra 180ms var\(--ease-out\)/)
    expect(css).toMatch(/@keyframes campo-entra\s*\{\s*from\s*\{\s*opacity:\s*0;\s*transform:\s*translateY\(4px\)/)
    expect(css).toMatch(/:root\[data-motion='soft'\] \.campo\s*\{\s*animation:\s*campo-funde 150ms/)
    const funde = css.match(/@keyframes campo-funde\s*\{[\s\S]*?\}\s*\}/)![0]
    expect(funde).not.toMatch(/transform/)
  })
})
