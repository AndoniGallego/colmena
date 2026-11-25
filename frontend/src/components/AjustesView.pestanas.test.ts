// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const desktopRef = ref(false)

vi.mock('../motion', () => ({
  gsap: { from() {}, fromTo() {} },
  isSoft: () => true,
  motionPref: ref('full'),
  setMotion: () => {},
  systemReduced: ref(false),
  useGsap: () => ({ run: (fn: () => void) => fn() }),
}))
vi.mock('../lib/viewport', () => ({ get desktop() { return desktopRef } }))
vi.mock('../lib/keyboard', () => ({
  useKeyboard: () => ({ open: ref(false), height: ref(null), top: ref(0) }),
}))
vi.mock('../lib/theme', () => ({ setTheme: () => {}, theme: ref('light') }))
const setAtajos = vi.fn(async (_: unknown) => undefined)
vi.mock('../state/app', () => ({
  revokeAllSessions: vi.fn(async () => true),
  revokeSessionsErr: ref(''),
  auth: ref('ready'),
  getAtajos: vi.fn(async () => ({})),
  setAtajos: (a: unknown) => setAtajos(a),
}))
vi.mock('../state/ajustes', () => ({ closeAjustes: vi.fn() }))
vi.mock('../state/limpieza', () => ({ abrirLimpieza: vi.fn() }))
vi.mock('./Icon.vue', () => ({ default: { name: 'Icon', render: () => null } }))
vi.mock('./SegControl.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./ClaudePanel.vue', () => ({ default: { template: '<div class="m-claude">claude-panel</div>' } }))
vi.mock('./NotificationsSection.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./PermisosHistorial.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./MemoriaSection.vue', () => ({ default: { template: '<div class="m-memoria">memoria-section</div>' } }))
vi.mock('./ViewFrame.vue', () => ({
  default: { name: 'ViewFrame', template: '<div><slot name="back" /><slot /></div>' },
}))

const { default: AjustesView } = await import('./AjustesView.vue')
const { atajosGuardados, capturandoAtajo } = await import('../state/atajos')
const KEY = 'colmena.ajustes.pestana'

function montar() {
  return mount(AjustesView, { attachTo: document.body })
}
const tabs = (w: ReturnType<typeof montar>) => w.findAll('[role="tab"]')

beforeEach(() => {
  document.body.innerHTML = ''
  localStorage.clear()
  desktopRef.value = false
  atajosGuardados.value = {}
  capturandoAtajo.value = false
  vi.restoreAllMocks()
  setAtajos.mockClear()
})

describe('AjustesView por pestañas', () => {
  it('muestra solo el panel activo', () => {
    const w = montar()
    expect(w.findAll('[role="tabpanel"]')).toHaveLength(1)
    expect(tabs(w)[0].attributes('aria-selected')).toBe('true')
    expect(w.text()).not.toContain('memoria-section')
  })

  it('al tocar otra pestaña cambia el panel y aria-selected', async () => {
    const w = montar()
    const t = tabs(w)
    await t[2].trigger('click')
    expect(t[2].attributes('aria-selected')).toBe('true')
    expect(t[0].attributes('aria-selected')).toBe('false')
    expect(w.find('[role="tabpanel"]').attributes('aria-labelledby')).toBe(t[2].attributes('id'))
    expect(t[2].attributes('aria-controls')).toBe(w.find('[role="tabpanel"]').attributes('id'))
    expect(w.text()).toContain('memoria-section')
  })

  it('la flecha abajo o derecha pasa a la siguiente, Home y End van a los extremos', async () => {
    const w = montar()
    const lista = w.find('[role="tablist"]')
    await lista.trigger('keydown', { key: 'ArrowRight' })
    expect(tabs(w)[1].attributes('aria-selected')).toBe('true')
    await lista.trigger('keydown', { key: 'ArrowDown' })
    expect(tabs(w)[2].attributes('aria-selected')).toBe('true')
    await lista.trigger('keydown', { key: 'End' })
    expect(tabs(w).at(-1)!.attributes('aria-selected')).toBe('true')
    await lista.trigger('keydown', { key: 'Home' })
    expect(tabs(w)[0].attributes('aria-selected')).toBe('true')
  })

  it('recuerda la pestaña y la restaura al montar', async () => {
    const w = montar()
    await tabs(w)[1].trigger('click')
    expect(localStorage.getItem(KEY)).toBe('claude')
    w.unmount()
    const w2 = montar()
    expect(tabs(w2)[1].attributes('aria-selected')).toBe('true')
  })

  it('si la guardada no existe abre la primera', () => {
    localStorage.setItem(KEY, 'mantenimiento')
    const w = montar()
    expect(tabs(w)[0].attributes('aria-selected')).toBe('true')
  })

  it('en escritorio la lista de pestañas es vertical', () => {
    desktopRef.value = true
    const w = montar()
    expect(w.find('[role="tablist"]').attributes('aria-orientation')).toBe('vertical')
  })

  it('no se rompe si localStorage tira error', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('x') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('x') })
    const w = montar()
    expect(tabs(w)[0].attributes('aria-selected')).toBe('true')
    await tabs(w)[1].trigger('click')
    expect(tabs(w)[1].attributes('aria-selected')).toBe('true')
  })
})

describe('pestaña Atajos', () => {
  async function abrirAtajos(w: ReturnType<typeof montar>) {
    const t = tabs(w).find((x) => x.text().includes('Atajos'))!
    await t.trigger('click')
  }

  it('lista los atajos con Ctrl+K como kbd, después de Avisos', async () => {
    const w = montar()
    const nombres = tabs(w).map((t) => t.text())
    expect(nombres.indexOf('Atajos')).toBe(nombres.indexOf('Avisos') + 1)
    await abrirAtajos(w)
    const kbds = w.findAll('kbd').map((k) => k.text())
    expect(kbds).toContain('Ctrl')
    expect(kbds).toContain('K')
    expect(w.text()).toContain('Abrir el buscador')
    expect(w.text()).toContain('Los atajos son para teclado')
  })

  it('en Mac muestra ⌘ en vez de Ctrl en los atajos que lo aceptan', async () => {
    const orig = Object.getOwnPropertyDescriptor(Navigator.prototype, 'platform')!
    Object.defineProperty(Navigator.prototype, 'platform', { configurable: true, get: () => 'MacIntel' })
    try {
      const w = montar()
      await abrirAtajos(w)
      expect(w.findAll('kbd').map((k) => k.text())).toContain('⌘')
      const fila = w.findAll('.atajo').find((f) => f.text().includes('Abrir el buscador'))!
      expect(fila.text()).not.toContain('Ctrl')
    } finally {
      Object.defineProperty(Navigator.prototype, 'platform', orig)
    }
  })
})

describe('Atajos que se pueden cambiar', () => {
  const tecla = (init: KeyboardEventInit) => window.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...init }))
  const montadas: ReturnType<typeof montar>[] = []
  afterEach(() => montadas.splice(0).forEach((m) => m.unmount()))
  async function abrir() {
    const w = montar()
    montadas.push(w)
    await tabs(w).find((x) => x.text().includes('Atajos'))!.trigger('click')
    return w
  }
  const fila = (w: Awaited<ReturnType<typeof abrir>>, que: string) => w.findAll('.atajo').find((f) => f.text().includes(que))!

  it('las filas editables tienen Cambiar y las fijas no', async () => {
    const w = await abrir()
    expect(w.findAll('button').filter((b) => b.text() === 'Cambiar')).toHaveLength(5)
    expect(fila(w, 'Abrir el buscador').find('button').text()).toBe('Cambiar')
    expect(fila(w, 'Mandar el mensaje').find('button').exists()).toBe(false)
    expect(w.text()).not.toContain('Volver al original')
  })

  it('cambiar el buscador: captura la combinación, la guarda y la muestra', async () => {
    const w = await abrir()
    await fila(w, 'Abrir el buscador').find('button').trigger('click')
    expect(w.text()).toContain('Apretá la combinación nueva')
    tecla({ key: 'j', ctrlKey: true })
    await new Promise((r) => setTimeout(r))
    expect(setAtajos).toHaveBeenCalledWith({ buscador: 'mod+j' })
    expect(w.text()).not.toContain('Apretá la combinación nueva')
    expect(fila(w, 'Abrir el buscador').findAll('kbd').map((k) => k.text())).toEqual(['Ctrl', 'J'])
    expect(fila(w, 'Abrir el buscador').text()).toContain('Volver al original')
  })

  it('muestra el error en línea y sigue esperando', async () => {
    const w = await abrir()
    await fila(w, 'Abrir el buscador').find('button').trigger('click')
    tecla({ key: 't', ctrlKey: true })
    await w.vm.$nextTick()
    expect(w.text()).toContain('El navegador usa Ctrl+T para abrir una pestaña')
    tecla({ key: ' ', code: 'Space', ctrlKey: true, shiftKey: true })
    await w.vm.$nextTick()
    expect(w.text()).toContain('Ya la usa «Dictar por voz»')
    tecla({ key: 'k' })
    await w.vm.$nextTick()
    expect(w.text()).toContain('Necesita Ctrl, Alt o Shift')
    expect(setAtajos).not.toHaveBeenCalled()
  })

  it('Esc cancela la captura sin cambiar nada', async () => {
    const w = await abrir()
    await fila(w, 'Abrir el buscador').find('button').trigger('click')
    expect(capturandoAtajo.value).toBe(true)
    tecla({ key: 'Escape' })
    await w.vm.$nextTick()
    expect(capturandoAtajo.value).toBe(false)
    expect(w.text()).not.toContain('Apretá la combinación nueva')
    expect(setAtajos).not.toHaveBeenCalled()
  })

  it('Volver al original borra el cambio', async () => {
    atajosGuardados.value = { dictar: 'mod+alt+d' }
    const w = await abrir()
    const f = fila(w, 'Dictar por voz')
    expect(f.findAll('kbd').map((k) => k.text())).toEqual(['Ctrl', 'Alt', 'D'])
    await f.findAll('button').find((b) => b.text() === 'Volver al original')!.trigger('click')
    await new Promise((r) => setTimeout(r))
    expect(setAtajos).toHaveBeenCalledWith({})
    expect(fila(w, 'Dictar por voz').findAll('kbd').map((k) => k.text())).toEqual(['Ctrl', 'Shift', 'Espacio'])
  })

  it('la fila de Windows manda al ícono de Colmena junto al reloj', async () => {
    const w = await abrir()
    expect(w.text()).toContain('Atajos → Cambiar atajos…')
    expect(w.text()).not.toContain('Ctrl+Alt+N')
  })
})
