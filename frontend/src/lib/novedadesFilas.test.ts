import { describe, expect, it } from 'vitest'
import { parseFilasNovedades, parseRefNovedad, quitarRefNovedad } from './novedadesFilas'

describe('novedadesFilas', () => {
  it('parsea pane y session al final de la fila', () => {
    const raw = 'Login pregunta: «¿sigo?» ⟦sesión:w1:p2|sid=abc123⟧'
    expect(parseRefNovedad(raw)).toEqual({ pane_id: 'w1:p2', session_id: 'abc123' })
    expect(quitarRefNovedad(raw)).toBe('Login pregunta: «¿sigo?»')
  })

  it('parseFilasNovedades separa texto y ref', () => {
    const out = parseFilasNovedades(['PS9 terminó: «listo» ⟦sesión:w9:p1|sid=s9⟧', 'sin ref'])
    expect(out[0].texto).toBe('PS9 terminó: «listo»')
    expect(out[0].ref).toEqual({ pane_id: 'w9:p1', session_id: 's9' })
    expect(out[1].ref).toBeNull()
  })
})
