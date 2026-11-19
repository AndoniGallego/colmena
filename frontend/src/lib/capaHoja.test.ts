import { describe, expect, it } from 'vitest'
import { estiloHoja } from './capaHoja'

describe('estiloHoja', () => {
  it('sin capa ni teclado no fija estilo', () => {
    expect(estiloHoja(undefined, undefined)).toBeUndefined()
  })
  it('con capa pone el z-index para quedar encima del visor', () => {
    expect(estiloHoja(undefined, 95)).toEqual({ zIndex: '95' })
  })
  it('combina la capa con el alto del teclado del celu', () => {
    expect(estiloHoja({ height: '300px', top: '10px' }, 95)).toEqual({ height: '300px', top: '10px', zIndex: '95' })
  })
})
