// @vitest-environment jsdom
import { createApp, h, nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getTerminalesCarpetas: vi.fn(),
  postTerminalesNueva: vi.fn(),
  postTerminalesNuevaTarea: vi.fn(),
}))
vi.mock('../state/app', () => api)
vi.mock('../motion', () => ({ gsap: { fromTo: (_e: unknown, _a: unknown, v: { onComplete?: () => void }) => v.onComplete?.(), to: (_e: unknown, v: { onComplete?: () => void }) => v.onComplete?.(), set: () => {} }, haptic: vi.fn(), isSoft: () => true, useGsap: () => ({ run: (fn: () => void) => fn() }) }))
vi.mock('./Icon.vue', () => ({ default: { name: 'Icon', render: () => null } }))

const { default: Sheet } = await import('./NuevaTerminalSheet.vue')
const { default: fuente } = await import('./NuevaTerminalSheet.vue?raw')

const CARPETAS = [
  { ruta: '~/Proyectos/orq', nombre: 'orq', repo: true },
  { ruta: '~/Proyectos/acmekit', nombre: 'acmekit', repo: true },
  { ruta: '~/Documents', nombre: 'Documents', repo: false },
]

const tick = async () => {
  for (let i = 0; i < 5; i++) await nextTick()
  await Promise.resolve()
  await nextTick()
}
const q = <T extends Element>(sel: string) => document.body.querySelector<T>(sel)
const botonAbrir = () => q<HTMLButtonElement>('button[type="submit"]')!

let app: ReturnType<typeof createApp>
const abierta = ref(false)

const grupoInicial = ref<string | undefined>(undefined)

async function montar() {
  app = createApp({ render: () => h(Sheet, { open: abierta.value, grupoInicial: grupoInicial.value }) })
  app.mount(document.createElement('div'))
  abierta.value = true
  await tick()
}

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
  api.getTerminalesCarpetas.mockResolvedValue({ carpetas: CARPETAS, grupos: [] })
  api.postTerminalesNuevaTarea.mockResolvedValue({ ok: true, pane_id: 'g1:p1', ruta: '/r', rama: 'feature/x' })
})
afterEach(() => {
  grupoInicial.value = undefined
  abierta.value = false
  app.unmount()
  document.body.innerHTML = ''
})

describe('NuevaTerminalSheet: nueva tarea', () => {
  it('abre en el último modo y con el último repo usado, solo entre repos', async () => {
    localStorage.setItem('orq.nuevaModo', 'tarea')
    localStorage.setItem('orq.nuevaRepo', '~/Proyectos/acmekit')
    await montar()
    expect(q('textarea.tarea')).not.toBeNull()
    const filas = [...document.body.querySelectorAll('.carp')]
    expect(filas.map((f) => f.querySelector('.nom')?.textContent)).toEqual(['orq', 'acmekit'])
    expect(filas.find((f) => f.getAttribute('aria-pressed') === 'true')?.querySelector('.nom')?.textContent).toBe('acmekit')
  })

  it('no deja abrir sin tarea', async () => {
    localStorage.setItem('orq.nuevaModo', 'tarea')
    await montar()
    expect(botonAbrir().disabled).toBe(true)
  })

  it('Ctrl+Enter envía solo repo y tarea, y recuerda el repo', async () => {
    localStorage.setItem('orq.nuevaModo', 'tarea')
    await montar()
    const ta = q<HTMLTextAreaElement>('textarea.tarea')!
    ta.value = '  Arreglar el login  '
    ta.dispatchEvent(new Event('input'))
    await tick()
    ta.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', ctrlKey: true, bubbles: true }))
    await tick()
    expect(api.postTerminalesNuevaTarea).toHaveBeenCalledTimes(1)
    const body = api.postTerminalesNuevaTarea.mock.calls[0][0]
    expect(body).toMatchObject({ repo: '~/Proyectos/orq', tarea: 'Arreglar el login' })
    expect(body.nombre).toBeUndefined()
    expect(body.rama).toBeUndefined()
    expect(localStorage.getItem('orq.nuevaRepo')).toBe('~/Proyectos/orq')
  })

  it('Enter solo no envía', async () => {
    localStorage.setItem('orq.nuevaModo', 'tarea')
    await montar()
    const ta = q<HTMLTextAreaElement>('textarea.tarea')!
    ta.value = 'algo'
    ta.dispatchEvent(new Event('input'))
    await tick()
    ta.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    await tick()
    expect(api.postTerminalesNuevaTarea).not.toHaveBeenCalled()
  })

  it('cambiar de modo se recuerda', async () => {
    await montar()
    expect(q('textarea.tarea')).toBeNull()
    const btn = [...document.body.querySelectorAll('.modo button')].find((b) => b.textContent === 'Nueva tarea') as HTMLButtonElement
    btn.click()
    await tick()
    expect(q('textarea.tarea')).not.toBeNull()
    expect(localStorage.getItem('orq.nuevaModo')).toBe('tarea')
  })

  it('en modo terminal sigue mostrando las carpetas de siempre', async () => {
    await montar()
    expect(document.body.querySelectorAll('.carp')).toHaveLength(3)
  })
})

describe('NuevaTerminalSheet: ticket de Jira', () => {
  async function escribir(sel: string, valor: string) {
    const el = q<HTMLInputElement | HTMLTextAreaElement>(sel)!
    el.value = valor
    el.dispatchEvent(new Event('input'))
    await tick()
  }

  it('con ticket válido y sin nota se habilita, pasa a mayúsculas y manda ticket sin rama', async () => {
    localStorage.setItem('orq.nuevaModo', 'tarea')
    await montar()
    expect(botonAbrir().disabled).toBe(true)
    await escribir('input.ticket', 'abc-123')
    expect(q<HTMLInputElement>('input.ticket')!.value).toBe('ABC-123')
    expect(botonAbrir().disabled).toBe(false)
    expect(q<HTMLTextAreaElement>('textarea.tarea')!.placeholder).toContain('Nota para Claude')
    expect(document.body.textContent).toContain('el flujo de tickets del kit de trabajo')
    botonAbrir().click()
    await tick()
    const body = api.postTerminalesNuevaTarea.mock.calls[0][0]
    expect(body).toMatchObject({ repo: '~/Proyectos/orq', tarea: '', ticket: 'ABC-123' })
    expect(body.rama).toBeUndefined()
  })

  it('el campo Rama muestra feature/<CLAVE> y queda deshabilitado', async () => {
    localStorage.setItem('orq.nuevaModo', 'tarea')
    await montar()
    await escribir('input.ticket', 'ABC-123')
    const rama = q<HTMLInputElement>('input.rama')!
    expect(rama.value).toBe('feature/ABC-123')
    expect(rama.disabled).toBe(true)
  })

  it('un ticket mal formado muestra el error y no deja abrir', async () => {
    localStorage.setItem('orq.nuevaModo', 'tarea')
    await montar()
    await escribir('input.ticket', 'SITE-0')
    expect(q('.warn')?.textContent).toContain('ABC-123')
    expect(botonAbrir().disabled).toBe(true)
  })

  it('el campo evita el zoom de iOS con 16px', () => {
    expect(fuente).toMatch(/input\.ticket[^}]*font-size: 16px/)
  })
})

describe('NuevaTerminalSheet: sumar pestaña a un grupo', () => {
  const GRUPOS = [
    { id: 'g1', nombre: 'Uno', carpeta: '~/Proyectos/orq' },
    { id: 'g2', nombre: 'Dos', carpeta: null },
  ]

  it('precarga el grupo y su carpeta, y abre sin tocar nada más', async () => {
    api.getTerminalesCarpetas.mockResolvedValue({ carpetas: CARPETAS, grupos: GRUPOS })
    api.postTerminalesNueva.mockResolvedValue({ ok: true, espacio_id: 'g1', sesion_id: 'g1:p2' })
    grupoInicial.value = 'g1'
    await montar()
    expect(q<HTMLSelectElement>('select.sel')!.value).toBe('g1')
    expect(q('.carp[aria-pressed="true"] .nom')?.textContent).toBe('orq')
    expect(q('details.mas[open]')).toBeNull()
    expect(botonAbrir().disabled).toBe(false)
    botonAbrir().click()
    await tick()
    expect(api.postTerminalesNueva.mock.calls[0][0]).toMatchObject({ carpeta: '~/Proyectos/orq', grupo: 'g1' })
  })

  it('aunque el último modo haya sido tarea, abre en terminal', async () => {
    localStorage.setItem('orq.nuevaModo', 'tarea')
    api.getTerminalesCarpetas.mockResolvedValue({ carpetas: CARPETAS, grupos: GRUPOS })
    grupoInicial.value = 'g1'
    await montar()
    expect(q('textarea.tarea')).toBeNull()
    expect(q<HTMLSelectElement>('select.sel')!.value).toBe('g1')
  })

  it('un grupo que ya no existe se ignora', async () => {
    api.getTerminalesCarpetas.mockResolvedValue({ carpetas: CARPETAS, grupos: GRUPOS })
    grupoInicial.value = 'g9'
    await montar()
    expect(q<HTMLSelectElement>('select.sel')!.value).toBe('')
  })
})
