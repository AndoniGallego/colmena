import { describe, expect, it } from 'vitest'
import { debeAbrirTerminalLocal, debeMostrarPinAlAbrir } from './abrirTerminalCliente'

describe('debeAbrirTerminalLocal', () => {
  it('abre en escritorio con presencia', () => {
    expect(debeAbrirTerminalLocal({ presenciaActiva: true, esEscritorio: true })).toBe(true)
  })

  it('no abre en celu', () => {
    expect(debeAbrirTerminalLocal({ presenciaActiva: true, esEscritorio: false })).toBe(false)
  })

  it('no abre en notch (sin presencia)', () => {
    expect(debeAbrirTerminalLocal({ presenciaActiva: false, esEscritorio: true })).toBe(false)
  })
})

describe('debeMostrarPinAlAbrir', () => {
  it('pide PIN si pedirPin y ventana cerrada', () => {
    expect(debeMostrarPinAlAbrir(true, false)).toBe(true)
  })

  it('no pide PIN si la ventana ya está abierta', () => {
    expect(debeMostrarPinAlAbrir(true, true)).toBe(false)
  })

  it('no pide PIN sin pedirPin', () => {
    expect(debeMostrarPinAlAbrir(false, false)).toBe(false)
  })
})
