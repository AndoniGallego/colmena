import { LEGACY_FENCE } from './legado'

const END_PUNCT = /[.:!?…]$/

interface Seg {
  text: string
  kind: 'p' | 'h' | 'li'
}

function inline(s: string): string {
  return s
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/<(https?:\/\/[^>\s]+)>/g, '$1')
    .replace(/<\/?[a-z][^>]*>/gi, '')
    .replace(/`+([^`]*)`+/g, '$1')
    .replace(/(\*\*|__)(.+?)\1/g, '$2')
    .replace(/(^|[\s(])[*_]([^*_\s][^*_]*?)[*_](?=[\s).,;:!?]|$)/g, '$1$2')
    .replace(/~~(.+?)~~/g, '$1')
    .replace(/(\*\*|__)/g, '')
    .replace(/`/g, '')
}

const BLOQUE = new RegExp(`(^|\\n)[ \\t]*(\`\`\`|~~~)(${LEGACY_FENCE}|diagrama|opciones)[^\\n]*\\n([\\s\\S]*?)(?:\\n[ \\t]*\\2[ \\t]*(?=\\n|$)|$)`, 'g')
const ESTADO = /(^|\n)[ \t]*(```|~~~)(?:estado|pruebas)[^\n]*\n[\s\S]*?(?:\n[ \t]*\2[ \t]*(?=\n|$)|$)/g
const CAMPO = /"(titulo|pregunta)"\s*:\s*"((?:[^"\\]|\\.)*)"/

/** Diagram and options blocks become a short phrase: their JSON never reaches a preview. */
export function sinBloques(src: string): string {
  return src.replace(ESTADO, '$1').replace(BLOQUE, (_, pre: string, _f: string, kind: string, body: string) => {
    const m = CAMPO.exec(body)
    let t = ''
    if (m) {
      try {
        t = String(JSON.parse(`"${m[2]}"`)).trim()
      } catch {
        t = m[2].trim()
      }
    }
    if (kind === 'opciones') return `${pre}${t || 'Opciones para elegir.'}\n`
    return `${pre}${t ? `Diagrama: ${t}${/[.!?…]$/.test(t) ? '' : '.'}` : 'Diagrama.'}\n`
  })
}

/** Markdown → una línea de texto plano para previews; el recorte lo hace el CSS (line-clamp). */
export function plainPreview(src: string | null | undefined): string {
  if (!src) return ''
  const segs: Seg[] = []
  let fence = false
  for (const raw of sinBloques(src.replace(/\r/g, '')).split('\n')) {
    const line = raw.trim()
    if (/^(```|~~~)/.test(line)) {
      fence = !fence
      continue
    }
    if (!line) continue
    if (fence) {
      segs.push({ text: line, kind: 'p' })
      continue
    }
    if (/^([-*_]\s*){3,}$/.test(line) || /^\|?[\s:|-]+\|?$/.test(line) && line.includes('-') && line.includes('|')) continue
    let m: RegExpMatchArray | null
    if ((m = line.match(/^#{1,6}\s+(.*)$/))) segs.push({ text: inline(m[1]).trim(), kind: 'h' })
    else if ((m = line.match(/^(?:[-*+]|\d+[.)])\s+(.*)$/))) segs.push({ text: inline(m[1]).trim(), kind: 'li' })
    else if (line.includes('|') && /^\|.*\|$/.test(line)) {
      const cells = line.slice(1, -1).split('|').map((c) => inline(c).trim()).filter(Boolean)
      segs.push({ text: cells.join(' · '), kind: 'p' })
    } else segs.push({ text: inline(line.replace(/^>+\s?/, '')).trim(), kind: 'p' })
  }
  let out = ''
  let prev: Seg | null = null
  for (const s of segs) {
    if (!s.text) continue
    if (prev) {
      if (prev.kind === 'h' && !END_PUNCT.test(out)) out += '.'
      out += s.kind === 'li' && prev.kind === 'li' ? ' · ' : ' '
    }
    out += s.text
    prev = s
  }
  return out.replace(/\s+/g, ' ').trim()
}
