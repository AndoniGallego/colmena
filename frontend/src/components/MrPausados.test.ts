import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it, vi } from 'vitest'
import type { Mr } from '../api/mrsApi'

vi.mock('../motion', () => ({ gsap: {}, haptic: () => {}, isSoft: () => true, useGsap: () => ({ run: (fn: () => void) => fn() }) }))
vi.mock('./Icon.vue', () => ({ default: { template: '<i />' } }))
vi.mock('./MrCard.vue', () => ({ default: { props: ['m'], template: '<div class="mock-card">{{ m.ref }}</div>' } }))

const { default: MrPausados } = await import('./MrPausados.vue')

const m: Mr = {
  ref: '7:2',
  project_id: 7,
  iid: 2,
  repo: 'g/r',
  repo_corto: 'r',
  titulo: 't',
  rama: 'f',
  target: 'main',
  rol: 'autor',
  autor: { username: 'u', nombre: 'U' },
  draft: false,
  conflictos: false,
  estado_merge: '',
  puede_mergear: true,
  sha: 'a'.repeat(40),
  pipeline: { estado: 'ok', id: 1, url: '' },
  aprobaciones: { dadas: 0, requeridas: 0, faltan: 0, por: [], yo: false, puedo: false },
  reviewers: [],
  hilos_sin_resolver: 0,
  comentarios_nuevos: 0,
  url: '',
  actualizado: '',
  creado: '',
  pausado: true,
}

async function render(open: boolean) {
  return renderToString(
    createSSRApp({
      render: () => h(MrPausados, { items: [m], now: 0, open, 'onUpdate:open': () => {} }),
    }),
  )
}

describe('MrPausados', () => {
  it('muestra el botón y oculta la lista hasta abrir', async () => {
    const cerrado = await render(false)
    expect(cerrado).toContain('Ver en pausa (1)')
    expect(cerrado).not.toContain('mock-card')

    const abierto = await render(true)
    expect(abierto).toContain('Ocultar en pausa (1)')
    expect(abierto).toContain('7:2')
  })
})
