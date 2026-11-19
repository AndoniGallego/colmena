import { describe, expect, it } from 'vitest'
import { agruparActividad, gitlabCtx, renderGitlabMarkdownRaw as render, resolveUrl, resumirSistema } from './gitlabMarkdown'

// sin DOM en node: se prueba la salida de markdown-it, que ya tiene que ser segura por sí sola (DOMPurify es la segunda capa)
const ctx = gitlabCtx('https://gitlab.com/mi-grupo/stores/services/datos/-/merge_requests/533')!

describe('gitlabCtx', () => {
  it('saca host, proyecto y MR del web_url', () => {
    expect(ctx).toEqual({
      origin: 'https://gitlab.com',
      projectUrl: 'https://gitlab.com/mi-grupo/stores/services/datos',
      mrUrl: 'https://gitlab.com/mi-grupo/stores/services/datos/-/merge_requests/533',
    })
  })
  it('sin https o sin MR no hay contexto', () => {
    expect(gitlabCtx('http://gitlab.com/a/b/-/merge_requests/1')).toBeNull()
    expect(gitlabCtx('javascript:alert(1)//-/merge_requests/1')).toBeNull()
    expect(gitlabCtx('')).toBeNull()
  })
})

describe('sanitización', () => {
  it('<script> y html con eventos quedan como texto escapado', () => {
    for (const src of ['<script>alert(1)</script>', 'hola <img src=x onerror=alert(1)>', '<svg onload=alert(1)>', '<a href="javascript:alert(1)">x</a>', '<iframe src="https://evil"></iframe>']) {
      const html = render(src, ctx)
      expect(html).not.toMatch(/<(script|img|svg|iframe)\b/i)
      expect(html).not.toMatch(/<[^>]+\son[a-z]+=/i)
      expect(html).not.toMatch(/href="javascript/i)
      expect(html).toContain('&lt;')
    }
  })

  it('links javascript:, data: y vbscript: no son links', () => {
    for (const src of ['[x](javascript:alert(1))', '[x](JaVaScRiPt:alert(1))', '[x](data:text/html,<b>)', '[x](vbscript:msgbox)', '<javascript:alert(1)>']) {
      const html = render(src, ctx)
      expect(html).not.toMatch(/href="(javascript|data|vbscript)/i)
      expect(html).not.toMatch(/<a\b/)
    }
  })

  it('solo http, https y mailto; target y rel seguros', () => {
    const html = render('[a](https://x.dev) [b](mailto:a@b.co) [c](ftp://x) [d](file:///etc/passwd)', ctx)
    expect(html).toContain('href="https://x.dev"')
    expect(html).toContain('href="mailto:a@b.co"')
    expect(html).not.toContain('href="ftp:')
    expect(html).not.toContain('href="file:')
    expect(html.match(/target="_blank"/g)).toHaveLength(2)
    expect(html.match(/rel="noopener noreferrer"/g)).toHaveLength(2)
  })

  it('las etiquetas permitidas no aceptan atributos', () => {
    const html = render('<details onclick="alert(1)">\n\n<b onmouseover=x>hola</b>', ctx)
    expect(html).not.toMatch(/<details/)
    expect(html).not.toMatch(/<b\b/)
    expect(html).not.toMatch(/<[^>]+\son[a-z]+=/i)
  })

  it('el summary pasa por el render inline: su html también se escapa', () => {
    const html = render('<details>\n<summary><img src=x onerror=alert(1)> **ver**</summary>\n\nadentro\n\n</details>', ctx)
    expect(html).toContain('<summary>&lt;img src=x onerror=alert(1)&gt; <strong>ver</strong></summary>')
  })

  it('url relativa fuera de GitLab o protocolo raro no resuelve', () => {
    expect(resolveUrl('/x', null)).toBeNull()
    expect(resolveUrl('//evil.com/x', ctx)).toBeNull()
    expect(resolveUrl('docs/a.md', ctx)).toBeNull()
    expect(resolveUrl(' javascript:alert(1)', ctx)).toBeNull()
    expect(resolveUrl('/mi-grupo/x/-/merge_requests/1', ctx)).toBe('https://gitlab.com/mi-grupo/x/-/merge_requests/1')
  })
})

describe('markdown de GitLab', () => {
  it('encabezados, listas, citas, tablas y código', () => {
    const html = render('## Cambios\n\n- uno\n- dos\n\n> cita\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```js\nconst x = 1 < 2\n```\n\nY `inline`.', ctx)
    expect(html).toContain('<h2>Cambios</h2>')
    expect(html).toContain('<li>uno</li>')
    expect(html).toContain('<blockquote>')
    expect(html).toContain('<div class="md-table"><table>')
    expect(html).toContain('<pre class="md-code"><span class="md-code-lang">js</span><code>const x = 1 &lt; 2')
    expect(html).toContain('<code>inline</code>')
  })

  it('checkboxes de solo lectura', () => {
    const html = render('- [x] hecho\n- [ ] falta\n- [y] no', ctx)
    expect(html).toContain('<li class="md-task"><input type="checkbox" class="md-check" disabled checked> hecho</li>')
    expect(html).toContain('<li class="md-task"><input type="checkbox" class="md-check" disabled> falta</li>')
    expect(html).toContain('<li>[y] no</li>')
  })

  it('details/summary de CodeRabbit y comentarios html', () => {
    const src = '<!-- This is an auto-generated comment -->\n<!-- internal state start -->\n<!-- ABCDEF==\nGHIJ== -->\n<!-- internal state end -->\n**Minor**\n\n<details>\n<summary>🔎 Supported</summary>\n\n```bash\nsed -n 1,10p a.js\n```\n\n</details>'
    const html = render(src, ctx)
    expect(html).not.toContain('auto-generated')
    expect(html).not.toContain('ABCDEF')
    expect(html).toContain('<strong>Minor</strong>')
    expect(html).toContain('<details class="md-details">')
    expect(html).toContain('<summary>🔎 Supported</summary>')
    expect(html).toContain('</details>')
  })

  it('cierra details sin cerrar y descarta cierres sueltos', () => {
    const open = render('<details>\n<summary>a</summary>\n\nb', ctx)
    expect(open.match(/<details/g)).toHaveLength(1)
    expect(open.match(/<\/details>/g)).toHaveLength(1)
    expect(render('</details>\n\nhola', ctx)).not.toContain('</details>')
  })

  it('html inline permitido sin atributos y <br>', () => {
    const html = render('a<br>b <code>x</code> <sub>y</sub> <!-- oculto --> c', ctx)
    expect(html).toContain('a<br>')
    expect(html).toContain('<code>x</code>')
    expect(html).toContain('<sub>y</sub>')
    expect(html).not.toContain('oculto')
  })

  it('imágenes: nunca <img>; relativas apuntan al MR, absolutas a su url', () => {
    const rel = render('![captura](/uploads/abc/foto.png)', ctx)
    expect(rel).not.toMatch(/<img/)
    expect(rel).toContain(`href="${ctx.mrUrl}"`)
    expect(rel).toContain('imagen: captura · ver en GitLab')
    const abs = render('![](https://cdn.dev/a.png)', ctx)
    expect(abs).toContain('href="https://cdn.dev/a.png"')
    expect(render('![x](/uploads/a.png)', null)).toContain('[imagen: x]')
  })

  it('links relativos de GitLab se anclan al host o al proyecto', () => {
    const html = render('[diff](/mi-grupo/x/-/merge_requests/1/diffs) [adj](/uploads/a/b.pdf) [ancla](#x)', ctx)
    expect(html).toContain('href="https://gitlab.com/mi-grupo/x/-/merge_requests/1/diffs"')
    expect(html).toContain('href="https://gitlab.com/mi-grupo/stores/services/datos/uploads/a/b.pdf"')
    expect(html).toContain('<span>ancla</span>')
  })

  it('menciones y referencias !123 / #45', () => {
    const html = render('@lucia.perez mirá !495 y #12. Mail a@b.com, sha abc#1x, `@code`', ctx)
    expect(html).toContain('<a href="https://gitlab.com/lucia.perez" class="md-mention" target="_blank" rel="noopener noreferrer">@lucia.perez</a>')
    expect(html).toContain('href="https://gitlab.com/mi-grupo/stores/services/datos/-/merge_requests/495" class="md-ref"')
    expect(html).toContain('/-/issues/12" class="md-ref"')
    expect(html).not.toContain('>@b.com<')
    expect(html).toContain('<code>@code</code>')
    expect(render('@ana', null)).toContain('<span class="md-mention">@ana</span>')
  })

  it('no linkifica nombres de archivo como dominios', () => {
    const html = render('ver README.md y start/routes.js, o https://x.dev', ctx)
    expect(html).not.toContain('http://README.md')
    expect(html).toContain('href="https://x.dev"')
  })
})

describe('notas de sistema', () => {
  it('resume y traduce las conocidas', () => {
    expect(resumirSistema('added 38 commits\n\n<ul><li>824036f5 - x</li></ul>')).toBe('sumó 38 commits')
    expect(resumirSistema('added 1 commit\n\n<ul></ul>')).toBe('sumó 1 commit')
    expect(resumirSistema('approved this merge request')).toBe('aprobó el MR')
    expect(resumirSistema('requested review from @diego.ramos and removed review request for @camila.torres')).toBe('pidió revisión a @diego.ramos y sacó a @camila.torres')
    expect(resumirSistema('requested review from @ana and @beto')).toBe('pidió revisión a @ana y @beto')
    expect(resumirSistema('marked this merge request as **ready**')).toBe('lo marcó listo para revisar')
    expect(resumirSistema('changed this line in [version 5 of the diff](/a/-/merge_requests/1/diffs?x=1)')).toBe('cambió una línea comentada (versión 5)')
    expect(resumirSistema('mentioned in commit f27a32acc73dd38ce7846dbe876108ed09a511f7')).toBe('lo mencionó en el commit f27a32a')
  })
  it('las desconocidas quedan en texto plano, sin html', () => {
    expect(resumirSistema('did <b>something</b> &amp; [more](https://x)')).toBe('did something & more')
  })
  it('agrupa eventos seguidos iguales', () => {
    const bot = { username: 'bot', nombre: 'CodeRabbit' }
    const yo = { username: 'yo', nombre: 'Yo' }
    const g = agruparActividad(
      [
        { id: 1, autor: bot, cuerpo: 'changed the description', fecha: 'a' },
        { id: 2, autor: bot, cuerpo: 'changed the description', fecha: 'b' },
        { id: 3, autor: yo, cuerpo: 'approved this merge request', fecha: 'c', mio: true },
        { id: 4, autor: bot, cuerpo: 'changed the description', fecha: 'd' },
      ],
    )
    expect(g.map((e) => [e.quien, e.texto, e.veces])).toEqual([
      ['CodeRabbit', 'cambió la descripción', 2],
      ['Vos', 'aprobó el MR', 1],
      ['CodeRabbit', 'cambió la descripción', 1],
    ])
    expect(g[0].fecha).toBe('b')
  })
})
