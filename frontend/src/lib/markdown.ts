import MarkdownIt, { type MarkdownIt as MD, type RendererRule } from 'markdown-it'
import DOMPurify from 'dompurify'

const passthrough: RendererRule =(t, i, o, _e, self) => self.renderToken(t, i, o)

/** Reglas compartidas por el chat y los MRs: links seguros, tablas y código que scrollean en su propia caja. */
export function applyBaseRules(md: MD) {
  const defaultLink = md.renderer.rules.link_open ?? passthrough
  md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
    tokens[idx].attrSet('target', '_blank')
    tokens[idx].attrSet('rel', 'noopener noreferrer')
    return defaultLink(tokens, idx, options, env, self)
  }

  const defaultTable = md.renderer.rules.table_open ?? passthrough
  md.renderer.rules.table_open = (tokens, idx, options, env, self) => '<div class="md-table">' + defaultTable(tokens, idx, options, env, self)
  const defaultTableClose = md.renderer.rules.table_close ?? passthrough
  md.renderer.rules.table_close = (tokens, idx, options, env, self) => defaultTableClose(tokens, idx, options, env, self) + '</div>'

  md.renderer.rules.fence = (tokens, idx) => {
    const t = tokens[idx]
    const lang = md.utils.escapeHtml(t.info.trim().split(/\s+/)[0] ?? '')
    const label = lang ? `<span class="md-code-lang">${lang}</span>` : ''
    const copyBtn = '<button type="button" class="md-copy" aria-label="Copiar código"></button>'
    return `<pre class="md-code">${label}${copyBtn}<code>${md.utils.escapeHtml(t.content)}</code></pre>`
  }
}

export const SANITIZE = { ADD_ATTR: ['target'], FORBID_TAGS: ['img', 'picture', 'source', 'svg', 'style', 'form'] }

const md = new MarkdownIt({ html: false, linkify: true, breaks: true, typographer: false })
applyBaseRules(md)

md.renderer.rules.image = (tokens, idx) => {
  const alt = tokens[idx].content.trim()
  const src = String(tokens[idx].attrGet('src') || '')
  if (src.startsWith('/') && !src.startsWith('//')) {
    return md.utils.escapeHtml(alt)
  }
  return md.utils.escapeHtml(alt ? `[imagen: ${alt}]` : '[imagen]')
}

export function renderMarkdown(src: string): string {
  if (!src) return ''
  return DOMPurify.sanitize(md.render(src), SANITIZE)
}
