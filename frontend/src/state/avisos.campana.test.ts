import { describe, expect, it } from 'vitest'
import src from './avisos.ts?raw'

describe('avisos sin toast al llegar uno nuevo', () => {
  it('state/avisos.ts no importa toast', () => {
    expect(src).not.toMatch(/\btoast\b/)
  })
})
