import { describe, expect, it, vi } from 'vitest'
import {
  TECLAS_BARRA,
  mensajeEntrada,
  mensajeTecla,
  formatoVentana,
  debeAbrirPin,
  manejarErrorEscritura,
} from './vivoEscritura'

describe('vivoEscritura', () => {
  it('arma mensajes JSON', () => {
    expect(mensajeEntrada('tok', 'a\r')).toEqual({ tipo: 'entrada', token: 'tok', texto: 'a\r' })
    expect(mensajeTecla('tok', 'esc')).toEqual({ tipo: 'tecla', token: 'tok', tecla: 'esc' })
  })

  it('lista cerrada de teclas de barra', () => {
    expect(TECLAS_BARRA).toContain('ctrl-c')
    expect(TECLAS_BARRA).not.toContain('f1')
  })

  it('formato cuenta regresiva', () => {
    expect(formatoVentana(125)).toBe('2:05')
    expect(formatoVentana(9)).toBe('0:09')
  })

  it('decide cuándo pedir PIN', () => {
    expect(debeAbrirPin(false, true)).toBe(true)
    expect(debeAbrirPin(true, true)).toBe(false)
    expect(debeAbrirPin(false, false)).toBe(false)
  })

  it('maneja error_escritura', () => {
    const out = manejarErrorEscritura('ventana')
    expect(out.soloLectura).toBe(true)
    expect(out.forget).toBe(true)
    expect(out.aviso).toMatch(/cerró/)
    expect(manejarErrorEscritura('apagado').forget).toBe(false)
  })
})

describe('rotuloTecla', () => {
  it('muestra símbolos legibles, no los nombres internos', async () => {
    const { rotuloTecla } = await import('./vivoEscritura')
    expect(rotuloTecla('izquierda')).toBe('←')
    expect(rotuloTecla('arriba')).toBe('↑')
    expect(rotuloTecla('abajo')).toBe('↓')
    expect(rotuloTecla('derecha')).toBe('→')
    expect(rotuloTecla('ctrl-c')).toBe('Ctrl-C')
    expect(rotuloTecla('esc')).toBe('Esc')
    expect(rotuloTecla('tab')).toBe('Tab')
    expect(rotuloTecla('enter')).toBe('Enter')
    expect(rotuloTecla('1')).toBe('1')
  })
})

describe('agrupadorEntrada', () => {
  it('junta lo tipeado en una tanda y lo manda una vez', async () => {
    vi.useFakeTimers()
    const { agrupadorEntrada } = await import('./vivoEscritura')
    const enviados: string[] = []
    const g = agrupadorEntrada((t) => enviados.push(t), 30)
    g.push('h')
    g.push('o')
    g.push('la')
    expect(enviados).toEqual([])
    vi.advanceTimersByTime(30)
    expect(enviados).toEqual(['hola'])
    vi.useRealTimers()
  })

  it('cancelar descarta lo pendiente', async () => {
    vi.useFakeTimers()
    const { agrupadorEntrada } = await import('./vivoEscritura')
    const enviados: string[] = []
    const g = agrupadorEntrada((t) => enviados.push(t), 30)
    g.push('x')
    g.cancelar()
    vi.advanceTimersByTime(100)
    expect(enviados).toEqual([])
    vi.useRealTimers()
  })

  it('parte tandas largas en trozos de 4096', async () => {
    vi.useFakeTimers()
    const { agrupadorEntrada } = await import('./vivoEscritura')
    const enviados: string[] = []
    const g = agrupadorEntrada((t) => enviados.push(t), 30)
    g.push('a'.repeat(5000))
    vi.advanceTimersByTime(30)
    expect(enviados.map((t) => t.length)).toEqual([4096, 904])
    vi.useRealTimers()
  })
})
