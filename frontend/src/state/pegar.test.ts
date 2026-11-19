import { describe, expect, it, vi } from 'vitest'
import { useFileIntake } from './pegar'

const png = () => new File([new Uint8Array([1, 2])], 'image.png', { type: 'image/png' })
const transfer = (files: File[], text = '') => ({
  types: [...(files.length ? ['Files'] : []), ...(text ? ['text/plain'] : [])],
  items: [...files.map((f) => ({ kind: 'file', getAsFile: () => f })), ...(text ? [{ kind: 'string', getAsFile: () => null }] : [])],
  files,
  getData: (t: string) => (t === 'text/plain' ? text : ''),
  dropEffect: 'none',
})
type Ev = ClipboardEvent & DragEvent & { preventDefault: ReturnType<typeof vi.fn> }
const ev = (dt: unknown, key: 'clipboardData' | 'dataTransfer' = 'clipboardData') =>
  ({ [key]: dt, preventDefault: vi.fn() }) as unknown as Ev

describe('useFileIntake: pegar', () => {
  it('solo imagen: se adjunta y no se pega nada en el texto', () => {
    const add = vi.fn()
    const e = ev(transfer([png()]))
    useFileIntake(add, () => false).onPaste(e)
    expect(add).toHaveBeenCalledTimes(1)
    expect(add.mock.calls[0][0][0].name).toMatch(/^captura-\d{8}-\d{6}\.png$/)
    expect(e.preventDefault).toHaveBeenCalled()
  })
  it('texto e imagen: el texto se pega normal y la imagen se adjunta', () => {
    const add = vi.fn()
    const e = ev(transfer([png()], 'hola'))
    useFileIntake(add, () => false).onPaste(e)
    expect(add).toHaveBeenCalledTimes(1)
    expect(e.preventDefault).not.toHaveBeenCalled()
  })
  it('solo texto: no toca nada', () => {
    const add = vi.fn()
    const e = ev(transfer([], 'hola'))
    useFileIntake(add, () => false).onPaste(e)
    expect(add).not.toHaveBeenCalled()
    expect(e.preventDefault).not.toHaveBeenCalled()
  })
  it('deshabilitado (esperando aprobación): no adjunta', () => {
    const add = vi.fn()
    useFileIntake(add, () => true).onPaste(ev(transfer([png()])))
    expect(add).not.toHaveBeenCalled()
  })
})

describe('useFileIntake: arrastrar', () => {
  it('entrar muestra el overlay, salir de hijos no lo apaga, soltar adjunta', () => {
    const add = vi.fn()
    const i = useFileIntake(add, () => false)
    const dt = transfer([png()])
    i.onDragEnter(ev(dt, 'dataTransfer'))
    i.onDragEnter(ev(dt, 'dataTransfer'))
    i.onDragLeave()
    expect(i.dragging.value).toBe(true)
    const over = ev(dt, 'dataTransfer')
    i.onDragOver(over)
    expect(over.preventDefault).toHaveBeenCalled()
    const drop = ev(dt, 'dataTransfer')
    i.onDrop(drop)
    expect(drop.preventDefault).toHaveBeenCalled()
    expect(i.dragging.value).toBe(false)
    expect(add).toHaveBeenCalledTimes(1)
  })
  it('salir del todo apaga el overlay', () => {
    const i = useFileIntake(vi.fn(), () => false)
    i.onDragEnter(ev(transfer([png()]), 'dataTransfer'))
    i.onDragLeave()
    expect(i.dragging.value).toBe(false)
  })
  it('arrastrar texto no es un adjunto', () => {
    const i = useFileIntake(vi.fn(), () => false)
    const e = ev(transfer([], 'hola'), 'dataTransfer')
    i.onDragEnter(e)
    expect(i.dragging.value).toBe(false)
    expect(e.preventDefault).not.toHaveBeenCalled()
  })
})
