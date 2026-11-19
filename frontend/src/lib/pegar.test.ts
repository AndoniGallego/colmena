import { describe, expect, it } from 'vitest'
import { checkFile } from './attachments'
import { carriesFiles, filesFrom, hasText, pastedName, stamp } from './pegar'

const now = new Date(2026, 10, 2, 9, 5, 7)
const png = (name = 'image.png') => new File([new Uint8Array([137, 80, 78, 71])], name, { type: 'image/png' })
const item = (f: File) => ({ kind: 'file', getAsFile: () => f })
const textItem = { kind: 'string', getAsFile: () => null }

describe('pastedName', () => {
  it('stamp con ceros', () => expect(stamp(now)).toBe('20261102-090507'))
  it('captura de Windows ("image.png") pasa a captura con fecha', () => {
    expect(pastedName({ name: 'image.png', type: 'image/png' }, now)).toBe('captura-20261102-090507.png')
  })
  it('sin nombre usa el tipo para la extensión', () => {
    expect(pastedName({ name: '', type: 'image/jpeg' }, now)).toBe('captura-20261102-090507.jpg')
  })
  it('varias capturas a la vez no chocan', () => {
    expect(pastedName({ name: 'image.png', type: 'image/png' }, now, 1)).toBe('captura-20261102-090507-2.png')
  })
  it('un archivo con nombre real se respeta', () => {
    expect(pastedName({ name: 'informe final.pdf', type: 'application/pdf' }, now)).toBe('informe final.pdf')
  })
  it('el nombre generado pasa las mismas validaciones que el clip', () => {
    expect(checkFile({ name: pastedName({ name: 'image.png', type: 'image/png' }, now), size: 10 }, 0)).toBeNull()
  })
})

describe('filesFrom', () => {
  it('toma los archivos de items y renombra solo los genéricos', () => {
    const real = new File(['x'], 'notas.txt', { type: 'text/plain' })
    const out = filesFrom({ types: ['Files'], items: [item(png()), textItem, item(real), item(png())] }, now)
    expect(out.map((f) => f.name)).toEqual(['captura-20261102-090507.png', 'notas.txt', 'captura-20261102-090507-2.png'])
    expect(out[1]).toBe(real)
    expect(out[0].type).toBe('image/png')
    expect(out[0].size).toBe(4)
  })
  it('sin items cae a files (drop)', () => {
    expect(filesFrom({ types: ['Files'], files: [png('foto.png')] }, now).map((f) => f.name)).toEqual(['foto.png'])
  })
  it('solo texto: nada que adjuntar', () => {
    expect(filesFrom({ types: ['text/plain'], items: [textItem] }, now)).toEqual([])
    expect(filesFrom(null)).toEqual([])
  })
})

describe('hasText / carriesFiles', () => {
  it('texto no vacío', () => {
    expect(hasText({ types: ['text/plain', 'Files'], getData: () => 'hola' })).toBe(true)
    expect(hasText({ types: ['text/plain'], getData: () => '' })).toBe(false)
    expect(hasText({ types: ['Files'], getData: () => '' })).toBe(false)
  })
  it('arrastre con archivos', () => {
    expect(carriesFiles({ types: ['Files'] })).toBe(true)
    expect(carriesFiles({ types: ['text/plain'] })).toBe(false)
  })
})
