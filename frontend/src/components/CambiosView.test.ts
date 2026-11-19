// @vitest-environment jsdom
import { h } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import type { Cambios } from '../api/cambiosApi'

const { cambios, cargarCambios, irAMr, mrDeSesion } = await vi.hoisted(async () => {
  const { reactive: rx } = await import('vue')
  const { vi: v } = await import('vitest')
  return {
    cambios: rx({ sid: '', data: null as unknown, loading: false, error: '' }),
    cargarCambios: v.fn(),
    irAMr: v.fn(),
    mrDeSesion: v.fn(() => null as unknown),
  }
})

vi.mock('../state/cambios', () => ({ cambios, cargarCambios: (...a: unknown[]) => (cargarCambios as (...x: unknown[]) => void)(...a) }))
vi.mock('../state/mrs', () => ({ irAMr: (...a: unknown[]) => (irAMr as (...x: unknown[]) => void)(...a), mrDeSesion: (...a: unknown[]) => (mrDeSesion as (...x: unknown[]) => unknown)(...a) }))
vi.mock('../lib/useSheetSwipe', () => ({ useSheetSwipe: () => {} }))
vi.mock('./Icon.vue', () => ({ default: { props: ['name'], render() { return h('i', { class: 'icon', 'data-name': (this as any).name }) } } }))

import CambiosView from './CambiosView.vue'
import formSrc from './DiffComentarioForm.vue?raw'
import sheetSrc from './DiffComentarioSheet.vue?raw'
import viewSrc from './CambiosView.vue?raw'
import { diffComentarios, pendientes, setComentariosApi } from '../state/diffComentarios'

const base = (): Cambios => ({
  repo: true, rama: 'feature/x', base: 'main', sin_guardar: 1, truncado: false, commits_total: 2,
  commits: [{ sha: 'abc1234', titulo: 'feat: uno' }, { sha: 'def5678', titulo: 'fix: dos' }],
  archivos: [
    { path: 'src/a.ts', estado: 'M', adds: 2, dels: 1, binario: false, truncado: false, diff: '@@ -1,2 +1,3 @@\n ctx\n-viejo\n+nuevo\n+otro' },
    { path: 'b.png', estado: 'A', adds: 0, dels: 0, binario: true, truncado: false, diff: '' },
    { path: 'c.txt', estado: 'D', adds: 0, dels: 4, binario: false, truncado: true, diff: '@@ -1,1 +0,0 @@\n-x' },
  ],
})

function montar(desktop: boolean, data: unknown = base()) {
  cambios.sid = 's1'
  cambios.data = data
  return mount(CambiosView, { props: { sid: 's1', desktop }, attachTo: document.body })
}

beforeEach(() => {
  document.body.innerHTML = ''
  localStorage.clear()
  diffComentarios.porSesion = {}
  diffComentarios.estado = {}
  cargarCambios.mockReset()
  irAMr.mockReset()
  mrDeSesion.mockReset().mockReturnValue(null)
  cambios.data = null
  cambios.error = ''
  cambios.loading = false
})

describe('CambiosView estados', () => {
  it('no es un repo', () => {
    const w = montar(true, { ...base(), repo: false, archivos: [] })
    expect(w.text()).toContain('No es un repo git')
  })

  it('sin cambios respecto de la base', () => {
    const w = montar(true, { ...base(), archivos: [], commits: [], commits_total: 0, sin_guardar: 0 })
    expect(w.text()).toContain('Sin cambios respecto de main')
  })

  it('error', () => {
    cambios.error = 'La carpeta de la sesión no está entre las permitidas'
    const w = montar(true, null)
    expect(w.text()).toContain('La carpeta de la sesión no está entre las permitidas')
  })

  it('pide los cambios al abrir', () => {
    montar(true)
    expect(cargarCambios).toHaveBeenCalledWith('s1')
  })
})

describe('CambiosView encabezado', () => {
  it('rama, base, commits expandibles y sin guardar', async () => {
    const w = montar(true)
    expect(w.text()).toContain('feature/x')
    expect(w.text()).toContain('main')
    expect(w.text()).toContain('sin guardar: 1 archivo')
    expect(w.text()).not.toContain('feat: uno')
    await w.get('[data-test="commits"]').trigger('click')
    expect(w.text()).toContain('feat: uno')
    expect(w.text()).toContain('abc1234')
  })

  it('Actualizar refresca', async () => {
    const w = montar(true)
    cargarCambios.mockClear()
    await w.get('[data-test="actualizar"]').trigger('click')
    expect(cargarCambios).toHaveBeenCalledWith('s1', true)
  })

  it('Ver MR solo si la sesión tiene uno', async () => {
    expect(montar(true).find('[data-test="ver-mr"]').exists()).toBe(false)
    mrDeSesion.mockReturnValue({ ref: '1:2' })
    const w = montar(true)
    await w.get('[data-test="ver-mr"]').trigger('click')
    expect(irAMr).toHaveBeenCalledWith('1:2')
  })
})

describe('CambiosView en pantalla ancha', () => {
  it('lista los archivos con +/− y muestra el diff del primero con números de línea', () => {
    const w = montar(true)
    const items = w.findAll('[data-test="archivo"]')
    expect(items).toHaveLength(3)
    expect(items[0].text()).toContain('src/a.ts')
    expect(items[0].text()).toContain('+2')
    expect(items[0].text()).toContain('−1')
    const lineas = w.findAll('[data-test="linea"]')
    expect(lineas.map((l) => l.classes())).toContainEqual(expect.arrayContaining(['add']))
    expect(lineas.map((l) => l.classes())).toContainEqual(expect.arrayContaining(['del']))
    expect(w.get('[data-test="diff"]').text()).toContain('nuevo')
    expect(w.findAll('[data-test="num-b"]').map((n) => n.text())).toEqual(expect.arrayContaining(['2', '3']))
  })

  it('j y k cambian de archivo', async () => {
    const w = montar(true)
    await w.get('.cambios').trigger('keydown', { key: 'j' })
    expect(w.get('[data-test="archivo"][aria-current="true"]').text()).toContain('b.png')
    expect(w.text()).toContain('Binario')
    await w.get('.cambios').trigger('keydown', { key: 'j' })
    expect(w.get('[data-test="diff"]').text()).toContain('recortado')
    await w.get('.cambios').trigger('keydown', { key: 'k' })
    await w.get('.cambios').trigger('keydown', { key: 'k' })
    expect(w.get('[data-test="archivo"][aria-current="true"]').text()).toContain('src/a.ts')
  })
})

describe('CambiosView en celu', () => {
  it('muestra la lista y el diff recién al tocar un archivo; Volver regresa a la lista', async () => {
    const w = montar(false)
    expect(w.find('[data-test="diff"]').exists()).toBe(false)
    await w.findAll('[data-test="archivo"]')[0].trigger('click')
    expect(w.get('[data-test="diff"]').text()).toContain('nuevo')
    expect(w.findAll('[data-test="archivo"]')).toHaveLength(0)
    await w.get('[data-test="volver-lista"]').trigger('click')
    expect(w.find('[data-test="diff"]').exists()).toBe(false)
    expect(w.findAll('[data-test="archivo"]')).toHaveLength(3)
  })
})

const marcar = (w: ReturnType<typeof montar>, i: number) => w.findAll('[data-test="marcar"]')[i].trigger('click')
// líneas elegibles del diff de a.ts: 0 ctx(b1) · 1 del(a2) · 2 add(b2) · 3 add(b3)

describe('CambiosView comentarios en pantalla ancha', () => {
  it('el encabezado del hunk no se puede marcar', () => {
    const w = montar(true)
    expect(w.findAll('[data-test="linea"]')).toHaveLength(5)
    expect(w.findAll('[data-test="marcar"]')).toHaveLength(4)
  })

  it('tocar el número marca, otro toque extiende y aparece "Comentar"', async () => {
    const w = montar(true)
    expect(w.find('[data-test="barra-comentar"]').exists()).toBe(false)
    await marcar(w, 2)
    expect(w.get('[data-test="barra-comentar"]').text()).toContain('Comentar L2')
    expect(w.findAll('[data-test="linea"]').filter((l) => l.attributes('aria-selected') === 'true')).toHaveLength(1)
    await marcar(w, 3)
    expect(w.get('[data-test="barra-comentar"]').text()).toContain('Comentar L2-3')
    await w.get('[data-test="limpiar-seleccion"]').trigger('click')
    expect(w.find('[data-test="barra-comentar"]').exists()).toBe(false)
  })

  it('en escritorio un clic en el texto de la línea también marca', async () => {
    const w = montar(true)
    await w.findAll('[data-test="linea"]')[3].get('.txt').trigger('click')
    expect(w.get('[data-test="barra-comentar"]').text()).toContain('Comentar L2')
  })

  it('el formulario va debajo de la línea, agrega y suma al contador de "Mandar a la sesión"', async () => {
    const w = montar(true)
    expect(w.find('[data-test="mandar"]').exists()).toBe(false)
    await marcar(w, 2)
    await marcar(w, 3)
    await w.get('[data-test="comentar"]').trigger('click')
    expect(w.get('[data-test="comentario-form"]').text()).toContain('L2-3')
    const ta = w.get('[data-test="comentario-texto"]')
    await ta.setValue('renombrá esto')
    await w.get('[data-test="comentario-agregar"]').trigger('click')
    expect(w.find('[data-test="comentario-form"]').exists()).toBe(false)
    expect(pendientes('s1')).toMatchObject([{ path: 'src/a.ts', lado: 'nuevo', desde: 2, hasta: 3, fragmento: 'nuevo\notro', texto: 'renombrá esto' }])
    expect(w.get('[data-test="mandar"]').text()).toContain('Mandar a la sesión (1)')
    expect(w.findAll('[data-test="linea"]').some((l) => l.classes().includes('comentada'))).toBe(true)
    expect(w.find('[data-test="barra-comentar"]').exists()).toBe(false)
  })

  it('Agregar está deshabilitado sin texto; Ctrl+Enter agrega y Esc cancela', async () => {
    const w = montar(true)
    await marcar(w, 2)
    await w.get('[data-test="comentar"]').trigger('click')
    expect(w.get('[data-test="comentario-agregar"]').attributes('disabled')).toBeDefined()
    await w.get('[data-test="comentario-texto"]').setValue('hola')
    await w.get('[data-test="comentario-texto"]').trigger('keydown', { key: 'Enter', ctrlKey: true })
    expect(pendientes('s1')).toHaveLength(1)
    await marcar(w, 3)
    await w.get('[data-test="comentar"]').trigger('click')
    await w.get('[data-test="comentario-texto"]').trigger('keydown', { key: 'Escape' })
    expect(w.find('[data-test="comentario-form"]').exists()).toBe(false)
    expect(pendientes('s1')).toHaveLength(1)
  })

  it('Mandar a la sesión llama a la API con el body esperado, vacía la lista y avisa', async () => {
    const api = vi.fn().mockResolvedValue({ ok: true, enviados: 1 })
    setComentariosApi(api)
    const w = montar(true)
    await marcar(w, 2)
    await w.get('[data-test="comentar"]').trigger('click')
    await w.get('[data-test="comentario-texto"]').setValue('mejor otro nombre')
    await w.get('[data-test="comentario-agregar"]').trigger('click')
    await w.get('[data-test="mandar"]').trigger('click')
    await vi.waitFor(() => expect(api).toHaveBeenCalledTimes(1))
    expect(api.mock.calls[0][0]).toBe('s1')
    expect(api.mock.calls[0][1].comentarios).toEqual([
      { path: 'src/a.ts', lado: 'nuevo', desde: 2, hasta: 2, fragmento: 'nuevo', texto: 'mejor otro nombre' },
    ])
    await vi.waitFor(() => expect(w.text()).toContain('Comentarios mandados'))
    expect(w.find('[data-test="mandar"]').exists()).toBe(false)
  })

  it('si el servidor rechaza, muestra el detalle y deja la lista intacta', async () => {
    const { ApiError } = await import('../api/types')
    setComentariosApi(vi.fn().mockRejectedValue(new ApiError(409, 'Ese archivo ya no está entre los cambios: tocá Actualizar')))
    const w = montar(true)
    await marcar(w, 2)
    await w.get('[data-test="comentar"]').trigger('click')
    await w.get('[data-test="comentario-texto"]').setValue('x')
    await w.get('[data-test="comentario-agregar"]').trigger('click')
    await w.get('[data-test="mandar"]').trigger('click')
    await vi.waitFor(() => expect(w.text()).toContain('tocá Actualizar'))
    expect(pendientes('s1')).toHaveLength(1)
  })

  it('"Mandar" se deshabilita antes de pasar los 4000 caracteres', async () => {
    const w = montar(true)
    for (let i = 0; i < 5; i++) {
      await marcar(w, 2)
      await w.get('[data-test="comentar"]').trigger('click')
      await w.get('[data-test="comentario-texto"]').setValue('z'.repeat(1000))
      await w.get('[data-test="comentario-agregar"]').trigger('click')
    }
    expect(pendientes('s1')).toHaveLength(5)
    expect(w.get('[data-test="mandar"]').attributes('disabled')).toBeDefined()
    expect(w.text()).toContain('mandá menos comentarios')
  })

  it('"Ver comentarios" lista, edita y borra antes de mandar', async () => {
    const w = montar(true)
    await marcar(w, 2)
    await w.get('[data-test="comentar"]').trigger('click')
    await w.get('[data-test="comentario-texto"]').setValue('uno')
    await w.get('[data-test="comentario-agregar"]').trigger('click')
    await w.get('[data-test="ver-comentarios"]').trigger('click')
    await nextTick()
    const lista = document.body.querySelector('[data-test="comentarios-lista"]') as HTMLElement
    expect(lista.textContent).toContain('src/a.ts')
    expect(lista.textContent).toContain('uno')
    ;(document.body.querySelector('[data-test="comentario-quitar"]') as HTMLElement).click()
    await nextTick()
    expect(pendientes('s1')).toHaveLength(0)
  })

  it('los comentarios de otro archivo no marcan líneas de este', async () => {
    diffComentarios.porSesion = { s1: [{ id: 'c1', path: 'otro.ts', lado: 'nuevo', desde: 2, hasta: 2, fragmento: '', texto: 'x' }] }
    const w = montar(true)
    expect(w.findAll('[data-test="linea"]').some((l) => l.classes().includes('comentada'))).toBe(false)
    expect(w.get('[data-test="mandar"]').text()).toContain('(1)')
  })
})

describe('CambiosView comentarios en celu', () => {
  it('el formulario sale como hoja inferior con el fragmento, y el botón Mandar está en la barra del visor', async () => {
    const w = montar(false)
    await w.findAll('[data-test="archivo"]')[0].trigger('click')
    expect(w.find('[data-test="comentario-form"]').exists()).toBe(false)
    await marcar(w, 2)
    await w.get('[data-test="comentar"]').trigger('click')
    await nextTick()
    const hoja = document.body.querySelector('[data-test="comentario-sheet"]') as HTMLElement
    expect(hoja).not.toBeNull()
    expect(hoja.textContent).toContain('nuevo')
    const ta = hoja.querySelector('[data-test="comentario-texto"]') as HTMLTextAreaElement
    ta.value = 'desde el celu'
    ta.dispatchEvent(new Event('input'))
    await nextTick()
    ;(hoja.querySelector('[data-test="comentario-agregar"]') as HTMLElement).click()
    await nextTick()
    expect(pendientes('s1')[0].texto).toBe('desde el celu')
    expect(w.get('.vh [data-test="mandar"]').text()).toContain('(1)')
  })
})

const regla = (src: string, sel: string) => new RegExp(`${sel.replace('.', '\\.')}\\s*\\{([^}]*)\\}`).exec(src)?.[1] ?? ''

describe('CambiosView comentarios: detalles de CSS que no se ven en jsdom', () => {
  it('el textarea del formulario tiene font-size 16px (evita el zoom de iOS)', () => {
    expect(regla(formSrc, '.texto')).toMatch(/font-size:\s*16px/)
  })
  it('la columna de números queda pegada a la izquierda dentro del scroll horizontal', () => {
    const r = regla(viewSrc, '.gut')
    expect(r).toMatch(/position:\s*sticky/)
    expect(r).toMatch(/left:\s*0/)
  })
  it('la marca de comentario y el borde de la selección se ven sobre el número de línea opaco', () => {
    expect(regla(viewSrc, '.ln.comentada .gut')).toMatch(/box-shadow:\s*inset 3px 0 0/)
    expect(regla(viewSrc, '.ln.sel .gut')).toMatch(/box-shadow:\s*inset/)
  })
  it('la hoja tiene scroll interno y se acota a lo visible cuando el teclado la achica', () => {
    const r = regla(sheetSrc, '.dcs')
    expect(r).toMatch(/overflow-y:\s*auto/)
    expect(r).toMatch(/overscroll-behavior:\s*contain/)
    expect(r).toMatch(/max-height:[^;]*100%/)
  })
})

describe('CambiosView comentarios: un solo botón Mandar por pantalla en celu', () => {
  it('en la lista y en el visor hay exactamente uno', async () => {
    diffComentarios.porSesion = { s1: [{ id: 'c1', path: 'src/a.ts', lado: 'nuevo', desde: 2, hasta: 2, fragmento: '', texto: 'x' }] }
    const w = montar(false)
    expect(w.findAll('[data-test="mandar"]')).toHaveLength(1)
    expect(w.findAll('[data-test="ver-comentarios"]')).toHaveLength(1)
    await w.findAll('[data-test="archivo"]')[0].trigger('click')
    expect(w.findAll('[data-test="mandar"]')).toHaveLength(1)
    expect(w.findAll('[data-test="ver-comentarios"]')).toHaveLength(1)
  })
})

describe('CambiosView comentarios: Actualizar con el diff cambiado', () => {
  const cambiado = () => {
    const d = base()
    d.archivos[0].diff = '@@ -1,2 +1,2 @@\n ctx\n+distinto'
    return d
  }

  it('limpia la selección', async () => {
    const w = montar(true)
    await marcar(w, 2)
    expect(w.find('[data-test="barra-comentar"]').exists()).toBe(true)
    cambios.data = cambiado()
    await nextTick()
    expect(w.find('[data-test="barra-comentar"]').exists()).toBe(false)
    expect(w.findAll('[data-test="linea"]').some((l) => l.attributes('aria-selected') === 'true')).toBe(false)
  })

  it('con el formulario abierto conserva el texto escrito', async () => {
    const w = montar(true)
    await marcar(w, 2)
    await w.get('[data-test="comentar"]').trigger('click')
    await w.get('[data-test="comentario-texto"]').setValue('no lo pierdas')
    cambios.data = cambiado()
    await nextTick()
    expect((w.get('[data-test="comentario-texto"]').element as HTMLTextAreaElement).value).toBe('no lo pierdas')
    expect(w.findAll('[data-test="linea"]').some((l) => l.attributes('aria-selected') === 'true')).toBe(false)
  })
})
