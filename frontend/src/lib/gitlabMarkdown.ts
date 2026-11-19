import MarkdownIt, { type StateBlock, type StateCore, type StateInline, type Token } from 'markdown-it'
import DOMPurify from 'dompurify'
import { applyBaseRules, SANITIZE } from './markdown'

/** Contexto para resolver links relativos, menciones y referencias del proyecto en GitLab. */
export interface GitlabCtx {
  origin: string
  projectUrl: string
  mrUrl: string
}

const MR_URL_RE = /^(https:\/\/[^/?#]+)(\/[^?#]+?)\/-\/merge_requests\/\d+/

export function gitlabCtx(mrUrl: string | undefined | null): GitlabCtx | null {
  const m = MR_URL_RE.exec(mrUrl ?? '')
  return m ? { origin: m[1], projectUrl: m[1] + m[2], mrUrl: m[0] } : null
}

/** Solo http, https y mailto; lo relativo a GitLab se ancla al proyecto o al host, el resto se descarta. */
export function resolveUrl(href: string, ctx: GitlabCtx | null): string | null {
  const h = href.trim()
  if (/^[a-z][a-z0-9+.-]*:/i.test(h)) {
    try {
      const u = new URL(h)
      return ['http:', 'https:', 'mailto:'].includes(u.protocol) ? h : null
    } catch {
      return null
    }
  }
  if (!ctx || !h.startsWith('/') || h.startsWith('//')) return null
  return (h.startsWith('/uploads/') ? ctx.projectUrl : ctx.origin) + h
}

const md = new MarkdownIt({ html: false, linkify: true, breaks: false, typographer: false })
md.linkify.set({ fuzzyLink: false, fuzzyEmail: false })
applyBaseRules(md)

// ---------- HTML de GitLab: solo una lista corta de etiquetas sin atributos, regeneradas por nosotros ----------

const BLOCK_PIECE = /\s*(?:<details(\s+open)?\s*>|<\/details\s*>|<summary\s*>(.*?)<\/summary\s*>|<summary\s*>|<\/summary\s*>|<br\s*\/?>|<hr\s*\/?>|<\/?(?:p|div|center)(?:\s[^<>]*)?>)/y

type GlTag = 'details' | 'summary'
interface Piece {
  html: string
  open?: GlTag
  close?: GlTag
}

function parseBlockLine(line: string, env: StateBlock['env']): Piece[] | null {
  const out: Piece[] = []
  BLOCK_PIECE.lastIndex = 0
  let pos = 0
  while (pos < line.length) {
    if (!line.slice(pos).trim()) break
    BLOCK_PIECE.lastIndex = pos
    const m = BLOCK_PIECE.exec(line)
    if (!m) return null
    pos = BLOCK_PIECE.lastIndex
    const tag = m[0].trim().toLowerCase()
    if (tag.startsWith('<details')) out.push({ html: `<details class="md-details"${m[1] ? ' open' : ''}>`, open: 'details' })
    else if (tag.startsWith('</details')) out.push({ html: '</details>', close: 'details' })
    else if (m[2] !== undefined) out.push({ html: `<summary>${md.renderInline(m[2], env)}</summary>` })
    else if (tag.startsWith('<summary')) out.push({ html: '<summary>', open: 'summary' })
    else if (tag.startsWith('</summary')) out.push({ html: '</summary>', close: 'summary' })
    else if (tag.startsWith('<hr')) out.push({ html: '<hr>' })
  }
  return out.length || line.trim() ? out : null
}

function glBlock(state: StateBlock, startLine: number, endLine: number, silent: boolean): boolean {
  if (state.sCount[startLine] - state.blkIndent >= 4) return false
  const lineAt = (n: number) => state.src.slice(state.bMarks[n] + state.tShift[n], state.eMarks[n])
  const first = lineAt(startLine)
  if (first.charCodeAt(0) !== 0x3c /* < */) return false

  if (first.startsWith('<!--')) {
    let n = startLine
    while (n < endLine && !lineAt(n).includes('-->')) n++
    if (silent) return true
    state.line = Math.min(n + 1, endLine)
    return true
  }

  const pieces = parseBlockLine(first, state.env)
  if (!pieces) return false
  if (silent) return true
  for (const p of pieces) {
    const t = state.push('html_block', '', 0)
    t.content = p.html + '\n'
    t.map = [startLine, startLine + 1]
    t.meta = { gl: p.open ? `+${p.open}` : p.close ? `-${p.close}` : '' }
  }
  state.line = startLine + 1
  return true
}
md.block.ruler.before('html_block', 'gl_html', glBlock, { alt: ['paragraph', 'reference', 'blockquote'] })

const INLINE_TAG = /<!--[\s\S]*?-->|<br\s*\/?>|<(\/?)(b|strong|i|em|code|sub|sup|kbd|s|del|ins|mark|small|u)\s*>/iy

function glInline(state: StateInline, silent: boolean): boolean {
  if (state.src.charCodeAt(state.pos) !== 0x3c) return false
  INLINE_TAG.lastIndex = state.pos
  const m = INLINE_TAG.exec(state.src)
  if (!m) return false
  if (!silent) {
    if (m[0].toLowerCase().startsWith('<br')) state.push('hardbreak', 'br', 0)
    else if (m[2]) state.push('html_inline', '', 0).content = `<${m[1]}${m[2].toLowerCase()}>`
  }
  state.pos += m[0].length
  return true
}
md.inline.ruler.before('html_inline', 'gl_inline', glInline)

// ---------- post-proceso: cierre de etiquetas, links, imágenes, checkboxes y menciones ----------

interface GitlabEnv {
  ctx?: GitlabCtx | null
}

function balance(state: StateCore) {
  const stack: GlTag[] = []
  for (const t of state.tokens) {
    const gl = t.type === 'html_block' ? (t.meta?.gl as string | undefined) : undefined
    if (!gl) continue
    const tag = gl.slice(1) as GlTag
    if (gl[0] === '+') stack.push(tag)
    else if (stack[stack.length - 1] === tag) stack.pop()
    else t.content = ''
  }
  while (stack.length) {
    const t = new state.Token('html_block', '', 0)
    t.content = `</${stack.pop()}>\n`
    state.tokens.push(t)
  }
}

function taskItems(state: StateCore) {
  const toks = state.tokens
  for (let i = 2; i < toks.length; i++) {
    const t = toks[i]
    if (t.type !== 'inline' || toks[i - 1].type !== 'paragraph_open' || toks[i - 2].type !== 'list_item_open') continue
    const first = t.children?.[0]
    const m = first?.type === 'text' ? /^\[([ xX])\]\s+/.exec(first.content) : null
    if (!first || !m || !t.children) continue
    first.content = first.content.slice(m[0].length)
    const box = new state.Token('html_inline', '', 0)
    box.content = `<input type="checkbox" class="md-check" disabled${m[1] === ' ' ? '' : ' checked'}> `
    t.children.unshift(box)
    toks[i - 2].attrJoin('class', 'md-task')
  }
}

const REF_RE = /(^|[^\w@/.!#&-])(@[A-Za-z0-9_](?:[A-Za-z0-9_.-]*[A-Za-z0-9_])?|![0-9]{1,9}|#[0-9]{1,9})(?![\w-])/g

function refTokens(state: StateCore, text: string, ctx: GitlabCtx | null): Token[] | null {
  REF_RE.lastIndex = 0
  const out: Token[] = []
  let last = 0
  let m: RegExpExecArray | null
  const pushText = (s: string) => {
    if (!s) return
    const t = new state.Token('text', '', 0)
    t.content = s
    out.push(t)
  }
  while ((m = REF_RE.exec(text))) {
    const start = m.index + m[1].length
    const ref = m[2]
    pushText(text.slice(last, start))
    const kind = ref[0] === '@' ? 'md-mention' : 'md-ref'
    let href = ''
    if (ctx) {
      if (ref[0] === '@') href = `${ctx.origin}/${ref.slice(1)}`
      else if (ref[0] === '!') href = `${ctx.projectUrl}/-/merge_requests/${ref.slice(1)}`
      else href = `${ctx.projectUrl}/-/issues/${ref.slice(1)}`
    }
    const open = new state.Token(href ? 'link_open' : 'gl_open', href ? 'a' : 'span', 1)
    open.attrs = href ? [['href', href], ['class', kind]] : [['class', kind]]
    const close = new state.Token(href ? 'link_close' : 'gl_close', href ? 'a' : 'span', -1)
    out.push(open)
    pushText(ref)
    out.push(close)
    last = start + ref.length
  }
  if (!out.length) return null
  pushText(text.slice(last))
  return out
}

function imageTokens(state: StateCore, img: Token, ctx: GitlabCtx | null): Token[] {
  const alt = (img.children?.map((c) => c.content).join('') || img.content || '').trim()
  const src = String(img.attrGet('src') ?? '')
  const abs = /^https?:\/\//i.test(src) ? resolveUrl(src, ctx) : null
  const href = abs ?? ctx?.mrUrl ?? ''
  const label = alt ? `imagen: ${alt}` : 'imagen'
  const text = new state.Token('text', '', 0)
  if (!href) {
    text.content = `[${label}]`
    return [text]
  }
  text.content = abs ? label : `${label} · ver en GitLab`
  const open = new state.Token('link_open', 'a', 1)
  open.attrs = [['href', href], ['class', 'md-img']]
  return [open, text, new state.Token('link_close', 'a', -1)]
}

function inlinePost(state: StateCore, ctx: GitlabCtx | null) {
  for (const block of state.tokens) {
    if (block.type !== 'inline' || !block.children) continue
    const out: Token[] = []
    const links: boolean[] = []
    for (const t of block.children) {
      if (t.type === 'link_open') {
        const href = resolveUrl(String(t.attrGet('href') ?? ''), ctx)
        if (href) t.attrSet('href', href)
        else {
          t.type = 'gl_open'
          t.tag = 'span'
          t.attrs = null
        }
        links.push(!href)
        out.push(t)
      } else if (t.type === 'link_close') {
        if (links.pop()) {
          t.type = 'gl_close'
          t.tag = 'span'
        }
        out.push(t)
      } else if (t.type === 'image') {
        out.push(...imageTokens(state, t, ctx))
      } else if (t.type === 'text' && !links.length) {
        out.push(...(refTokens(state, t.content, ctx) ?? [t]))
      } else out.push(t)
    }
    block.children = out
  }
}

md.core.ruler.push('gl_post', (state) => {
  const ctx = (state.env as GitlabEnv).ctx ?? null
  balance(state)
  taskItems(state)
  inlinePost(state, ctx)
})

export function renderGitlabMarkdownRaw(src: string, ctx: GitlabCtx | null = null): string {
  if (!src) return ''
  return md.render(src, { ctx })
}

/** Markdown de GitLab (descripciones y comentarios) a HTML seguro, con el mismo estilo que el chat. */
export function renderGitlabMarkdown(src: string, ctx: GitlabCtx | null = null): string {
  if (!src) return ''
  return DOMPurify.sanitize(renderGitlabMarkdownRaw(src, ctx), SANITIZE)
}

// ---------- notas de sistema ----------

const SISTEMA: [RegExp, (...g: string[]) => string][] = [
  [/^added (\d+) (?:new )?commits?/i, (n) => (n === '1' ? 'sumó 1 commit' : `sumó ${n} commits`)],
  [/^approved this merge request/i, () => 'aprobó el MR'],
  [/^unapproved this merge request/i, () => 'sacó su aprobación'],
  [/^changed the description/i, () => 'cambió la descripción'],
  [/^changed title/i, () => 'cambió el título'],
  [/^requested review from (.+?) and removed review request for (.+)$/i, (a, b) => `pidió revisión a ${a} y sacó a ${b}`],
  [/^requested review from (.+)$/i, (a) => `pidió revisión a ${a}`],
  [/^removed review request for (.+)$/i, (a) => `sacó la revisión de ${a}`],
  [/^assigned to (.+)$/i, (a) => `asignó a ${a}`],
  [/^unassigned (.+)$/i, (a) => `desasignó a ${a}`],
  [/^marked this merge request as ready/i, () => 'lo marcó listo para revisar'],
  [/^marked this merge request as draft/i, () => 'lo pasó a draft'],
  [/^marked as a draft/i, () => 'lo pasó a draft'],
  [/^resolved all threads/i, () => 'resolvió todos los hilos'],
  [/^mentioned in merge request (.+)$/i, (a) => `lo mencionó en el MR ${a}`],
  [/^mentioned in commit ([0-9a-f]{7})/i, (a) => `lo mencionó en el commit ${a}`],
  [/^mentioned in issue (.+)$/i, (a) => `lo mencionó en ${a}`],
  [/^changed this line in version (\d+) of the diff/i, (n) => `cambió una línea comentada (versión ${n})`],
  [/^changed target branch from (.+) to (.+)$/i, (_a, b) => `cambió el destino a ${b}`],
  [/^enabled an automatic merge/i, () => 'activó el merge automático'],
  [/^canceled the automatic merge/i, () => 'canceló el merge automático'],
  [/^merged$/i, () => 'mergeó el MR'],
  [/^closed$/i, () => 'cerró el MR'],
  [/^reopened$/i, () => 'reabrió el MR'],
]

/** Primera línea de una nota de sistema en texto plano y en castellano cuando es una conocida. */
export function resumirSistema(body: string): string {
  const line = (body ?? '').split('\n').find((l) => l.trim()) ?? ''
  const plain = line
    .replace(/<[^>]*>/g, ' ')
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\*\*|__|`/g, '')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&#39;|&apos;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/\s+/g, ' ')
    .trim()
  for (const [re, fn] of SISTEMA) {
    const m = re.exec(plain)
    if (m) return fn(...m.slice(1).map((g) => (g ?? '').replace(/ and /g, ' y ')))
  }
  return plain.length > 160 ? `${plain.slice(0, 159)}…` : plain
}

export interface EventoSistema {
  id: number
  autor: { username: string; nombre: string }
  cuerpo: string
  fecha: string
  mio?: boolean
}

export interface EventoAgrupado {
  id: number
  quien: string
  texto: string
  veces: number
  fecha: string
}

/** Junta eventos seguidos iguales (mismo autor y mismo texto) en una sola línea con contador. */
export function agruparActividad(eventos: EventoSistema[]): EventoAgrupado[] {
  const out: EventoAgrupado[] = []
  for (const e of eventos) {
    const quien = e.mio ? 'Vos' : e.autor.nombre || e.autor.username || 'GitLab'
    const texto = resumirSistema(e.cuerpo)
    if (!texto) continue
    const prev = out[out.length - 1]
    if (prev && prev.quien === quien && prev.texto === texto) {
      prev.veces++
      prev.fecha = e.fecha || prev.fecha
    } else out.push({ id: e.id, quien, texto, veces: 1, fecha: e.fecha })
  }
  return out
}
