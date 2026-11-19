import { beforeEach, describe, expect, it } from 'vitest'
import { answerForCard } from './opciones'
import {
  advance,
  allAnswered,
  answer,
  answerLine,
  back,
  buildReply,
  canNext,
  clearProgreso,
  goTo,
  initial,
  isSummary,
  loadProgreso,
  minLabel,
  next,
  pendientes,
  pendingLabel,
  restore,
  saveProgreso,
  signature,
  stepperKey,
  type MsgLite,
} from './stepper'

const block = (json: unknown) => '```opciones\n' + JSON.stringify(json) + '\n```'
const QA = { pregunta: '¿Cómo lo recorro?', opciones: [{ label: 'Todo junto' }, { label: 'Paso por paso siempre', recomendada: true }] }
const QB = { pregunta: '¿Y el aviso?', opciones: [{ label: 'Solo en la app' }, { label: 'También manda aviso al celu' }] }
const QC = { pregunta: '¿Cuánto dura?', opciones: [{ label: 'Nunca' }, { label: 'Una semana' }, { label: 'Lo mismo que Limpiar (1 día)' }] }
const multi = `Necesito tres cosas.\n\n${block(QA)}\n\n${block(QB)}\n\n${block(QC)}\n\nGracias.`
const msg = (id: string, assistant: boolean, text: string): MsgLite => ({ id, assistant, text })

const qs = pendientes([msg('a1', true, multi)])!.questions

describe('pendientes', () => {
  it('finds every option block of the last assistant message', () => {
    const p = pendientes([msg('u1', false, 'hola'), msg('a1', true, multi)])
    expect(p?.questions.map((q) => q.pregunta)).toEqual(['¿Cómo lo recorro?', '¿Y el aviso?', '¿Cuánto dura?'])
    expect(p?.sig).toBe(signature('a1', p!.questions))
  })

  it('is empty once the user wrote after the questions', () => {
    expect(pendientes([msg('a1', true, multi), msg('u1', false, '1. Todo junto')])).toBeNull()
  })

  it('is empty while a reply is on its way', () => {
    expect(pendientes([msg('a1', true, multi)], true)).toBeNull()
  })

  it('ignores older questions when the last assistant message has none', () => {
    expect(pendientes([msg('a1', true, multi), msg('a2', true, 'Listo, sigo.')])).toBeNull()
  })

  it('ignores assistant messages without options and empty chats', () => {
    expect(pendientes([msg('a1', true, 'Nada para elegir')])).toBeNull()
    expect(pendientes([])).toBeNull()
  })

  it('changes signature when the message or its questions change', () => {
    expect(signature('a1', qs)).not.toBe(signature('a2', qs))
    expect(signature('a1', qs)).not.toBe(signature('a1', qs.slice(1)))
  })
})

describe('buildReply', () => {
  it('joins one numbered line per question, in order', () => {
    const answers = [{ kind: 'opcion', i: 1 }, { kind: 'opcion', i: 1 }, { kind: 'opcion', i: 2 }] as const
    expect(buildReply(qs, [...answers])).toBe('2. Paso por paso siempre\n2. También manda aviso al celu\n3. Lo mismo que Limpiar (1 día)')
  })

  it('splits back per card so the cards in the message read as answered', () => {
    const reply = buildReply(qs, [{ kind: 'opcion', i: 0 }, { kind: 'opcion', i: 1 }, { kind: 'opcion', i: 2 }])!
    expect(qs.map((q, k) => answerForCard(q.opciones, reply, k, qs.length))).toEqual(['1. Todo junto', '2. También manda aviso al celu', '3. Lo mismo que Limpiar (1 día)'])
  })

  it('uses free text as is, folded to one line', () => {
    expect(buildReply(qs, [{ kind: 'texto', text: '  depende\n del día ' }, { kind: 'opcion', i: 0 }, { kind: 'opcion', i: 0 }])).toBe('depende del día\n1. Solo en la app\n1. Nunca')
  })

  it('is null while something is missing or blank', () => {
    expect(buildReply(qs, [{ kind: 'opcion', i: 0 }, null, { kind: 'opcion', i: 0 }])).toBeNull()
    expect(buildReply(qs, [{ kind: 'texto', text: '   ' }, { kind: 'opcion', i: 0 }, { kind: 'opcion', i: 0 }])).toBeNull()
  })

  it('a single question is a single line', () => {
    expect(buildReply([QC as never], [{ kind: 'opcion', i: 1 }])).toBe('2. Una semana')
    expect(answerLine(qs[0], { kind: 'opcion', i: 9 })).toBe('')
  })
})

describe('navigation', () => {
  it('answers, advances to the next open question and ends in the summary', () => {
    let s = initial(3)
    expect(canNext(qs, s)).toBe(false)
    s = advance(qs, answer(qs, s, { kind: 'opcion', i: 1 }))
    expect(s.step).toBe(1)
    s = advance(qs, answer(qs, s, { kind: 'opcion', i: 0 }))
    s = advance(qs, answer(qs, s, { kind: 'opcion', i: 2 }))
    expect(isSummary(3, s)).toBe(true)
    expect(allAnswered(qs, s)).toBe(true)
  })

  it('editing from the summary goes back to it', () => {
    let s = { step: 3, answers: [{ kind: 'opcion', i: 0 }, { kind: 'opcion', i: 0 }, { kind: 'opcion', i: 0 }] } as ReturnType<typeof initial>
    s = goTo(qs, s, 0)
    expect(s.step).toBe(0)
    s = advance(qs, answer(qs, s, { kind: 'opcion', i: 1 }))
    expect(s.step).toBe(3)
  })

  it('skips to a question left open', () => {
    let s = { step: 0, answers: [null, null, { kind: 'opcion', i: 0 }] } as ReturnType<typeof initial>
    s = advance(qs, answer(qs, s, { kind: 'opcion', i: 0 }))
    expect(s.step).toBe(1)
    s = advance(qs, answer(qs, s, { kind: 'opcion', i: 0 }))
    expect(s.step).toBe(3)
  })

  it('next needs an answer; back stops at the first question', () => {
    let s = initial(3)
    expect(next(qs, s)).toBe(s)
    s = answer(qs, s, { kind: 'texto', text: 'otra cosa' })
    s = next(qs, s)
    expect(s.step).toBe(1)
    s = back(back(s))
    expect(s.step).toBe(0)
  })

  it('goTo only reaches questions already visited or the first open one', () => {
    const s = initial(3)
    expect(goTo(qs, s, 2).step).toBe(0)
    expect(goTo(qs, s, 3).step).toBe(0)
    const s1 = answer(qs, s, { kind: 'opcion', i: 0 })
    expect(goTo(qs, s1, 1).step).toBe(1)
  })

  it('one question has no summary step', () => {
    const one = [qs[0]]
    const s = advance(one, answer(one, initial(1), { kind: 'opcion', i: 0 }))
    expect(s.step).toBe(0)
    expect(isSummary(1, s)).toBe(false)
    expect(next(one, s)).toBe(s)
  })
})

describe('restore', () => {
  const sig = signature('a1', qs)

  it('brings back progress for the same questions', () => {
    const r = restore(qs, sig, { sig, step: 1, answers: [{ kind: 'opcion', i: 1 }, null, null], dismissed: true, at: 1 })
    expect(r.state).toEqual({ step: 1, answers: [{ kind: 'opcion', i: 1 }, null, null] })
    expect(r.dismissed).toBe(true)
  })

  it('starts over for other questions or broken data', () => {
    expect(restore(qs, sig, { sig: 'otra', step: 2, answers: [null, null, null], dismissed: true, at: 1 })).toEqual({ state: initial(3), dismissed: false, minimizado: false })
    expect(restore(qs, sig, null).state).toEqual(initial(3))
    const r = restore(qs, sig, { sig, step: 3, answers: [{ kind: 'opcion', i: 7 }, { kind: 'raro' } as never, null], dismissed: false, at: 1 })
    expect(r.state).toEqual({ step: 0, answers: [null, null, null] })
  })
})

describe('stepperKey', () => {
  it('maps numbers, Enter, arrows, Backspace and Escape', () => {
    expect(stepperKey({ key: '3' }, false)).toEqual({ type: 'pick', i: 2 })
    expect(stepperKey({ key: '7' }, false)).toBeNull()
    expect(stepperKey({ key: 'Enter' }, false)).toEqual({ type: 'enter' })
    expect(stepperKey({ key: 'Enter', shiftKey: true }, false)).toBeNull()
    expect(stepperKey({ key: 'ArrowLeft' }, false)).toEqual({ type: 'back' })
    expect(stepperKey({ key: 'Backspace' }, false)).toEqual({ type: 'back' })
    expect(stepperKey({ key: 'ArrowRight' }, false)).toEqual({ type: 'forward' })
    expect(stepperKey({ key: 'Escape' }, false)).toEqual({ type: 'escape' })
  })

  it('leaves typing alone except Enter and Escape', () => {
    expect(stepperKey({ key: '2' }, true)).toBeNull()
    expect(stepperKey({ key: 'Backspace' }, true)).toBeNull()
    expect(stepperKey({ key: 'Enter' }, true)).toEqual({ type: 'enter' })
    expect(stepperKey({ key: 'Escape' }, true)).toEqual({ type: 'escape' })
    expect(stepperKey({ key: '1', ctrlKey: true }, false)).toBeNull()
    expect(stepperKey({ key: 'Enter', isComposing: true }, true)).toBeNull()
  })
})

describe('persistence', () => {
  beforeEach(() => clearProgreso('chat'))

  it('saves and loads per chat, and clears', () => {
    expect(loadProgreso('chat')).toBeNull()
    saveProgreso('chat', { sig: 's', step: 1, answers: [null], dismissed: false })
    expect(loadProgreso('chat')).toMatchObject({ sig: 's', step: 1 })
    expect(loadProgreso('otro')).toBeNull()
    clearProgreso('chat')
    expect(loadProgreso('chat')).toBeNull()
  })

  it('labels the pending chip', () => {
    expect(pendingLabel(1)).toBe('1 pregunta pendiente')
    expect(pendingLabel(3)).toBe('3 preguntas pendientes')
  })
})

describe('minimizar', () => {
  const qs = pendientes([{ id: 'm', assistant: true, text: multi }])!.questions
  const sig = signature('m', qs)

  it('m minimiza solo si no se esta escribiendo, sin modificadores', () => {
    expect(stepperKey({ key: 'm' }, false)).toEqual({ type: 'minimize' })
    expect(stepperKey({ key: 'M' }, false)).toEqual({ type: 'minimize' })
    expect(stepperKey({ key: 'm' }, true)).toBeNull()
    expect(stepperKey({ key: 'm', ctrlKey: true }, false)).toBeNull()
    expect(stepperKey({ key: 'm', metaKey: true }, false)).toBeNull()
  })

  it('la etiqueta dice cuantas preguntas hay y en cual vas', () => {
    expect(minLabel(qs, { step: 1, answers: [{ kind: 'opcion', i: 0 }, null, null] })).toBe('Preguntas · 2 de 3 · tocá para seguir')
    expect(minLabel(qs, { step: 3, answers: [] })).toContain('3 de 3')
    expect(minLabel(qs.slice(0, 1), initial(1))).toContain('responder')
  })

  it('persiste minimizado con las respuestas y el paso, y lo restaura', () => {
    const state = { step: 1, answers: [{ kind: 'opcion', i: 1 } as const, null, null] }
    saveProgreso('chat', { sig, step: state.step, answers: state.answers, dismissed: true, minimizado: true })
    const r = restore(qs, sig, loadProgreso('chat'))
    expect(r.minimizado).toBe(true)
    expect(r.dismissed).toBe(true)
    expect(r.state).toEqual(state)
  })

  it('un set nuevo de preguntas (otra sig) se expande solo', () => {
    const saved = { sig, step: 1, answers: [null, null, null], dismissed: true, minimizado: true, at: 1 }
    const r = restore(qs, signature('otro', qs), saved)
    expect(r.minimizado).toBe(false)
    expect(r.dismissed).toBe(false)
    expect(r.state).toEqual(initial(3))
  })

  it('un guardado viejo sin minimizado sigue funcionando', () => {
    const r = restore(qs, sig, { sig, step: 0, answers: [null, null, null], dismissed: true, at: 1 })
    expect(r).toMatchObject({ dismissed: true, minimizado: false })
  })
})
