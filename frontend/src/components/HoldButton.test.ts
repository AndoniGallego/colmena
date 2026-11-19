// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../motion', () => ({ haptic: () => undefined }))

const { default: HoldButton } = await import('./HoldButton.vue')

const ayuda = (ms?: number) =>
  mount(HoldButton, { props: ms === undefined ? {} : { ms } }).find('.hint').text()

describe('HoldButton ayuda', () => {
  it('por defecto dice 1 s', () => {
    expect(ayuda()).toBe('Mantené apretado 1 s')
  })
  it('usa el tiempo que se le pasa', () => {
    expect(ayuda(2000)).toBe('Mantené apretado 2 s')
    expect(ayuda(1500)).toBe('Mantené apretado 1,5 s')
  })
})
