import { describe, expect, it, vi } from 'vitest'
import { renderMarkdown } from './markdown'

// sin DOM en node: se prueba la salida de markdown-it (la capa que decide si hay <img>)
vi.mock('dompurify', () => ({ default: { sanitize: (h: string) => h } }))

describe('renderMarkdown', () => {
  it('no emite <img>: la imagen queda como texto', () => {
    const html = renderMarkdown('![mapa](https://evil.example/x.png?d=secreto)')
    expect(html).not.toMatch(/<img/i)
    expect(html).not.toContain('evil.example')
    expect(html).toContain('[imagen: mapa]')
  })

  it('imagen sin alt y html crudo', () => {
    expect(renderMarkdown('![](https://a/b.png)')).toContain('[imagen]')
    expect(renderMarkdown('<img src=x onerror=alert(1)>')).not.toMatch(/<img/i)
  })

  it('los links abren en pestaña nueva con rel seguro', () => {
    const html = renderMarkdown('[doc](https://example.com)')
    expect(html).toContain('target="_blank"')
    expect(html).toContain('rel="noopener noreferrer"')
  })

  it('un fence con lenguaje incluye botón copiar dentro del pre (post-sanitize)', () => {
    const html = renderMarkdown('```bash\necho hi\n```')
    expect(html).toMatch(/<pre class="md-code">[\s\S]*<button[^>]*class="md-copy"[\s\S]*<\/pre>/)
    expect(html).toContain('<span class="md-code-lang">bash</span>')
    expect(html).toContain('aria-label="Copiar código"')
    expect(html).toContain('<code>echo hi\n</code>')
  })

  it('un fence sin lenguaje también incluye botón copiar', () => {
    const html = renderMarkdown('```\nplain\n```')
    expect(html).toMatch(/<pre class="md-code"><button type="button" class="md-copy"/)
    expect(html).not.toContain('md-code-lang')
    expect(html).toContain('<code>plain\n</code>')
  })
})
