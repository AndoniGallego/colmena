import { describe, expect, it } from 'vitest'
import { esNombrePropioTab, tituloTarjeta, ocultarNombreTab } from './cardTitle'

describe('esNombrePropioTab', () => {
  it('detecta nombres propios', () => {
    expect(esNombrePropioTab('deploy')).toBe(true)
    expect(esNombrePropioTab('')).toBe(false)
    expect(esNombrePropioTab('3')).toBe(false)
    expect(esNombrePropioTab('42')).toBe(false)
  })
})

describe('tituloTarjeta', () => {
  it('prioriza el nombre de pestaña propio', () => {
    expect(tituloTarjeta('Claude Code', 'haciendo algo', 'deploy')).toBe('deploy')
  })
  it('usa el título del agente si la pestaña es numérica', () => {
    expect(tituloTarjeta('Claude Code', 'haciendo', '1')).toBe('Claude Code')
    expect(tituloTarjeta('', 'haciendo', '')).toBe('haciendo')
  })
})

describe('ocultarNombreTab', () => {
  it('oculta cuando una sola tarjeta repite el título', () => {
    expect(ocultarNombreTab(1, 'deploy', 'deploy')).toBe(true)
    expect(ocultarNombreTab(2, 'deploy', 'deploy')).toBe(false)
    expect(ocultarNombreTab(1, 'tab 1', 'Claude Code')).toBe(false)
  })
})
