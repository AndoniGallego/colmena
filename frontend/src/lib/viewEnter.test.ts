import { describe, expect, it, vi } from 'vitest'
import { animateViewEnter, viewEnterPreset } from './viewEnter'

describe('viewEnterPreset', () => {
  it('returns null when soft motion', () => {
    expect(viewEnterPreset(true)).toBeNull()
  })
  it('returns defaults when full motion', () => {
    expect(viewEnterPreset(false)).toMatchObject({ y: 12, duration: 0.45 })
  })
})

describe('animateViewEnter', () => {
  it('skips gsap when soft', () => {
    const from = vi.fn()
    const gsap = { from, fromTo: from, killTweensOf: vi.fn() } as never
    const run = <T>(fn: () => T) => fn()
    animateViewEnter(gsap, run, [{ tagName: 'DIV' } as Element], true)
    expect(from).not.toHaveBeenCalled()
  })

  it('skips gsap when no targets', () => {
    const from = vi.fn()
    const gsap = { from, fromTo: from, killTweensOf: vi.fn() } as never
    const run = <T>(fn: () => T) => fn()
    animateViewEnter(gsap, run, [], false)
    expect(from).not.toHaveBeenCalled()
  })

  it('animates to visible explicitly so a repeated entrance never ends invisible', () => {
    const fromTo = vi.fn()
    const killTweensOf = vi.fn()
    const gsap = { fromTo, killTweensOf } as never
    const run = <T>(fn: () => T) => fn()
    const el = { tagName: 'DIV' } as Element
    animateViewEnter(gsap, run, [el], false)
    expect(killTweensOf).toHaveBeenCalledWith([el])
    expect(fromTo).toHaveBeenCalledWith(
      [el],
      expect.objectContaining({ opacity: 0 }),
      expect.objectContaining({ opacity: 1, y: 0, clearProps: 'transform,opacity' }),
    )
  })
})
