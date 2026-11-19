// @vitest-environment jsdom
import { createApp, h, nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { EVENTO_CURSOR } from '../lib/tareas'
import type { CursorApi, TrabajadorCursor } from '../api/cursorApi'
import { ApiError } from '../api/types'

vi.mock('./Icon.vue', () => ({ default: { name: 'Icon', render: () => null } }))

const { default: TrabajadoresCursor } = await import('./TrabajadoresCursor.vue')

const t = (over: Partial<TrabajadorCursor> = {}): TrabajadorCursor => ({
  id: 'a'.repeat(32), nombre: 'Renombrar helpers', estado: 'corriendo', ruta: '/home/u/repo-cursor-x', rama: 'cursor/renombrar-ab12',
  base: '0'.repeat(40), inicio: 1000, fin: null, codigo: null, archivos: [], resumen: '', pedido: 'Renombrá foo',
  origen: { tipo: 'claude', nombre: 'PS9 plugins' }, log_recortado: false, ...over,
})

function falsa(lista: TrabajadorCursor[], extra: Partial<CursorApi> = {}): CursorApi {
  return {
    getCursorEstado: vi.fn(async () => ({ disponible: true, corriendo: 1, max_simultaneos: 2 })),
    getTrabajadores: vi.fn(async () => lista),
    getLog: vi.fn(async () => '{"type":"assistant"}\nlínea final'),
    postCancelar: vi.fn(async () => {}),
    ...extra,
  }
}

const flush = async () => {
  for (let i = 0; i < 5; i++) await Promise.resolve()
  await nextTick()
}

let app: ReturnType<typeof createApp> | null = null
let el: HTMLElement
function montar(api: CursorApi, ahora = 1000 + 125) {
  el = document.createElement('div')
  document.body.appendChild(el)
  app = createApp({ render: () => h(TrabajadoresCursor, { api, ahora: () => ahora }) })
  app.mount(el)
}
afterEach(() => {
  app?.unmount()
  el?.remove()
  app = null
})

const boton = (texto: string) => [...el.querySelectorAll('button')].find((b) => b.textContent?.trim() === texto)

describe('TrabajadoresCursor', () => {
  it('carga al montar y muestra nombre, estado, duración, rama, archivos y quién lo pidió', async () => {
    const api = falsa([t(), t({ id: 'b'.repeat(32), nombre: 'Traducir', estado: 'ok', fin: 1000 + 600, codigo: 0, archivos: ['a.py', 'b.py'] })])
    montar(api)
    await flush()
    expect(api.getTrabajadores).toHaveBeenCalledTimes(1)
    const txt = el.textContent ?? ''
    expect(txt).toContain('Renombrar helpers')
    expect(txt).toContain('Trabajando')
    expect(txt).toContain('2 min')
    expect(txt).toContain('cursor/renombrar-ab12')
    expect(txt).toContain('PS9 plugins')
    expect(txt).toContain('Terminó')
    expect(txt).toContain('10 min')
    expect(txt).toContain('2 archivos')
    expect(txt).toContain('1 de 2 trabajando')
  })

  it('Cancelar solo aparece en el que corre y llama al api', async () => {
    const api = falsa([t(), t({ id: 'b'.repeat(32), estado: 'error', fin: 1100 })])
    montar(api)
    await flush()
    const cancelar = [...el.querySelectorAll('button')].filter((b) => b.textContent?.trim() === 'Cancelar')
    expect(cancelar.length).toBe(1)
    cancelar[0].click()
    await flush()
    expect(api.postCancelar).toHaveBeenCalledWith('a'.repeat(32))
    expect(api.getTrabajadores).toHaveBeenCalledTimes(2)
  })

  it('Ver log trae el final del log y lo muestra como texto', async () => {
    const api = falsa([t({ estado: 'ok', fin: 1100 })])
    montar(api)
    await flush()
    boton('Ver log')!.click()
    await flush()
    expect(api.getLog).toHaveBeenCalledWith('a'.repeat(32))
    expect(el.querySelector('pre.log')?.textContent).toContain('línea final')
    expect(boton('Ocultar log')).toBeTruthy()
  })

  it('Actualizar vuelve a pedir la lista; sin trabajadores dice que no hay', async () => {
    const api = falsa([])
    montar(api)
    await flush()
    expect(el.textContent).toContain('No hay trabajadores Cursor')
    boton('Actualizar')!.click()
    await flush()
    expect(api.getTrabajadores).toHaveBeenCalledTimes(2)
  })

  it('un error de la API se muestra sin romper', async () => {
    const api = falsa([], { getTrabajadores: vi.fn(async () => { throw new ApiError(500, 'Se rompió') }) })
    montar(api)
    await flush()
    expect(el.querySelector('[role="alert"]')?.textContent).toContain('Se rompió')
  })

  it('sin la prop ahora, un trabajador corriendo muestra una duración real (no NaN)', async () => {
    const api = falsa([t({ inicio: Math.floor(Date.now() / 1000) - 90, fin: null })])
    el = document.createElement('div')
    document.body.appendChild(el)
    app = createApp({ render: () => h(TrabajadoresCursor, { api }) })
    app.mount(el)
    await flush()
    expect(el.textContent).not.toContain('NaN')
    expect(el.querySelector('.tc-dur')?.textContent).toMatch(/\d/)
  })

  it('no pone su propio título: lo pone el contenedor', async () => {
    montar(falsa([t()]))
    await flush()
    expect(el.textContent).not.toMatch(/Trabajadores (de )?Cursor/)
  })

  it('recarga cuando llega el evento de cursor y deja de escuchar al desmontar', async () => {
    const api = falsa([t()])
    montar(api)
    await flush()
    window.dispatchEvent(new Event(EVENTO_CURSOR))
    await flush()
    expect(api.getTrabajadores).toHaveBeenCalledTimes(2)
    app!.unmount()
    app = null
    window.dispatchEvent(new Event(EVENTO_CURSOR))
    await flush()
    expect(api.getTrabajadores).toHaveBeenCalledTimes(2)
  })

  it('el resumen de Cursor se muestra como texto, sin interpretar HTML', async () => {
    const api = falsa([t({ estado: 'ok', fin: 1100, resumen: '<img src=x onerror=alert(1)>Listo' })])
    montar(api)
    await flush()
    expect(el.querySelector('img')).toBeNull()
    expect(el.textContent).toContain('<img src=x onerror=alert(1)>Listo')
  })
})
