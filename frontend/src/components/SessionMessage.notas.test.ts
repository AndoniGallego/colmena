// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} })) as never

const crearNota = vi.fn(async (_b: unknown) => {})
vi.mock('../state/notas', async () => {
  const { shallowRef } = await import('vue')
  return { notas: shallowRef([]), crearNota: (b: unknown) => crearNota(b) }
})
const { notas } = await import('../state/notas')
const { default: SessionMessage } = await import('./SessionMessage.vue')

const item = (kind: string, text: string, ts = '2026-11-18T10:00:00Z') => ({ kind, text, ts, idx: 1 }) as never
const montar = (it: never, extra: Record<string, unknown> = { sessionId: 's1', sessionNombre: 'Mi sesión' }) =>
  mount(SessionMessage, { props: { item: it, quiet: true, ...extra }, attachTo: document.body })

beforeEach(() => {
  crearNota.mockReset()
  crearNota.mockResolvedValue(undefined)
  ;(notas as unknown as { value: unknown[] }).value = []
  window.getSelection()?.removeAllRanges()
})

describe('SessionMessage guardar como nota', () => {
  it('tocar la acción guarda un apunte con el origen', async () => {
    const w = montar(item('claude', 'hola mundo'))
    await w.find('[data-guardar-nota]').trigger('click')
    expect(crearNota).toHaveBeenCalledWith({ tipo: 'apunte', texto: 'hola mundo', origen: { sid: 's1', nombre: 'Mi sesión', ts: '2026-11-18T10:00:00Z' } })
  })

  it('también en mensajes del usuario', async () => {
    const w = montar(item('user', 'pregunta'))
    await w.find('[data-guardar-nota]').trigger('click')
    expect(crearNota).toHaveBeenCalledOnce()
  })

  it('con una selección dentro del mensaje guarda solo la selección', async () => {
    const w = montar(item('user', 'uno dos tres'))
    const p = w.find('.text').element.firstChild as Text
    const r = document.createRange()
    r.setStart(p, 4)
    r.setEnd(p, 7)
    const s = window.getSelection()!
    s.removeAllRanges()
    s.addRange(r)
    await w.find('[data-guardar-nota]').trigger('click')
    expect(crearNota.mock.calls[0][0]).toMatchObject({ texto: 'dos' })
  })

  it('una selección fuera del mensaje se ignora', async () => {
    const fuera = document.createElement('p')
    fuera.textContent = 'ajeno'
    document.body.append(fuera)
    const w = montar(item('user', 'uno dos tres'))
    const r = document.createRange()
    r.selectNodeContents(fuera)
    const s = window.getSelection()!
    s.removeAllRanges()
    s.addRange(r)
    await w.find('[data-guardar-nota]').trigger('click')
    expect(crearNota.mock.calls[0][0]).toMatchObject({ texto: 'uno dos tres' })
  })

  it('sin sessionId no aparece la acción', () => {
    const w = montar(item('claude', 'x'), {})
    expect(w.find('[data-guardar-nota]').exists()).toBe(false)
  })

  it('con ts vacío guarda igual con origen.ts vacío', async () => {
    const w = montar(item('claude', 'x', ''))
    await w.find('[data-guardar-nota]').trigger('click')
    expect(crearNota.mock.calls[0][0]).toMatchObject({ origen: { ts: '' } })
  })

  it('si falla muestra un aviso corto', async () => {
    crearNota.mockRejectedValue(new Error('x'))
    const w = montar(item('claude', 'x'))
    await w.find('[data-guardar-nota]').trigger('click')
    await Promise.resolve()
    await w.vm.$nextTick()
    expect(w.find('[role="alert"]').text()).toContain('No pude guardar')
  })

  it('muestra la marca NOTA si el mensaje ya tiene una nota', async () => {
    const w = montar(item('claude', 'x'))
    expect(w.find('.marca-nota').exists()).toBe(false)
    ;(notas as unknown as { value: unknown[] }).value = [{ id: 'n', origen: { sid: 's1', nombre: 'a', ts: '2026-11-18T10:00:00Z' } }]
    await w.vm.$nextTick()
    expect(w.find('.marca-nota').text()).toBe('NOTA')
  })
})

describe('SessionMessage texto guardado', () => {
  it('un mensaje de Claude con bloque estado guarda solo la prosa', async () => {
    const w = montar(item('claude', 'Listo, quedó hecho.\n\n```estado\n{"hizo": "Arreglé algo"}\n```'))
    await w.find('[data-guardar-nota]').trigger('click')
    expect(crearNota.mock.calls[0][0]).toMatchObject({ texto: 'Listo, quedó hecho.' })
  })

  it('un mensaje del usuario guarda solo su texto, sin marcadores de adjuntos', async () => {
    const w = montar(item('user', 'mirá esto\n[imagen]'))
    await w.find('[data-guardar-nota]').trigger('click')
    const t = (crearNota.mock.calls[0][0] as { texto: string }).texto
    expect(t).toContain('mirá esto')
    expect(t).not.toContain('[imagen]')
  })

  it('si no queda prosa no ofrece guardar', () => {
    const w = montar(item('claude', '```estado\n{"hizo": "Algo"}\n```'))
    expect(w.find('[data-guardar-nota]').exists()).toBe(false)
  })

  it('un texto de más de 4000 caracteres se recorta con puntos suspensivos dentro del tope y avisa', async () => {
    const w = montar(item('claude', 'a'.repeat(5000)))
    await w.find('[data-guardar-nota]').trigger('click')
    const t = (crearNota.mock.calls[0][0] as { texto: string }).texto
    expect(t).toHaveLength(4000)
    expect(t.endsWith('…')).toBe(true)
    await w.vm.$nextTick()
    expect(w.find('[role="status"]').text()).toContain('recortada')
  })
})

describe('SessionMessage doble guardado', () => {
  it('dos toques seguidos crean una sola nota', async () => {
    let fin!: () => void
    crearNota.mockImplementation(() => new Promise<void>((r) => (fin = r)))
    const w = montar(item('claude', 'x'))
    const b = w.find('[data-guardar-nota]')
    await b.trigger('click')
    await b.trigger('click')
    expect(crearNota).toHaveBeenCalledTimes(1)
    expect(b.attributes('disabled')).toBeDefined()
    fin()
  })

  it('si el mensaje ya tiene nota, el botón queda deshabilitado y dice que ya está', async () => {
    ;(notas as unknown as { value: unknown[] }).value = [{ id: 'n', origen: { sid: 's1', nombre: 'a', ts: '2026-11-18T10:00:00Z' } }]
    const w = montar(item('claude', 'x'))
    const b = w.find('[data-guardar-nota]')
    expect(b.attributes('disabled')).toBeDefined()
    expect(b.attributes('aria-label')).toBe('Ya está en notas')
    await b.trigger('click')
    expect(crearNota).not.toHaveBeenCalled()
  })
})

describe('SessionMessage si la animación falla', () => {
  it('la nota queda guardada, sin aviso de error ni rechazos sin atender', async () => {
    const mov = await import('../lib/notasMovimiento')
    vi.spyOn(mov, 'destinoVisible').mockReturnValue(true)
    vi.spyOn(mov, 'guardarEnNotas').mockImplementation(() => {
      throw new Error('boom')
    })
    const btn = document.createElement('button')
    btn.setAttribute('data-notas-destino', '')
    document.body.append(btn)
    const w = montar(item('claude', 'x'))
    await w.find('[data-guardar-nota]').trigger('click')
    await new Promise((r) => setTimeout(r, 0))
    expect(crearNota).toHaveBeenCalledOnce()
    expect(w.find('[role="alert"]').exists()).toBe(false)
  })
})
