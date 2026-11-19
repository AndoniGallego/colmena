import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it, vi } from 'vitest'
import { parseSegments } from '../lib/segments'

vi.mock('../lib/markdown', () => ({ renderMarkdown: (t: string) => (t.includes('```') ? `<pre><code>${t}</code></pre>` : `<p>${t}</p>`) }))
vi.mock('./DiagramaCard.vue', () => ({ default: { render: () => null } }))
vi.mock('./PruebasCard.vue', () => ({ default: { render: () => null } }))

import SegmentsView from './SegmentsView.vue'

const render = (text: string) => renderToString(createSSRApp({ render: () => h(SegmentsView, { segments: parseSegments(text) }) }))
const bloque = (cuerpo: string) => '```estado\n' + cuerpo + '\n```'

describe('SegmentsView con bloque estado', () => {
  it('lo dibuja como tarjetita con las líneas, no como código ni JSON', async () => {
    const html = await render(`Listo.\n\n${bloque('{"hizo": "Saqué el mapa", "falta": "Elegir", "pide": "¿Cuál?"}')}`)
    expect(html).toContain('estado-card')
    expect(html).toContain('Saqué el mapa')
    expect(html).toContain('Falta: Elegir')
    expect(html).toContain('¿Cuál?')
    expect(html).not.toContain('"hizo"')
    expect(html).not.toContain('<code')
  })

  it('con JSON inválido lo muestra como código', async () => {
    const html = await render(bloque('{"hizo": '))
    expect(html).not.toContain('estado-card')
    expect(html).toContain('<code')
  })
})
