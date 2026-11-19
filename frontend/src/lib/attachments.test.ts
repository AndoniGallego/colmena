import { describe, expect, it } from 'vitest'
import { attachmentLabel, checkFile, formatSize, kindFromId, kindOf, MAX_BYTES, splitAttachments } from './attachments'

describe('kindOf', () => {
  it('classifies by extension', () => {
    expect(kindOf('Foto.PNG')).toBe('image')
    expect(kindOf('a.pdf')).toBe('pdf')
    expect(kindOf('notas.md')).toBe('text')
    expect(kindOf('run.sh')).toBeNull()
    expect(kindOf('sinextension')).toBeNull()
  })
})

describe('checkFile', () => {
  it('accepts a normal file', () => {
    expect(checkFile({ name: 'a.png', size: 10 }, 0)).toBeNull()
  })
  it('rejects by count, type, emptiness and size', () => {
    expect(checkFile({ name: 'a.png', size: 10 }, 5)).toMatch(/Máximo 5/)
    expect(checkFile({ name: 'a.exe', size: 10 }, 0)).toMatch(/Solo imágenes/)
    expect(checkFile({ name: 'a.png', size: 0 }, 0)).toMatch(/vacío/)
    expect(checkFile({ name: 'a.png', size: MAX_BYTES + 1 }, 0)).toMatch(/20 MB/)
  })
})

describe('formatSize', () => {
  it('uses the closest unit', () => {
    expect(formatSize(900)).toBe('900 B')
    expect(formatSize(2048)).toBe('2 KB')
    expect(formatSize(3 * 1024 * 1024)).toBe('3 MB')
    expect(formatSize(1.5 * 1024 * 1024)).toBe('1.5 MB')
  })
})

describe('splitAttachments', () => {
  const id = '20261031-101500-error-checkout.png'
  it('lifts wrapped paths out of the text', () => {
    const r = splitAttachments(`Mirá esto (Adjunto: /home/usuario/x/uploads/${id})`)
    expect(r).toEqual({ text: 'Mirá esto', ids: [id], images: 0 })
  })
  it('handles several attachments', () => {
    const b = '20261031-101501-log.txt'
    const r = splitAttachments(`Dos (Adjunto: /u/${id}) (Adjunto: /u/${b})`)
    expect(r.ids).toEqual([id, b])
    expect(r.text).toBe('Dos')
  })
  it('handles the wording used when there is no text', () => {
    const b = '20261031-101501-log.txt'
    const r = splitAttachments(`Te paso /u/${id}, /u/${b}`)
    expect(r.ids).toEqual([id, b])
    expect(r.text).toBe('')
  })
  it('counts inline image markers', () => {
    expect(splitAttachments('Hola\n[imagen]\n[imagen]')).toEqual({ text: 'Hola', ids: [], images: 2 })
  })
  it('leaves ordinary text and unrelated paths alone', () => {
    expect(splitAttachments('Mirá /etc/passwd (Adjunto: nada)').ids).toEqual([])
    expect(splitAttachments('Te paso la posta').text).toBe('Te paso la posta')
  })
})

describe('ids', () => {
  it('derives kind and label', () => {
    expect(kindFromId('20261031-101500-foto.jpg')).toBe('image')
    expect(attachmentLabel('20261031-101500-foto.jpg')).toBe('foto.jpg')
  })
})
