import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it, vi } from 'vitest'
import type { LoteDock } from '../lib/dock'
import { dockHold, pendientes } from '../lib/stepper'

vi.mock('../motion', () => ({
  finePointer: () => false,
  haptic: () => {},
  isSoft: () => true,
  ring: () => {},
  gsap: { set() {}, to() {}, killTweensOf() {}, utils: { selector: () => () => [] } },
  useGsap: () => ({ run: (fn: () => void) => fn() }),
}))
vi.stubGlobal('window', { matchMedia: () => ({ matches: false, addEventListener() {} }), addEventListener() {}, removeEventListener() {} })
const { default: PreguntasDock } = await import('./PreguntasDock.vue')

const texto = 'Elegí.\n\n```opciones\n{"pregunta":"¿Seguimos?","opciones":[{"label":"Sí"},{"label":"No"}]}\n```'
const pend = pendientes([{ id: '1', assistant: true, text: texto }])!
const lote: LoteDock = { key: 's:x', sig: pend.sig, questions: pend.questions }

const render = (hold: boolean) =>
  renderToString(createSSRApp({ render: () => h(PreguntasDock, { lotes: [lote], chatKey: 's:x', hold, active: true, send: () => true }, { default: () => h('div', { class: 'el-input' }) }) }))

describe('stepper de preguntas con la sesión working', () => {
  it('working solo (agentes en segundo plano o lo que sea) no lo retiene', () => {
    expect(dockHold({ working: true, blocked: false })).toBe(false)
    expect(dockHold({ working: false, blocked: false })).toBe(false)
  })
  it('con un diálogo bloqueante sí se retiene', () => {
    expect(dockHold({ working: true, blocked: true })).toBe(true)
    expect(dockHold({ working: false, blocked: true })).toBe(true)
  })
  it('working + opciones en el último mensaje: el stepper aparece sobre el input', async () => {
    const html = await render(dockHold({ working: true, blocked: false }))
    expect(html).toContain('¿Seguimos?')
  })
  it('retenido (blocked): queda el input y no el stepper', async () => {
    const html = await render(dockHold({ working: false, blocked: true }))
    expect(html).not.toContain('¿Seguimos?')
    expect(html).toContain('el-input')
  })
  it('SessionChatView usa dockHold y no retiene por working', async () => {
    const src = (await import('node:fs')).readFileSync(new URL('./SessionChatView.vue', import.meta.url).pathname, 'utf8')
    expect(src).toContain(':hold="dockHold({ working, blocked })"')
    expect(src).not.toContain(':hold="working')
  })
})

describe('stepper minimizado', () => {
  it('guardado como minimizado: barra con el progreso, sin stepper, input disponible', async () => {
    const { saveProgreso, clearProgreso } = await import('../lib/stepper')
    saveProgreso(lote.key, { sig: lote.sig, step: 0, answers: [null], dismissed: true, minimizado: true })
    const html = await render(false)
    clearProgreso(lote.key)
    expect(html).toContain('pmin')
    expect(html).toContain('tocá para responder')
    expect(html).toContain('el-input')
    expect(html).not.toContain('Minimizar preguntas')
  })
  it('el stepper abierto trae el boton Minimizar accesible', async () => {
    const html = await render(false)
    expect(html).toContain('aria-label="Minimizar preguntas"')
  })
  it('ambas vistas usan PreguntasDock', async () => {
    const fs = await import('node:fs')
    for (const f of ['SessionChatView.vue']) {
      expect(fs.readFileSync(new URL(`./${f}`, import.meta.url).pathname, 'utf8')).toContain('<PreguntasDock')
    }
  })
})

describe('tarjeta de opciones en el chat de la sesión', () => {
  it('SessionChatView arma el lote desde el último mensaje de Claude y lo pasa al dock', async () => {
    const src = (await import('node:fs')).readFileSync(new URL('./SessionChatView.vue', import.meta.url).pathname, 'utf8')
    expect(src).toContain('pendientes(')
    expect(src).toContain(':lotes="lotes"')
  })
  it('tocar la opción 1 manda "1. <label>"', async () => {
    const { buildReply } = await import('../lib/stepper')
    expect(buildReply(pend.questions, [{ kind: 'opcion', i: 0 }])).toBe('1. Sí')
  })
})
