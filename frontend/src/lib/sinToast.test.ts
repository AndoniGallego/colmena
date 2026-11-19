import { describe, expect, it } from 'vitest'

const fuentes = import.meta.glob('../**/*.{ts,vue}', { eager: true, import: 'default', query: '?raw' }) as Record<string, string>

describe('sin lib/toast en el código', () => {
  it('no queda import de lib/toast', () => {
    const hits = Object.entries(fuentes)
      .filter(([f]) => !f.includes('sinToast.test'))
      .filter(([, src]) => src.includes("lib/toast"))
    expect(hits).toEqual([])
  })

  it('no queda toast( en fuentes', () => {
    const hits = Object.entries(fuentes)
      .filter(([f]) => !f.includes('sinToast.test'))
      .filter(([, src]) => /\btoast\s*\(/.test(src))
    expect(hits).toEqual([])
  })
})
