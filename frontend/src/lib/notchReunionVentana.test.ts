import { describe, expect, it } from 'vitest'
import { accionAlTocarNotch, reunionViva } from './notchReunionVentana'

describe('reunionViva', () => {
  it('escuchando, pausada, sin PC y llena siguen vivas', () => {
    for (const e of ['escuchando', 'pausada', 'sin_pc', 'llena']) expect(reunionViva(e), e).toBe(true)
  })
  it('inactiva, guardándose o guardada ya no', () => {
    for (const e of ['inactiva', 'terminando', 'guardada']) expect(reunionViva(e), e).toBe(false)
  })
})

describe('accionAlTocarNotch', () => {
  it('con una reunión viva y el notch cerrado trae la ventana', () => {
    expect(accionAlTocarNotch({ modo: 'cerrado', estadoReunion: 'escuchando', enPrograma: true })).toBe('mostrar_ventana')
    expect(accionAlTocarNotch({ modo: 'cerrado', estadoReunion: 'pausada', enPrograma: true })).toBe('mostrar_ventana')
  })
  it('sin reunión viva abre el panel como siempre', () => {
    expect(accionAlTocarNotch({ modo: 'cerrado', estadoReunion: 'inactiva', enPrograma: true })).toBe('alternar')
    expect(accionAlTocarNotch({ modo: 'cerrado', estadoReunion: 'guardada', enPrograma: true })).toBe('alternar')
  })
  it('fuera de la app de Windows mantiene el comportamiento de siempre', () => {
    expect(accionAlTocarNotch({ modo: 'cerrado', estadoReunion: 'escuchando', enPrograma: false })).toBe('alternar')
  })
  it('con el notch abierto, tocarlo lo cierra (alternar)', () => {
    expect(accionAlTocarNotch({ modo: 'panel', estadoReunion: 'escuchando', enPrograma: true })).toBe('alternar')
    expect(accionAlTocarNotch({ modo: 'aviso', estadoReunion: 'escuchando', enPrograma: true })).toBe('alternar')
  })
})
