import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const readStyle = (name: string) =>
  readFileSync(new URL(`./${name}`, import.meta.url).pathname, 'utf8')

const rawVue = import.meta.glob('../**/*.vue', { query: '?raw', import: 'default', eager: true }) as Record<string, string>
const rawLibTs = import.meta.glob(['../lib/**/*.ts', '../piezas/*/lib/**/*.ts'], { query: '?raw', import: 'default', eager: true }) as Record<string, string>

function relPath(globKey: string) {
  return globKey.replace(/^\.\.\//, 'src/')
}

function lineOf(text: string, index: number) {
  return text.slice(0, index).split('\n').length
}

const VAR_DEF = /--([a-zA-Z0-9_-]+)\s*:/g
const VAR_USE = /var\(\s*--([a-zA-Z0-9][a-zA-Z0-9_-]*)(?=\s*[,)])/g

function defsFromCss(text: string) {
  const s = new Set<string>()
  let m: RegExpExecArray | null
  VAR_DEF.lastIndex = 0
  while ((m = VAR_DEF.exec(text))) s.add(m[1])
  return s
}

function defsFromVue(text: string) {
  const s = new Set<string>()
  const blocks = [...text.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/gi)]
  for (const b of blocks) defsFromCss(b[1]).forEach((x) => s.add(x))
  return s
}

function defsFromTs(text: string) {
  const s = new Set<string>()
  const patterns = [
    /setProperty\(\s*['"](--[^'"]+)['"]/g,
    /['"](--[a-zA-Z0-9_-]+)['"]\s*:/g,
  ]
  for (const re of patterns) {
    re.lastIndex = 0
    let m: RegExpExecArray | null
    while ((m = re.exec(text))) {
      const name = m[1].replace(/^--/, '')
      s.add(name)
    }
  }
  return s
}

function hasVarFallback(text: string, index: number) {
  const slice = text.slice(index, index + 120)
  return /^var\(\s*--[a-zA-Z0-9_-]+\s*,/.test(slice)
}

function collectDefinedVars() {
  const defined = new Set<string>()
  for (const name of ['base.css', 'ui.css']) {
    defsFromCss(readStyle(name)).forEach((x) => defined.add(x))
  }
  for (const [, text] of Object.entries(rawVue)) {
    defsFromVue(text).forEach((x) => defined.add(x))
    defsFromTs(text).forEach((x) => defined.add(x))
  }
  for (const [key, text] of Object.entries(rawLibTs)) {
    if (key.includes('.test.')) continue
    defsFromTs(text).forEach((x) => defined.add(x))
    if (key.includes('ansi.ts')) {
      for (let i = 0; i < 256; i++) defined.add(`ansi-${i}`)
    }
  }
  return defined
}

/** Runtime-only tokens referenced with explicit fallbacks in var(). */
const VAR_FALLBACK_OK = new Set<string>([
  // --sbw se asigna en runtime al medir scrollbar
  'sbw',
])

function hexToRgb(hex: string) {
  const h = hex.replace('#', '')
  const n = parseInt(h.length === 3 ? h.replace(/./g, '$&$&') : h, 16)
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 }
}

function relLum(hex: string) {
  const { r, g, b } = hexToRgb(hex)
  const lin = (c: number) => {
    const s = c / 255
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
}

function contrast(fg: string, bg: string) {
  const l1 = relLum(fg)
  const l2 = relLum(bg)
  const hi = Math.max(l1, l2)
  const lo = Math.min(l1, l2)
  return (hi + 0.05) / (lo + 0.05)
}

function themeVars(baseCss: string, theme: 'dark' | 'light') {
  const blockRe =
    theme === 'dark'
      ? /:root,\s*\n:root\[data-theme='dark'\]\s*\{([^}]+)\}/s
      : /:root\[data-theme='light'\]\s*\{([^}]+)\}/s
  const m = baseCss.match(blockRe)
  if (!m) throw new Error(`bloque ${theme} no encontrado`)
  const vars: Record<string, string> = {}
  for (const line of m[1].split('\n')) {
    const hit = line.match(/^\s*(--[a-zA-Z0-9_-]+):\s*(#[0-9a-fA-F]{3,8})\s*;/)
    if (hit) vars[hit[1]] = hit[2]
  }
  return vars
}

// Spinners de carga: clases *spin* / spinner o keyframes spin|ui-spin
const SPINNER_SELECTOR = /(?:\.[\w-]*\b(?:spin|spinner)\b[\w-]*|animation:\s*(?:ui-)?spin\b)/

describe('tokens CSS', () => {
  it('cada var(--x) apunta a una variable definida (o fallback permitido)', () => {
    const defined = collectDefinedVars()
    const offenders: string[] = []
    const styleFiles = { 'src/styles/base.css': readStyle('base.css'), 'src/styles/ui.css': readStyle('ui.css') }
    const files: Record<string, string> = { ...rawVue, ...styleFiles }
    for (const [key, text] of Object.entries(rawLibTs)) {
      if (!key.includes('.test.')) files[relPath(key)] = text
    }
    for (const [key, text] of Object.entries(files)) {
      const rel = key.startsWith('src/') ? key : relPath(key)
      VAR_USE.lastIndex = 0
      let m: RegExpExecArray | null
      while ((m = VAR_USE.exec(text))) {
        const name = m[1]
        if (defined.has(name)) continue
        if (hasVarFallback(text, m.index)) continue
        if (VAR_FALLBACK_OK.has(name)) continue
        offenders.push(`${rel}:${lineOf(text, m.index)}: --${name}`)
      }
    }
    expect(offenders, offenders.join('\n')).toEqual([])
  })

  it('contraste WCAG de texto y st-blocked sobre bg y surface', () => {
    const base = readStyle('base.css')
    const themes = ['dark', 'light'] as const
    const report: string[] = []
    for (const th of themes) {
      const v = themeVars(base, th)
      const pairs: Array<{ fg: string; minOnBg: number; minOnSurface: number; label: string }> = [
        { fg: '--text-3', minOnBg: 4.5, minOnSurface: 4.5, label: 'text-3' },
        { fg: '--text-4', minOnBg: 3, minOnSurface: 3, label: 'text-4' },
        { fg: '--st-blocked', minOnBg: th === 'light' ? 4.5 : 3, minOnSurface: th === 'light' ? 4.5 : 3, label: 'st-blocked' },
      ]
      for (const p of pairs) {
        const fg = v[p.fg]
        const bg = v['--bg']
        const surf = v['--surface']
        const cBg = contrast(fg, bg)
        const cSurf = contrast(fg, surf)
        report.push(`${th} ${p.label} on bg=${cBg.toFixed(2)} surface=${cSurf.toFixed(2)} (${fg})`)
        expect(cBg, `${th} ${p.label} on bg`).toBeGreaterThanOrEqual(p.minOnBg)
        expect(cSurf, `${th} ${p.label} on surface`).toBeGreaterThanOrEqual(p.minOnSurface)
      }
    }
    expect(report.length).toBeGreaterThan(0)
  })

  it('pointer coarse sube h-sm y h-md a 44px', () => {
    const base = readStyle('base.css')
    const block = base.match(/@media\s*\(\s*pointer:\s*coarse\s*\)\s*\{([\s\S]*?)\n\}/)
    expect(block, 'bloque pointer:coarse').toBeTruthy()
    const inner = block![1]
    expect(inner).toMatch(/:root\s*\{[^}]*--h-sm:\s*44px/s)
    expect(inner).toMatch(/:root\s*\{[^}]*--h-md:\s*44px/s)
  })

  it('ui.css no usa :deep(', () => {
    const ui = readStyle('ui.css')
    expect(ui).not.toMatch(/:deep\(/)
  })

  it('animaciones infinite respetan movimiento suave (data-motion o clase loop)', () => {
    const spinnersOnly = new Set<string>()
    const needsFix: string[] = []
    for (const [key, text] of Object.entries(rawVue)) {
      if (!key.includes('/components/') && !key.includes('/piezas/')) continue
      if (!/animation:[^;]*infinite/.test(text)) continue
      const rel = relPath(key)
      const rules = [...text.matchAll(/([^{}\n]+)\{[^}]*animation:[^;]*infinite[^}]*\}/gs)]
      const decorative = rules.filter((r) => !SPINNER_SELECTOR.test(r[0]))
      if (!decorative.length) {
        spinnersOnly.add(rel)
        continue
      }
      const hasMotion = /data-motion/.test(text)
      const hasLoopClass = /\bloop\b/.test(text)
      if (!hasMotion && !hasLoopClass) needsFix.push(rel)
    }
    expect(needsFix, needsFix.join('\n')).toEqual([])
    expect(spinnersOnly.size).toBeGreaterThan(0) // spinners excluidos explícitamente
  })

  it('S7: text-wrap en títulos y párrafos', () => {
    const base = readStyle('base.css')
    const ui = readStyle('ui.css')
    expect(base).toMatch(/h1,\s*h2,\s*h3[^{]*\{[^}]*text-wrap:\s*balance/s)
    expect(base).toMatch(/\.md h1,[^{]*\{[^}]*text-wrap:\s*balance/s)
    expect(base).toMatch(/\.md p\s*\{[^}]*text-wrap:\s*pretty/s)
    expect(base).toMatch(/(^|\n)p\s*\{[^}]*text-wrap:\s*pretty/s)
    expect(ui).toMatch(/\.sheet-title\s*\{[^}]*text-wrap:\s*balance/s)
  })

  it('S7: escalas --r-*, --t-* y --press-scale definidas', () => {
    const base = readStyle('base.css')
    for (const t of ['--r-xs: 6px', '--r-sm: 8px', '--r-md: 10px', '--r-lg: 14px', '--r-xl: 20px', '--r-pill: 999px', '--press-scale: 0.96']) {
      expect(base).toContain(t)
    }
    for (const t of ['2xs', 'xs', 'sm', 'md', 'lg']) expect(base).toMatch(new RegExp(`--t-${t}:\\s*[0-9.]+px`))
  })

  it('S7: radios y tamaños casi iguales usan tokens', () => {
    const offenders: string[] = []
    const files: Record<string, string> = { ...rawVue, '../styles/ui.css': readStyle('ui.css') }
    for (const [key, text] of Object.entries(files)) {
      const re = /border-radius:\s*(9|10|11|13|14|999)px\s*[;}]|font-size:\s*(10|11|12|13)\.5px/g
      let m: RegExpExecArray | null
      while ((m = re.exec(text))) offenders.push(`${key}:${lineOf(text, m.index)}`)
    }
    expect(offenders, offenders.join('\n')).toEqual([])
  })

  it('S7: .sheet-panel sin border (el anillo viene de --shadow-pop)', () => {
    const ui = readStyle('ui.css')
    const block = ui.match(/\n\.sheet-panel\s*\{([^}]*)\}/)![1]
    expect(block).not.toMatch(/\bborder(-bottom)?\s*:/)
    expect(readStyle('base.css')).toMatch(/--shadow-pop:[^;]*0 0 0 1px/)
  })

  it('S7: content-visibility en listas largas', () => {
    const cambios = Object.entries(rawVue).find(([k]) => k.endsWith('/CambiosView.vue'))![1]
    expect(cambios).not.toMatch(/content-visibility/)
    const chat = Object.entries(rawVue).find(([k]) => k.endsWith('/SessionChatView.vue'))![1]
    expect(chat, 'los mensajes del chat no usan content-visibility (saltos al subir)').not.toMatch(/content-visibility|contain-intrinsic-size/)
    const bib = Object.entries(rawVue).find(([k]) => k.endsWith('/BibliotecaView.vue'))![1]
    expect(bib).toMatch(/content-visibility:\s*auto/)
    expect(bib).toMatch(/contain-intrinsic-size:\s*auto\s+\d+px/)
  })

  it('S7: cross-fade de íconos (clases icon-swap-*)', () => {
    const ui = readStyle('ui.css')
    expect(ui).toMatch(/\.icon-swap-enter-active/)
    expect(ui).toMatch(/\.icon-swap-leave-active/)
    expect(ui).toMatch(/\.icon-swap-enter-from/)
    expect(ui).toMatch(/scale:\s*0\.25/)
    for (const f of ['LoginScreen', 'DiagramaCard', 'MrDetail']) {
      const t = Object.entries(rawVue).find(([k]) => k.endsWith(`/${f}.vue`))![1]
      expect(t, f).toMatch(/<Transition name="icon-swap" mode="out-in"/)
    }
  })

  it('S7: borde de imágenes con --img-outline en ambos temas', () => {
    const base = readStyle('base.css')
    expect(base).toMatch(/--img-outline:\s*oklch\(1 0 0 \/ 0\.1\)/)
    expect(base).toMatch(/--img-outline:\s*oklch\(0 0 0 \/ 0\.1\)/)
    for (const f of ['BibCard', 'BibImage', 'ChatFotos', 'AttachThumbs']) {
      const t = Object.entries(rawVue).find(([k]) => k.endsWith(`/${f}.vue`))![1]
      expect(t, f).toMatch(/outline:\s*1px solid var\(--img-outline\)/)
    }
  })
})
