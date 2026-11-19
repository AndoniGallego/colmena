import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, nextTick, ref } from 'vue'
import { RETENER_RESUMEN_MS, type Resumen } from '../lib/notchCeldas'

vi.hoisted(() => {
  vi.stubGlobal('window', {
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    addEventListener() {},
    screen: { availWidth: 800, availHeight: 600 },
  })
  vi.stubGlobal('location', { search: '', pathname: '/notch' })
})

vi.mock('../motion', () => ({
  isSoft: () => true,
  gsap: { set() {}, to() {}, fromTo() {}, killTweensOf() {} },
}))

const { crearResumenVisible } = await import('./notchResumen')

function r(over: Partial<Resumen> = {}): Resumen {
  return { teToca: 0, trabajando: 0, termino: 0, ...over }
}

describe('crearResumenVisible', () => {
  it('actualizaciones repetidas durante la espera no la estiran', async () => {
    vi.useFakeTimers()
    const fuente = ref(r({ trabajando: 1 }))
    const { visible, detener } = crearResumenVisible(fuente, ref(false))
    fuente.value = r({ trabajando: 0 })
    await nextTick()
    vi.advanceTimersByTime(3000)
    fuente.value = r({ trabajando: 0 })
    await nextTick()
    vi.advanceTimersByTime(RETENER_RESUMEN_MS - 3000)
    expect(visible.value).toEqual(r({ trabajando: 0 }))
    detener()
    vi.useRealTimers()
  })

  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('retiene y aplica a los 4500 ms', async () => {
    const fuente = ref(r({ trabajando: 1 }))
    const hayAviso = ref(false)
    const { visible, detener } = crearResumenVisible(fuente, hayAviso)

    expect(visible.value).toEqual(r({ trabajando: 1 }))

    fuente.value = r({ trabajando: 0 })
    await nextTick()
    expect(visible.value).toEqual(r({ trabajando: 1 }))

    vi.advanceTimersByTime(RETENER_RESUMEN_MS - 1)
    expect(visible.value).toEqual(r({ trabajando: 1 }))

    vi.advanceTimersByTime(1)
    await nextTick()
    expect(visible.value).toEqual(r({ trabajando: 0 }))
    detener()
  })

  it('aviso a los 3000 ms aplica el resumen actual en ese momento', async () => {
    const fuente = ref(r({ trabajando: 1 }))
    const hayAviso = ref(false)
    const { visible, detener } = crearResumenVisible(fuente, hayAviso)

    fuente.value = r({ trabajando: 0 })
    await nextTick()
    expect(visible.value).toEqual(r({ trabajando: 1 }))

    vi.advanceTimersByTime(3000)
    hayAviso.value = true
    await nextTick()
    expect(visible.value).toEqual(r({ trabajando: 0 }))

    vi.advanceTimersByTime(RETENER_RESUMEN_MS)
    expect(visible.value).toEqual(r({ trabajando: 0 }))
    detener()
  })

  it('subida de trabajando se aplica al instante', async () => {
    const fuente = ref(r({ trabajando: 1 }))
    const hayAviso = ref(false)
    const { visible, detener } = crearResumenVisible(fuente, hayAviso)

    fuente.value = r({ trabajando: 2 })
    await nextTick()
    expect(visible.value).toEqual(r({ trabajando: 2 }))
    detener()
  })

  it('cancela el timer al aplicar un cambio no retenido', async () => {
    const fuente = ref(r({ trabajando: 1 }))
    const hayAviso = ref(false)
    const { visible, detener } = crearResumenVisible(fuente, hayAviso)

    fuente.value = r({ trabajando: 0 })
    await nextTick()
    expect(visible.value).toEqual(r({ trabajando: 1 }))

    fuente.value = r({ trabajando: 2 })
    await nextTick()
    expect(visible.value).toEqual(r({ trabajando: 2 }))

    vi.advanceTimersByTime(RETENER_RESUMEN_MS)
    expect(visible.value).toEqual(r({ trabajando: 2 }))
    detener()
  })

  it('varios cambios retenidos seguidos aplican el último valor de la fuente', async () => {
    const fuente = ref(r({ trabajando: 2 }))
    const hayAviso = ref(false)
    const { visible, detener } = crearResumenVisible(fuente, hayAviso)

    fuente.value = r({ trabajando: 1 })
    fuente.value = r({ trabajando: 0, termino: 1 })
    await nextTick()
    expect(visible.value).toEqual(r({ trabajando: 2 }))

    vi.advanceTimersByTime(RETENER_RESUMEN_MS)
    await nextTick()
    expect(visible.value).toEqual(r({ trabajando: 0, termino: 1 }))
    detener()
  })

  it('hayAviso como computed reacciona igual que un ref', async () => {
    const fuente = ref(r({ trabajando: 1 }))
    const aviso = ref(false)
    const hayAviso = computed(() => aviso.value)
    const { visible, detener } = crearResumenVisible(fuente, hayAviso)

    fuente.value = r({ trabajando: 0 })
    await nextTick()
    aviso.value = true
    await nextTick()
    expect(visible.value).toEqual(r({ trabajando: 0 }))
    detener()
  })
})
