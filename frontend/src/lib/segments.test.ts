import { describe, expect, it } from 'vitest'
import { replyForCard, chosenIndex, replyText, groupReply } from './opciones'
import { parseSegments, cardCount } from './segments'

const ops = (q: string, ...labels: string[]) => '```opciones\n' + JSON.stringify({ pregunta: q, opciones: labels.map((label) => ({ label })) }) + '\n```'
const pre = (body: object) => '```pregunta\n' + JSON.stringify(body) + '\n```'
const proceso = '```diagrama\n' + JSON.stringify({ titulo: 'T', tipo: 'proceso', pasos: [{ texto: 'Uno' }] }) + '\n```'

describe('parseSegments', () => {
  it('returns plain markdown as one segment', () => {
    expect(parseSegments('hola\n\nmundo')).toEqual([{ type: 'md', text: 'hola\n\nmundo' }])
    expect(parseSegments('')).toEqual([])
  })

  it('keeps every block in order with the text between them', () => {
    const segs = parseSegments(`Antes\n\n${ops('A?', 'x', 'y')}\n\nEntre\n\n${ops('B?', 'z')}\n\n${proceso}\n\nDespués`)
    expect(segs.map((s) => s.type)).toEqual(['md', 'opciones', 'md', 'opciones', 'diagrama', 'md'])
    expect(segs[0]).toEqual({ type: 'md', text: 'Antes' })
    expect(segs[2]).toEqual({ type: 'md', text: 'Entre' })
    expect(segs[5]).toEqual({ type: 'md', text: 'Después' })
    expect(cardCount(segs)).toBe(2)
  })

  it('leaves a broken block as markdown and still parses the next one', () => {
    const segs = parseSegments('```opciones\n{"pregunta": \n```\n\n' + ops('B?', 'z'))
    expect(segs.map((s) => s.type)).toEqual(['md', 'opciones'])
    expect((segs[0] as { text: string }).text).toContain('{"pregunta"')
  })

  it('ignores other fenced code', () => {
    const t = '```php\necho 1;\n```'
    expect(parseSegments(t)).toEqual([{ type: 'md', text: t }])
  })

  it('shows a pending segment for an unclosed fence while streaming', () => {
    const segs = parseSegments(`${ops('A?', 'x')}\n\nSigo\n\`\`\`diagrama\n{"titu`, true)
    expect(segs.map((s) => s.type)).toEqual(['opciones', 'md', 'pending'])
    expect(segs[2]).toEqual({ type: 'pending', kind: 'diagrama' })
  })

  it('accepts an unclosed but complete block once the message is done', () => {
    const segs = parseSegments('```diagrama\n{"tipo":"proceso","pasos":[{"texto":"Uno"}]}')
    expect(segs.map((s) => s.type)).toEqual(['diagrama'])
  })

  it('parsea bloques pregunta con sig', () => {
    const segs = parseSegments(`Antes\n\n${pre({ sig: 'abc', recomendada: 'Sí' })}\n\nDespués`)
    expect(segs.map((s) => s.type)).toEqual(['md', 'pregunta', 'md'])
    expect(segs[1]).toEqual({ type: 'pregunta', data: { sig: 'abc', recomendada: 'Sí' } })
  })

  it('deja pregunta inválida como markdown', () => {
    const t = '```pregunta\n{"nada":1}\n```\n\n' + pre({ sig: 'ok' })
    const segs = parseSegments(t)
    expect(segs.map((s) => s.type)).toEqual(['md', 'pregunta'])
    expect((segs[0] as { text: string }).text).toContain('pregunta')
  })

  it('parsea bloques aviso', () => {
    const av = '```aviso\n' + JSON.stringify({ pane_id: 'w1:p1', tipo: 'fin', titulo: 'Login', texto: 'Listo' }) + '\n```'
    const segs = parseSegments(av)
    expect(segs).toEqual([{ type: 'aviso', data: { pane_id: 'w1:p1', tipo: 'fin', titulo: 'Login', texto: 'Listo' } }])
  })

  it('deja aviso inválido como markdown', () => {
    const t = '```aviso\n{"tipo":"fin"}\n```'
    expect(parseSegments(t)[0].type).toBe('md')
  })
})

describe('grouped replies', () => {
  const a = [{ label: 'Recortarlo', detalle: '', recomendada: false }, { label: 'Sacarlo', detalle: '', recomendada: false }]
  const b = [{ label: 'Sí', detalle: '', recomendada: false }, { label: 'No', detalle: '', recomendada: false }]
  const reply = groupReply([replyText(2, 'Sacarlo'), replyText(1, 'Sí')])

  it('joins one line per card', () => {
    expect(reply).toBe('2. Sacarlo\n1. Sí')
  })

  it('recognizes the choice per card', () => {
    expect(chosenIndex(a, replyForCard(reply, 0, 2))).toBe(1)
    expect(chosenIndex(b, replyForCard(reply, 1, 2))).toBe(0)
  })

  it('does not split a reply that does not match the card count', () => {
    expect(replyForCard('una sola línea', 1, 2)).toBe('una sola línea')
    expect(chosenIndex(a, replyForCard('una sola línea', 0, 2))).toBe(-1)
  })

  it('leaves a single-card reply untouched', () => {
    expect(replyForCard('1. Recortarlo', 0, 1)).toBe('1. Recortarlo')
  })
})
