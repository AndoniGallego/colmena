import { describe, expect, it } from 'vitest'
import { autosizeArea } from './autosize'

function fake(content: number, boxH = 90) {
  const log: string[] = []
  const box = { offsetHeight: boxH, style: { minHeight: '' } }
  const style = { height: '', minHeight: '400px' }
  const el = {
    style,
    parentElement: box,
    get scrollHeight() {
      log.push(`medir con contenedor min=${box.style.minHeight || 'libre'}, alto=${style.height}, min propio=${style.minHeight || 'css'}`)
      return content
    },
  }
  return { el, box, log }
}

describe('autosizeArea', () => {
  it('mide con el contenedor fijado a su alto, así el chat de arriba no se estira ni pierde el fondo', () => {
    const { el, box, log } = fake(140)
    autosizeArea(el, 200)
    expect(log).toEqual(['medir con contenedor min=90px, alto=0px, min propio=css'])
    expect(el.style.minHeight).toBe('140px')
    expect(el.style.height).toBe('')
    expect(box.style.minHeight).toBe('')
  })
  it('respeta el máximo', () => {
    const { el } = fake(900)
    autosizeArea(el, 200)
    expect(el.style.minHeight).toBe('200px')
  })
  it('sin contenedor igual ajusta', () => {
    const { el } = fake(80)
    autosizeArea({ ...el, scrollHeight: 80, parentElement: null }, 200)
    expect(el.style.minHeight).toBe('80px')
  })
})
