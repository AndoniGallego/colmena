import { describe, expect, it } from 'vitest'
import { answerForCard, chosenIndex, parseOpciones, replyText } from './opciones'

const block = (json: unknown) => '```opciones\n' + (typeof json === 'string' ? json : JSON.stringify(json)) + '\n```'

describe('parseOpciones', () => {
  it('parses a valid block with text around it', () => {
    const p = parseOpciones(
      'Antes\n\n' +
        block({ pregunta: '¿Qué hacemos?', opciones: [{ label: 'Recortarlo', detalle: 'Solo lo último', recomendada: true }, { label: 'Sacarlo' }] }) +
        '\n\nDespués',
    )
    expect(p.before).toBe('Antes')
    expect(p.after).toBe('Después')
    expect(p.opciones).toEqual({
      pregunta: '¿Qué hacemos?',
      opciones: [
        { label: 'Recortarlo', detalle: 'Solo lo último', recomendada: true },
        { label: 'Sacarlo', detalle: '', recomendada: false },
      ],
    })
  })

  it('keeps at most 6 options', () => {
    const opciones = Array.from({ length: 9 }, (_, i) => ({ label: `o${i}` }))
    expect(parseOpciones(block({ pregunta: 'x', opciones })).opciones?.opciones).toHaveLength(6)
  })

  it('clips long fields', () => {
    const o = parseOpciones(block({ pregunta: 'p'.repeat(400), opciones: [{ label: 'l'.repeat(120), detalle: 'd'.repeat(300) }] })).opciones!
    expect(o.pregunta).toHaveLength(300)
    expect(o.opciones[0].label).toHaveLength(80)
    expect(o.opciones[0].detalle).toHaveLength(200)
    expect(o.opciones[0].label.endsWith('…')).toBe(true)
  })

  it('ignores unknown fields and options without label', () => {
    const o = parseOpciones(block({ pregunta: 'x', extra: 1, opciones: [{ label: 'a', foo: 'bar' }, { detalle: 'sin label' }, 'texto'] })).opciones!
    expect(o.opciones).toEqual([{ label: 'a', detalle: '', recomendada: false }])
  })

  it('only a literal true recommends', () => {
    expect(parseOpciones(block({ opciones: [{ label: 'a', recomendada: 'true' }] })).opciones!.opciones[0].recomendada).toBe(false)
  })

  it('falls back to plain text when the JSON is broken or empty', () => {
    const broken = 'Hola\n\n' + block('{"pregunta": ')
    const p = parseOpciones(broken)
    expect(p.opciones).toBeNull()
    expect(p.before).toBe(broken)
    expect(parseOpciones(block({ pregunta: 'x', opciones: [] })).opciones).toBeNull()
    expect(parseOpciones(block({ pregunta: 'x' })).opciones).toBeNull()
  })

  it('reports an unclosed fence while streaming', () => {
    const p = parseOpciones('Mirá\n```opciones\n{"pregu', true)
    expect(p.pending).toBe(true)
    expect(p.before).toBe('Mirá')
  })
})

describe('chosenIndex', () => {
  const ops = [
    { label: 'Recortarlo', detalle: '', recomendada: true },
    { label: 'Sacarlo', detalle: '', recomendada: false },
  ]
  it('matches by numbered prefix and by bare label', () => {
    expect(chosenIndex(ops, replyText(2, 'Sacarlo'))).toBe(1)
    expect(chosenIndex(ops, 'Recortarlo')).toBe(0)
  })
  it('does not match unrelated replies', () => {
    expect(chosenIndex(ops, 'mejor hagamos otra cosa')).toBe(-1)
    expect(chosenIndex(ops, '1. Sacarlo')).toBe(-1)
  })
})

describe('answerForCard', () => {
  const ops = [
    { label: 'Recortarlo', detalle: '', recomendada: true },
    { label: 'Sacarlo', detalle: '', recomendada: false },
  ]
  it('is the reply when it picks one of the options', () => {
    expect(answerForCard(ops, '2. Sacarlo', 0, 1)).toBe('2. Sacarlo')
  })
  it('stays open when the next message is unrelated text', () => {
    expect(answerForCard(ops, 'che, mirá esto otro', 0, 1)).toBeNull()
    expect(answerForCard(ops, null, 0, 1)).toBeNull()
  })
  it('takes the line of each card in a grouped reply', () => {
    const reply = '1. Recortarlo\n2. Sacarlo'
    expect(answerForCard(ops, reply, 0, 2)).toBe('1. Recortarlo')
    expect(answerForCard(ops, reply, 1, 2)).toBe('2. Sacarlo')
  })
  it('stays open when a grouped message is not a reply to the cards', () => {
    expect(answerForCard(ops, 'una línea\notra línea', 0, 2)).toBeNull()
    expect(answerForCard(ops, 'mensaje suelto', 1, 2)).toBeNull()
  })
})
