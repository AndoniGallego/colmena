import { describe, expect, it } from 'vitest'
import { mobilePageIndex, mobilePageOrder } from './mobileSections'

describe('mobilePageOrder', () => {
  it('incluye MRs cuando están habilitados, sin pestaña de chat', () => {
    expect(mobilePageOrder(true)).toEqual(['board', 'mrs', 'notas', 'biblioteca'])
    expect(mobilePageOrder(true, [])).toEqual(['board', 'mrs', 'notas', 'biblioteca'])
  })

  it('saca MRs cuando están apagados', () => {
    expect(mobilePageOrder(false)).toEqual(['board', 'notas', 'biblioteca'])
    expect(mobilePageOrder(false)).not.toContain('mrs')
  })

  it('las secciones de piezas van después de MRs y antes de Notas', () => {
    expect(mobilePageOrder(true, [{ id: 'demo' }])).toEqual(['board', 'mrs', 'demo', 'notas', 'biblioteca'])
    expect(mobilePageOrder(false, [{ id: 'demo' }, { id: 'otra' }])).toEqual(['board', 'demo', 'otra', 'notas', 'biblioteca'])
  })

  it('índice coherente con el orden', () => {
    const sinMrs = mobilePageOrder(false, [{ id: 'demo' }])
    expect(mobilePageIndex(sinMrs, 'demo')).toBe(1)
    expect(mobilePageIndex(sinMrs, 'notas')).toBe(2)
    expect(mobilePageIndex(sinMrs, 'mrs')).toBe(0)
  })
})
