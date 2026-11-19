// @ts-nocheck
export const ASSETS_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000

export type CachedAsset = { url: string; cachedAt: number }

function htmlValid(html: string): boolean {
  const t = html.trim()
  if (!t) return false
  return /<!DOCTYPE\s+html/i.test(t) || /<\s*html[\s>]/i.test(t)
}

export function extractReferencedAssets(html: string): string[]
export function extractReferencedAssets(html) {
  const out = new Set()
  const re = /\/assets\/[^"'\s>)]+/g
  let m
  while ((m = re.exec(html))) out.add(m[0])
  return [...out]
}

export function assetsToEvict(html: string, cached: CachedAsset[], nowMs: number, maxAgeMs?: number): string[]
export function assetsToEvict(html, cached, nowMs, maxAgeMs = ASSETS_MAX_AGE_MS) {
  if (!htmlValid(html)) return []
  const ref = new Set(extractReferencedAssets(html))
  const drop = []
  for (const { url, cachedAt } of cached) {
    if (!url.startsWith('/assets/')) continue
    if (ref.has(url)) continue
    if (nowMs - cachedAt > maxAgeMs) drop.push(url)
  }
  return drop
}
