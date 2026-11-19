import { describe, expect, it } from 'vitest'
import casos from './opciones.casos.json'
import { toOpciones, type Opciones } from './opciones'
import { questionsOf, signature } from './stepper'

describe('casos compartidos con el servidor', () => {
  for (const c of casos.to_opciones) it(`toOpciones: ${c.nombre}`, () => expect(toOpciones(c.entrada)).toEqual(c.salida))
  for (const c of casos.texto) it(`tarjetas: ${c.nombre}`, () => expect(questionsOf(c.texto)).toEqual(c.preguntas))
  for (const c of casos.firma) it(`firma: ${c.id}`, () => expect(signature(c.id, c.preguntas as Opciones[])).toBe(c.sig))
})
