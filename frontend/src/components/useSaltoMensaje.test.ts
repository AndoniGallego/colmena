// @vitest-environment jsdom
import { effectScope, nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} })) as never
const { useSaltoMensaje } = await import('./useSaltoMensaje')
const { saltoMensaje } = await import('../state/notas')

const scopes: ReturnType<typeof effectScope>[] = []
function armar(opts: { visible?: boolean; sid?: string | null } = {}) {
  const el = document.createElement('div')
  el.getClientRects = (() => (opts.visible === false ? [] : [{}])) as never
  const art = document.createElement('article')
  art.dataset.ts = 'b'
  art.scrollIntoView = vi.fn()
  el.append(art)
  const scroller = ref<HTMLElement | null>(el)
  const mensajes = ref(1)
  const sid = ref<string | null>(opts.sid === undefined ? 's1' : opts.sid)
  const cargado = ref(true)
  const verCambios = ref(false)
  const stick = ref(true)
  const toBottom = vi.fn()
  const scope = effectScope()
  scopes.push(scope)
  scope.run(() => useSaltoMensaje({ scroller, mensajes, sid, cargado, verCambios, stick, toBottom }))
  return { art, scroller, mensajes, sid, cargado, verCambios, stick, toBottom }
}
const flush = async () => {
  for (let i = 0; i < 5; i++) await nextTick()
  await new Promise((r) => setTimeout(r, 0))
}

afterEach(() => {
  scopes.splice(0).forEach((s) => s.stop())
})

beforeEach(() => {
  saltoMensaje.value = null
})

describe('useSaltoMensaje', () => {
  it('salta al mensaje de la sesión abierta, suelta el pegado al fondo y limpia', async () => {
    const t = armar()
    saltoMensaje.value = { sid: 's1', ts: 'b' }
    await flush()
    expect(t.art.scrollIntoView).toHaveBeenCalled()
    expect(t.stick.value).toBe(false)
    expect(t.toBottom).not.toHaveBeenCalled()
    expect(saltoMensaje.value).toBeNull()
  })
  it('con un ts desconocido va al final y limpia', async () => {
    const t = armar()
    saltoMensaje.value = { sid: 's1', ts: 'nope' }
    await flush()
    expect(t.art.scrollIntoView).not.toHaveBeenCalled()
    expect(t.toBottom).toHaveBeenCalledOnce()
    expect(saltoMensaje.value).toBeNull()
  })
  it('para otra sesión no hace nada y no limpia', async () => {
    const t = armar()
    saltoMensaje.value = { sid: 'otra', ts: 'b' }
    await flush()
    expect(t.art.scrollIntoView).not.toHaveBeenCalled()
    expect(t.toBottom).not.toHaveBeenCalled()
    expect(saltoMensaje.value).toEqual({ sid: 'otra', ts: 'b' })
  })
  it('espera a que cargue y salta cuando carga', async () => {
    const t = armar()
    t.cargado.value = false
    saltoMensaje.value = { sid: 's1', ts: 'b' }
    await flush()
    expect(saltoMensaje.value).not.toBeNull()
    t.cargado.value = true
    await flush()
    expect(t.art.scrollIntoView).toHaveBeenCalled()
    expect(saltoMensaje.value).toBeNull()
  })
  it('con el scroller oculto espera y no limpia', async () => {
    const t = armar({ visible: false })
    saltoMensaje.value = { sid: 's1', ts: 'b' }
    await flush()
    expect(t.art.scrollIntoView).not.toHaveBeenCalled()
    expect(saltoMensaje.value).not.toBeNull()
  })
  it('al cerrar el chat se limpia un salto pendiente', async () => {
    const t = armar()
    saltoMensaje.value = { sid: 'otra', ts: 'b' }
    await flush()
    t.sid.value = null
    await flush()
    expect(saltoMensaje.value).toBeNull()
  })
})
