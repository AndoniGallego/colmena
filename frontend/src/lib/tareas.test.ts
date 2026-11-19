import { describe, expect, it } from 'vitest'
import { MAX_PEDIDO, armarCuerpoPrograma, cuandoTexto, estadoCorrida, proximaTexto, validarPrograma, type FormPrograma } from './tareas'

const base: FormPrograma = { nombre: 'Revisar MRs', repo: '/r/a', pedido: 'Mirá los MRs abiertos', agente: 'claude', modelo: '', tipo: 'diaria', hora: '09:00', dias: [], dia: 1 }

describe('lib/tareas', () => {
  it('cuandoTexto cubre diaria, días y semanal', () => {
    expect(cuandoTexto({ tipo: 'diaria', hora: '09:00' })).toBe('Todos los días a las 09:00')
    expect(cuandoTexto({ tipo: 'dias', hora: '08:30', dias: [4, 0, 2] })).toBe('Lun, Mié y Vie a las 08:30')
    expect(cuandoTexto({ tipo: 'dias', hora: '08:30', dias: [0] })).toBe('Lun a las 08:30')
    expect(cuandoTexto({ tipo: 'semanal', hora: '18:00', dia: 4 })).toBe('Los viernes a las 18:00')
  })

  it('proximaTexto: pausada, sin fecha y hoy/mañana', () => {
    const ahora = new Date(2026, 10, 17, 10, 0).getTime() / 1000
    expect(proximaTexto(null, ahora)).toBe('Pausada')
    expect(proximaTexto(new Date(2026, 10, 17, 18, 30).getTime() / 1000, ahora)).toBe('Hoy 18:30')
    expect(proximaTexto(new Date(2026, 10, 18, 9, 5).getTime() / 1000, ahora)).toBe('Mañana 09:05')
    expect(proximaTexto(new Date(2026, 10, 20, 9, 5).getTime() / 1000, ahora)).toMatch(/^Vie 20\/11 09:05$/)
  })

  it('validarPrograma pide lo mínimo y devuelve un mensaje claro', () => {
    expect(validarPrograma(base, true)).toBe('')
    expect(validarPrograma({ ...base, nombre: '  ' }, true)).toMatch(/nombre/i)
    expect(validarPrograma({ ...base, repo: '' }, true)).toMatch(/repo/i)
    expect(validarPrograma({ ...base, pedido: '' }, true)).toMatch(/pedido/i)
    expect(validarPrograma({ ...base, pedido: 'x'.repeat(MAX_PEDIDO + 1) }, true)).toMatch(/3800/)
    expect(MAX_PEDIDO).toBe(3800)
    expect(validarPrograma({ ...base, pedido: 'x'.repeat(MAX_PEDIDO) }, true)).toBe('')
    expect(validarPrograma({ ...base, hora: '25:00' }, true)).toMatch(/hora/i)
    expect(validarPrograma({ ...base, tipo: 'dias', dias: [] }, true)).toMatch(/día/i)
    expect(validarPrograma({ ...base, agente: 'cursor' }, false)).toMatch(/cursor/i)
    expect(validarPrograma({ ...base, agente: 'cursor', modelo: 'a b' }, true)).toMatch(/modelo/i)
  })

  it('armarCuerpoPrograma manda solo lo que corresponde al tipo y al agente', () => {
    expect(armarCuerpoPrograma(base)).toEqual({ nombre: 'Revisar MRs', repo: '/r/a', pedido: 'Mirá los MRs abiertos', agente: 'claude', modelo: '', cuando: { tipo: 'diaria', hora: '09:00' } })
    expect(armarCuerpoPrograma({ ...base, tipo: 'dias', dias: [4, 0] }).cuando).toEqual({ tipo: 'dias', hora: '09:00', dias: [0, 4] })
    expect(armarCuerpoPrograma({ ...base, tipo: 'semanal', dia: 3 }).cuando).toEqual({ tipo: 'semanal', hora: '09:00', dia: 3 })
    expect(armarCuerpoPrograma({ ...base, modelo: 'gpt-5' }).modelo).toBe('')
    expect(armarCuerpoPrograma({ ...base, agente: 'cursor', modelo: ' gpt-5 ' }).modelo).toBe('gpt-5')
  })

  it('estadoCorrida mapea cada estado a icono y etiqueta', () => {
    expect(estadoCorrida('ok').icono).toBe('check')
    expect(estadoCorrida('fallo').icono).toBe('warn')
    expect(estadoCorrida('salteada').icono).toBe('minus')
    expect(estadoCorrida('en_curso').icono).toBe('clock')
    expect(estadoCorrida('raro').etiqueta).toBe('raro')
  })
})
