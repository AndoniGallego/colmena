// @vitest-environment jsdom
import { createApp, nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { UsoPlan } from '../lib/usoPlan'

vi.mock('../motion', () => ({ gsap: { quickSetter: () => () => {}, to: () => ({ kill() {} }), set: () => {} }, isSoft: () => true, useGsap: () => ({ run: (fn: () => void) => fn() }) }))

const { default: UsoPlanPill } = await import('./UsoPlanPill.vue')

const futuro = (min: number) => new Date(Date.now() + min * 60_000).toISOString()
const plan = (extra: Partial<UsoPlan> = {}): UsoPlan => ({
  fiveHour: { pct: 23.4, resetsAt: futuro(130), vencido: false },
  sevenDay: { pct: 41, resetsAt: futuro(3 * 1440), vencido: false },
  actualizado: new Date().toISOString(),
  edadS: 5,
  ...extra,
})

let app: ReturnType<typeof createApp> | null = null
let host: HTMLElement
async function montar(props: Record<string, unknown>) {
  host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp(UsoPlanPill, props)
  app.mount(host)
  await nextTick()
  await Promise.resolve()
  await nextTick()
}
function pantalla(ancha: boolean) {
  vi.stubGlobal('matchMedia', (q: string) => ({ matches: ancha && q.includes('640px'), media: q, addEventListener() {}, removeEventListener() {} }))
}
afterEach(() => {
  vi.unstubAllGlobals()
  app?.unmount()
  app = null
  host?.remove()
  document.body.innerHTML = ''
})

describe('UsoPlanPill', () => {
  it('sin datos no renderiza nada', async () => {
    await montar({ cargar: async () => null })
    expect(host.querySelector('.uso-plan')).toBeNull()
    expect(host.querySelector('button')).toBeNull()
  })

  it('si falla la carga tampoco ocupa lugar', async () => {
    await montar({ cargar: async () => { throw new Error('x') } })
    expect(host.querySelector('button')).toBeNull()
  })

  it('en escritorio muestra el texto y el aria-label', async () => {
    await montar({ cargar: async () => plan() })
    const b = host.querySelector('button')!
    expect(b.textContent).toContain('5h 23% · sem 41%')
    expect(b.getAttribute('aria-label')).toBe('Plan de Claude: 23% de 5 horas, 41% semanal')
  })

  it('compact: mini anillo doble sin texto', async () => {
    await montar({ compact: true, cargar: async () => plan() })
    const b = host.querySelector('button')!
    expect(b.querySelectorAll('svg.mini circle.arc').length).toBe(2)
    expect(b.textContent?.trim()).toBe('')
    expect(b.getAttribute('aria-label')).toContain('23% de 5 horas')
  })

  it('vencida muestra renovado en vez del porcentaje', async () => {
    await montar({ cargar: async () => plan({ fiveHour: { pct: 95, resetsAt: futuro(-1), vencido: true } }) })
    expect(host.querySelector('button')!.textContent).toContain('5h renovado')
  })

  it('al tocar abre el detalle con quedan y se renueva en', async () => {
    await montar({ cargar: async () => plan() })
    expect(document.body.querySelector('[role="dialog"]')).toBeNull()
    host.querySelector('button')!.click()
    await nextTick()
    const d = document.body.querySelector('[role="dialog"]')!
    expect(d).not.toBeNull()
    expect(d.textContent).toContain('23% usado')
    expect(d.textContent).toContain('Quedan 77%')
    expect(d.textContent).toContain('se renueva en 2 h')
    expect(d.textContent).toContain('Actualizado')
  })

  it('datos viejos se marcan grises', async () => {
    await montar({ cargar: async () => plan({ actualizado: new Date(Date.now() - 3600_000).toISOString() }) })
    expect(host.querySelector('.uso-plan')!.classList.contains('gris')).toBe(true)
  })

  it('compact: cada ventana en su anillo por clave', async () => {
    await montar({ compact: true, cargar: async () => plan({ fiveHour: null }) })
    const arcos = [...host.querySelectorAll('svg.mini circle.arc')]
    expect(arcos.length).toBe(1)
    expect(arcos[0].getAttribute('r')).toBe('5')
    expect(host.querySelectorAll('svg.mini circle.track').length).toBe(2)
    app?.unmount()
    host.remove()
    await montar({ compact: true, cargar: async () => plan({ sevenDay: null }) })
    const solo5 = [...host.querySelectorAll('svg.mini circle.arc')]
    expect(solo5.length).toBe(1)
    expect(solo5[0].getAttribute('r')).toBe('9')
  })

  it('si el plan desaparece con la hoja abierta, se cierra y no reaparece sola', async () => {
    let actual: UsoPlan | null = plan()
    await montar({ cargar: async () => actual })
    host.querySelector('button')!.click()
    await nextTick()
    expect(document.body.querySelector('[role="dialog"]')).not.toBeNull()
    actual = null
    document.dispatchEvent(new Event('visibilitychange'))
    await nextTick()
    await Promise.resolve()
    await nextTick()
    expect(document.body.querySelector('[role="dialog"]')).toBeNull()
    actual = plan()
    document.dispatchEvent(new Event('visibilitychange'))
    await nextTick()
    await Promise.resolve()
    await nextTick()
    expect(host.querySelector('button')).not.toBeNull()
    expect(document.body.querySelector('[role="dialog"]')).toBeNull()
  })

  it('en escritorio el panel se ancla al rect del botón', async () => {
    pantalla(true)
    Object.defineProperty(window, 'innerWidth', { value: 1200, configurable: true })
    await montar({ cargar: async () => plan() })
    const b = host.querySelector('button')!
    b.getBoundingClientRect = () => ({ top: 10, bottom: 40, left: 900, right: 1000, width: 100, height: 30, x: 900, y: 10, toJSON() {} }) as DOMRect
    b.click()
    await nextTick()
    const p = document.body.querySelector('[role="dialog"]') as HTMLElement
    expect(p.style.top).toBe('50px')
    expect(p.style.right).toBe('196px')
    expect(p.classList.contains('arriba')).toBe(false)
    expect(p.classList.contains('ancla')).toBe(true)
  })

  it('en el celu el panel es la hoja superior y sin posición inline', async () => {
    pantalla(false)
    await montar({ cargar: async () => plan() })
    host.querySelector('button')!.click()
    await nextTick()
    const p = document.body.querySelector('[role="dialog"]') as HTMLElement
    expect(p.classList.contains('arriba')).toBe(true)
    expect(p.style.top).toBe('')
  })

  it('el CSS apaga desplazamiento en modo suave y reducir movimiento con la misma especificidad', async () => {
    const { readFileSync } = await import('node:fs')
    const css = readFileSync('src/components/UsoPlanPill.vue', 'utf8')
    for (const sel of ['.up-enter-from .up.arriba', '.up-leave-to .up.arriba', '.up-enter-from .up.ancla']) {
      expect(css).toContain(`:root[data-motion='soft'] ${sel}`)
    }
    const media = css.slice(css.indexOf('@media (prefers-reduced-motion: reduce)'))
    expect(media).toContain('.up-enter-from .up.arriba')
    expect(media).toContain('.up-enter-from .up.ancla')
    expect(css).not.toMatch(/\.up\.ancla \{[^}]*opacity: 0/)
  })
})
