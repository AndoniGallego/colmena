import { describe, expect, it } from 'vitest'
import { gridLayout, overlayExtra, stepIndex } from './chatFotos'

describe('gridLayout', () => {
  it('1 foto ocupa sola', () => {
    expect(gridLayout(1)).toEqual([{ index: 0 }])
  })
  it('2 fotos en dos columnas', () => {
    expect(gridLayout(2).map((c) => c.index)).toEqual([0, 1])
  })
  it('3 fotos con una grande', () => {
    expect(gridLayout(3)).toEqual([{ index: 0, span: 'large' }, { index: 1 }, { index: 2 }])
  })
  it('4 fotos en grilla 2x2', () => {
    expect(gridLayout(4).length).toBe(4)
  })
})

describe('overlayExtra', () => {
  it('sin overlay hasta 4', () => {
    expect(overlayExtra(4)).toBe(0)
    expect(overlayExtra(7)).toBe(4)
  })
})

describe('stepIndex', () => {
  it('respeta bordes', () => {
    expect(stepIndex(0, -1, 5)).toBe(0)
    expect(stepIndex(4, 1, 5)).toBe(4)
    expect(stepIndex(2, 1, 5)).toBe(3)
  })
})
