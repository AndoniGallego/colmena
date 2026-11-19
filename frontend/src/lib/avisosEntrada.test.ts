import { describe, expect, it } from 'vitest'
import { hastaMarcarLeido } from './avisosEntrada'

describe('avisosEntrada', () => {
  it('hastaMarcarLeido usa el máximo id visible', () => {
    expect(hastaMarcarLeido(1, [{ id: 3 }, { id: 2 }])).toBe(3)
    expect(hastaMarcarLeido(5, [{ id: 3 }])).toBe(5)
  })
})
