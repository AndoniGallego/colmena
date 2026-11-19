// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

vi.hoisted(() => {
  window.matchMedia ??= ((q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} })) as unknown as typeof window.matchMedia
})
import ComandoCard from './ComandoCard.vue'
import SegmentsView from './SegmentsView.vue'
import { parseSegments } from '../lib/segments'

describe('SegmentsView con bloques comando', () => {
  it('numera cada tarjeta desde cstart y le pasa sesión y mensaje', async () => {
    const b = (c: string) => '```comando\n' + JSON.stringify({ comando: c, motivo: 'm' }) + '\n```'
    const w = mount(SegmentsView, {
      props: { segments: parseSegments(`a\n\n${b('ls')}\n\nb\n\n${b('pwd')}`), sessionId: 's1', cmid: 'mid-aaaaaaaa', cstart: 3 },
    })
    const cards = w.findAllComponents(ComandoCard)
    expect(cards.map((c) => [c.props('indice'), c.props('mid'), c.props('sessionId')])).toEqual([
      [3, 'mid-aaaaaaaa', 's1'],
      [4, 'mid-aaaaaaaa', 's1'],
    ])
  })
  it('le pasa a cada tarjeta el cwd real del mensaje', () => {
    const b = '```comando\n' + JSON.stringify({ comando: 'ls', motivo: 'm' }) + '\n```'
    const w = mount(SegmentsView, {
      props: { segments: parseSegments(b), sessionId: 's1', cmid: 'mid-aaaaaaaa', cstart: 0, ccwd: '/srv/app' },
    })
    expect(w.findComponent(ComandoCard).props('cwd')).toBe('/srv/app')
  })
})
