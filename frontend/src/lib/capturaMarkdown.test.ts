import { describe, expect, it, vi } from 'vitest'
import { renderMarkdown } from './markdown'

vi.mock('dompurify', () => ({ default: { sanitize: (h: string) => h } }))

describe('renderMarkdown rutas locales', () => {
  it('ruta absoluta local: alt discreto, sin URL en el HTML', () => {
    const html = renderMarkdown('![Búsqueda mug](/tmp/claude-chrome-screenshots-x/a.jpg)')
    expect(html).not.toMatch(/<img/i)
    expect(html).not.toContain('/tmp/claude')
    expect(html).toContain('Búsqueda mug')
  })

  it('https sigue como texto de imagen', () => {
    const html = renderMarkdown('![mapa](https://example.com/x.png)')
    expect(html).toContain('[imagen: mapa]')
  })
})
