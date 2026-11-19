import { describe, expect, it } from 'vitest'
import src from './MrCreateSheet.vue?raw'

describe('MrCreateSheet errores en el lugar', () => {
  it('muestra error en el panel con role="alert"', () => {
    expect(src).toMatch(/role="alert"/)
    expect(src).not.toMatch(/\btoast\b/)
  })
})
