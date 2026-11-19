import { computed, createSSRApp, h, reactive, ref } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it, vi } from 'vitest'
import type { Mr } from '../api/mrsApi'

const mrs = reactive({
  items: [] as Mr[],
  sel: null as string | null,
  detalle: null,
  detLoading: false,
  detError: '',
  busy: null as string | null,
  habilitado: false,
})
const mrSel = computed(() => mrs.items.find((m) => m.ref === mrs.sel) ?? null)

vi.mock('../motion', () => ({
  gsap: {},
  haptic: () => {},
  isSoft: () => true,
  useGsap: () => ({ run: (fn: () => void) => fn() }),
}))
vi.mock('../lib/time', () => ({
  ago: () => '',
  fechaLarga: () => '',
  useNow: () => ref(0),
}))
vi.mock('../lib/gitlabMarkdown', () => ({
  gitlabCtx: () => ({}),
  renderGitlabMarkdown: (s: string) => s,
  agruparActividad: () => [],
}))
vi.mock('../state/app', () => ({}))
const { mrsVisible, sesion } = vi.hoisted(() => ({ mrsVisible: { value: true }, sesion: { id: null as string | null } }))

vi.mock('../state/mrs', () => ({
  mrs,
  mrSel,
  mrsVisible,
  mrsPin: reactive({ open: false }),
  mrsApi: () => ({ opciones: async () => ({ equipo: [] }) }),
  aprobar: vi.fn(),
  cambiarReviewers: vi.fn(),
  cargarDetalle: vi.fn(),
  comentar: vi.fn(),
  marcarDraft: vi.fn(),
  pausar: vi.fn(),
  pedirActualizacion: vi.fn(),
  mandarASesion: vi.fn(),
  envio: reactive({ cual: '', hecho: '', error: { clave: '', msg: '' } }),
  mrsDestino: reactive({ open: false }),
  sesionDeMr: () => sesion.id,
  pedirPin: vi.fn(),
  reintentar: vi.fn(),
}))
vi.mock('./Icon.vue', () => ({ default: { name: 'Icon', render: () => null } }))
vi.mock('./InlineAlert.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./SkeletonList.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./MrPipe.vue', () => ({ default: { template: '<span />' } }))
vi.mock('./MrDestinoSheet.vue', () => ({ default: { template: '<i />' } }))

const { default: MrDetail } = await import('./MrDetail.vue')
const { normalizeDetalle } = await import('../api/mrsApi')

const baseMr: Mr = {
  ref: '7:1',
  project_id: 7,
  iid: 1,
  repo: 'grupo/repo7',
  repo_corto: 'repo7',
  titulo: 'feat: cosa',
  rama: 'feature/x',
  target: 'main',
  rol: 'autor',
  autor: { username: 'yo', nombre: 'Yo' },
  draft: false,
  conflictos: false,
  estado_merge: 'mergeable',
  puede_mergear: true,
  sha: 'a'.repeat(40),
  pipeline: { estado: 'ok', id: 1, url: '' },
  aprobaciones: { dadas: 0, requeridas: 1, faltan: 1, por: [], yo: false, puedo: false },
  reviewers: [],
  hilos_sin_resolver: 0,
  comentarios_nuevos: 0,
  url: 'https://gitlab.example.com/grupo/repo7/-/merge_requests/1',
  actualizado: '',
  creado: '',
  pausado: false,
}

async function renderDetail(mr: Mr) {
  mrs.items = [mr]
  mrs.sel = mr.ref
  mrs.detalle = null
  mrs.detLoading = false
  mrs.detError = ''
  return renderToString(
    createSSRApp({
      render: () => h(MrDetail, { onBack: () => {} }),
    }),
  )
}

describe('mrDetailEscapeAllowed', () => {
  it('con mrsVisible false no permite Escape', async () => {
    const { mrDetailEscapeAllowed } = await import('../lib/mrDetailEscape')
    expect(mrDetailEscapeAllowed(false, false, 'Escape', false)).toBe(false)
  })
  it('con mrsVisible true permite Escape', async () => {
    const { mrDetailEscapeAllowed } = await import('../lib/mrDetailEscape')
    expect(mrDetailEscapeAllowed(true, false, 'Escape', false)).toBe(true)
  })
})

describe('MrDetail', () => {
  it('copia el link del MR en la barra en lugar de abrir GitLab', async () => {
    const html = await renderDetail(baseMr)
    expect(html).toContain('aria-label="Copiar link del MR"')
    expect(html).not.toMatch(/<a[^>]*aria-label="Abrir en GitLab"/)
  })

  it('ofrece pedirle a la sesión que lo actualice solo si hay una sesión asociada', async () => {
    sesion.id = 'sess-a'
    expect(await renderDetail(baseMr)).toContain('Pedirle a la sesión que lo actualice')
    sesion.id = null
    expect(await renderDetail(baseMr)).not.toContain('Pedirle a la sesión que lo actualice')
  })
})

describe('MrDetail: mandar a la sesión', () => {
  const detalle = () =>
    normalizeDetalle({
      ...baseMr,
      jobs: [
        { id: 900, nombre: 'test', etapa: 'test', estado: 'fallo', status: 'failed' },
        { id: 901, nombre: 'lint', etapa: 'build', estado: 'ok', status: 'success' },
      ],
      hilos: [
        { id: 'ab12cd34ef', resoluble: true, resuelto: false, archivo: 'a.py', linea: 3, notas: [{ id: 1, cuerpo: 'hola', autor: { username: 'u' } }] },
        { id: 'cd34ef56ab', resoluble: true, resuelto: true, archivo: 'b.py', linea: 4, notas: [{ id: 2, cuerpo: 'ya', autor: { username: 'u' } }] },
        { id: 'ee34ef56ab', resoluble: false, resuelto: false, archivo: '', linea: 0, notas: [{ id: 3, cuerpo: 'charla', autor: { username: 'u' } }] },
      ],
      actividad: [],
      archivos: [],
    })!

  async function render() {
    mrs.items = [baseMr]
    mrs.sel = baseMr.ref
    mrs.detalle = detalle() as never
    mrs.detLoading = false
    mrs.detError = ''
    const html = await renderToString(createSSRApp({ render: () => h(MrDetail, { onBack: () => {} }) }))
    mrs.detalle = null
    return html
  }

  it('ofrece el botón solo en jobs fallidos y en hilos sin resolver', async () => {
    const html = await render()
    expect(html).toContain('aria-label="Mandar el job test a la sesión"')
    expect(html).not.toContain('Mandar el job lint a la sesión')
    expect(html.match(/Mandar el comentario de a\.py a la sesión/g)?.length).toBe(1)
    expect(html).not.toContain('b.py a la sesión')
    expect(html).toContain('Mandar el comentario a la sesión')
  })
})
