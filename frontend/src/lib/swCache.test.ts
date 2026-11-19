import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { ASSETS_MAX_AGE_MS, assetsToEvict, extractReferencedAssets, type CachedAsset } from './swCache'

const day = 24 * 60 * 60 * 1000
const now = Date.UTC(2026, 10, 11)

const html = `<!doctype html><html><head>
  <script type="module" crossorigin src="/assets/index-abc.js"></script>
  <link rel="stylesheet" href="/assets/index-def.css">
</head></html>`

function fnBody(src: string, name: string): string {
  const re = new RegExp(`function ${name}\\([^)]*\\)\\s*\\{`)
  const m = re.exec(src)
  if (!m) throw new Error(`missing ${name}`)
  let i = m.index + m[0].length
  let depth = 1
  while (i < src.length && depth) {
    const ch = src[i++]
    if (ch === '{') depth++
    else if (ch === '}') depth--
  }
  return src.slice(m.index, i)
}

const norm = (s: string) => s.replace(/\s+/g, ' ').trim()

describe('extractReferencedAssets', () => {
  it('saca rutas /assets/ del html', () => {
    expect(extractReferencedAssets(html).sort()).toEqual(['/assets/index-abc.js', '/assets/index-def.css'])
  })
})

describe('assetsToEvict', () => {
  const cached: CachedAsset[] = [
    { url: '/assets/index-abc.js', cachedAt: now - 10 * day },
    { url: '/assets/index-def.css', cachedAt: now - 10 * day },
    { url: '/assets/old-chunk.js', cachedAt: now - 10 * day },
    { url: '/assets/recent.js', cachedAt: now - 2 * day },
  ]

  it('no borra assets referenciados en el html', () => {
    const drop = assetsToEvict(html, cached, now)
    expect(drop).not.toContain('/assets/index-abc.js')
    expect(drop).not.toContain('/assets/index-def.css')
  })

  it('borra no referenciados y viejos', () => {
    expect(assetsToEvict(html, cached, now)).toContain('/assets/old-chunk.js')
  })

  it('no borra no referenciados pero recientes', () => {
    expect(assetsToEvict(html, cached, now)).not.toContain('/assets/recent.js')
  })

  it('html vacío no borra nada', () => {
    expect(assetsToEvict('', cached, now)).toEqual([])
    expect(assetsToEvict('   \n', cached, now)).toEqual([])
  })

  it('html inválido no borra nada', () => {
    expect(assetsToEvict('not html at all', cached, now)).toEqual([])
  })

  it('respeta maxAgeMs', () => {
    const one = [{ url: '/assets/x.js', cachedAt: now - ASSETS_MAX_AGE_MS - 1 }]
    expect(assetsToEvict('<html></html>', one, now)).toContain('/assets/x.js')
    const two = [{ url: '/assets/x.js', cachedAt: now - ASSETS_MAX_AGE_MS + 1000 }]
    expect(assetsToEvict('<html></html>', two, now)).toEqual([])
  })
})

describe('sw.js sync', () => {
  it('assetsToEvict coincide con la copia en public/sw.js', () => {
    const ts = readFileSync(new URL('./swCache.ts', import.meta.url).pathname, 'utf8')
    const sw = readFileSync(new URL('../../public/sw.js', import.meta.url).pathname, 'utf8')
    expect(sw).toMatch(/copia de swCache\.ts/)
    expect(norm(fnBody(sw, 'assetsToEvict'))).toBe(norm(fnBody(ts, 'assetsToEvict')))
  })
})
