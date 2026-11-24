// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, type LibItem } from '../api/types'

vi.mock('../motion', () => ({
  gsap: { set: vi.fn(), to: vi.fn(), fromTo: vi.fn() },
  haptic: vi.fn(),
  isSoft: () => true,
  useGsap: () => ({ run: (fn: () => void) => fn() }),
}))
vi.mock('../state/biblioteca', () => ({
  fresh: vi.fn(async (i: LibItem) => i),
  quitarItems: vi.fn(),
  refreshItem: vi.fn(),
  cachedLibItem: vi.fn(),
}))
const getLibraryCharla = vi.fn()
vi.mock('../state/app', () => ({
  getLibraryText: vi.fn(),
  getLibraryCharla: (...a: unknown[]) => getLibraryCharla(...a),
}))

const { default: BibViewer } = await import('./BibViewer.vue')

const raw = {
  titulo: 'Daily de pagos',
  inicio: 1_795_000_000,
  fin: 1_795_000_900,
  duracion_s: 900,
  repos: ['tienda-pagos'],
  motivo: 'sin_pc',
  resumen: ['Se acordó cambiar el reintento'],
  pendientes: ['Hablar con Nico'],
  tocadas: [{ texto: '¿Subimos el timeout?', tipo: 'pregunta', respuesta: 'Sí, a 30 s', archivos: ['pagos/cliente.py'] }],
}

const item = (over: Partial<LibItem> = {}): LibItem => ({
  id: 'a'.repeat(32), kind: 'reunion', source: 'Reunión', session_id: 's1', session_titulo: 'Sesión', project: 'p', subagent: '',
  ts: '2026-11-22T15:00:00', title: 'Daily de pagos', description: '', caption: '', nombre: '', donde: '', exists: false,
  copia: false, servible: false, motivo: '', size: 0, mime: '', url: '', version: 1, versions: [], diagrama_raw: '', src: '',
  reunion_raw: JSON.stringify(raw), tiene_charla: true,
  ...over,
})

const montar = (i: LibItem) => mount(BibViewer, { props: { item: i, hasPrev: false, hasNext: false, mode: 'panel' } })
const verCharla = (w: ReturnType<typeof montar>) => w.findAll('button').find((b) => b.text() === 'Ver la charla')

afterEach(() => getLibraryCharla.mockReset())

describe('BibViewer con una reunión', () => {
  it('muestra título, duración, motivo, resumen, pendientes y tocadas con su respuesta', () => {
    const t = montar(item()).text()
    expect(t).toContain('Daily de pagos')
    expect(t).toContain('15 min')
    expect(t).toContain('la PC dejó de avisar')
    expect(t).toContain('Se acordó cambiar el reintento')
    expect(t).toContain('Hablar con Nico')
    expect(t).toContain('¿Subimos el timeout?')
    expect(t).toContain('Sí, a 30 s')
    expect(t).toContain('pagos/cliente.py')
  })

  it('"Ver la charla" la pide por la API y la muestra como texto plano en un pre', async () => {
    getLibraryCharla.mockResolvedValue('<img src=x onerror=alert(1)> hola')
    const id = 'b'.repeat(32)
    const w = montar(item({ id }))
    await verCharla(w)!.trigger('click')
    await flushPromises()
    expect(getLibraryCharla).toHaveBeenCalledWith(id)
    const pre = w.find('pre')
    expect(pre.text()).toBe('<img src=x onerror=alert(1)> hola')
    expect(pre.find('img').exists()).toBe(false)
  })

  it('si la charla falla avisa y deja reintentar', async () => {
    getLibraryCharla.mockRejectedValueOnce(new Error('x'))
    const w = montar(item())
    await verCharla(w)!.trigger('click')
    await flushPromises()
    expect(w.text()).toContain('No pude traer la charla')
    expect(verCharla(w)).toBeDefined()
  })

  it('si el back responde 404 dice que la charla ya se borró', async () => {
    getLibraryCharla.mockRejectedValueOnce(new ApiError(404, 'No existe'))
    const w = montar(item())
    await verCharla(w)!.trigger('click')
    await flushPromises()
    expect(w.text()).toContain('La charla ya se borró (pasaron 90 días)')
    expect(verCharla(w)).toBeUndefined()
  })

  it('sin charla dice que ya se borró y no ofrece el botón', () => {
    const w = montar(item({ tiene_charla: false }))
    expect(w.text()).toContain('La charla ya se borró (pasaron 90 días)')
    expect(verCharla(w)).toBeUndefined()
    expect(getLibraryCharla).not.toHaveBeenCalled()
  })

  it('con una reunión ilegible muestra un aviso en vez de romper', () => {
    const w = montar(item({ reunion_raw: '{roto' }))
    expect(w.text()).toContain('No pude leer esta reunión')
  })
})
