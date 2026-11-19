import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { instalarCopiaCodigo, textoACopiar } from './codeCopy'

describe('textoACopiar', () => {
  it('devuelve solo el contenido del code, sin la etiqueta de lenguaje', () => {
    const pre = {
      querySelector: (sel: string) => (sel === 'code' ? { textContent: 'echo hi\n' } : null),
    } as unknown as HTMLElement
    expect(textoACopiar(pre)).toBe('echo hi\n')
  })
})

describe('instalarCopiaCodigo', () => {
  const copyText = vi.fn(async () => true)
  let doc: Document
  let desinstalar: () => void

  beforeEach(() => {
    vi.useFakeTimers()
    copyText.mockClear()
    doc = {
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as unknown as Document
  })

  afterEach(() => {
    desinstalar?.()
    vi.useRealTimers()
  })

  function armarDom(type: 'md-copy' | 'outside') {
    const classes = new Set<string>()
    const btn = {
      type: 'button',
      classList: {
        add: (c: string) => classes.add(c),
        remove: (c: string) => classes.delete(c),
        contains: (c: string) => classes.has(c),
      },
      setAttribute: vi.fn(),
      getAttribute: vi.fn(() => 'Copiar código'),
      closest(sel: string) {
        if (sel === '.md-copy') return btn
        if (sel === 'pre.md-code') return pre
        return null
      },
    }
    const pre = {
      className: 'md-code',
      querySelector: (sel: string) => (sel === 'code' ? { textContent: 'echo hi' } : null),
      closest(sel: string) {
        return sel === 'pre.md-code' ? pre : null
      },
    }

    const target = type === 'md-copy' ? btn : pre
    const event = {
      target,
      stopPropagation: vi.fn(),
    } as unknown as Event

    const add = doc.addEventListener as ReturnType<typeof vi.fn>
    const handler = add.mock.calls[0][1] as (e: Event) => void
    void handler(event)
    return { btn, event, pre, classes }
  }

  it('registra un listener de click en el documento', () => {
    desinstalar = instalarCopiaCodigo(doc, { copyText })
    expect(doc.addEventListener).toHaveBeenCalledWith('click', expect.any(Function))
  })

  it('click en .md-copy copia el code, marca copiado y lo revierte a los 1.8s', async () => {
    desinstalar = instalarCopiaCodigo(doc, { copyText })
    const { btn, event } = armarDom('md-copy')

    await vi.waitFor(() => expect(copyText).toHaveBeenCalledWith('echo hi'))
    expect(event.stopPropagation).toHaveBeenCalled()
    expect(btn.classList.contains('copiado')).toBe(true)
    expect(btn.setAttribute).toHaveBeenCalledWith('aria-label', 'Copiado')

    vi.advanceTimersByTime(1800)
    expect(btn.classList.contains('copiado')).toBe(false)
    expect(btn.setAttribute).toHaveBeenCalledWith('aria-label', 'Copiar código')
  })

  it('click fuera de .md-copy no copia', () => {
    desinstalar = instalarCopiaCodigo(doc, { copyText })
    armarDom('outside')
    expect(copyText).not.toHaveBeenCalled()
  })

  it('desinstalar quita el listener', () => {
    desinstalar = instalarCopiaCodigo(doc, { copyText })
    const add = doc.addEventListener as ReturnType<typeof vi.fn>
    const handler = add.mock.calls[0][1]
    desinstalar()
    expect(doc.removeEventListener).toHaveBeenCalledWith('click', handler)
  })
})
