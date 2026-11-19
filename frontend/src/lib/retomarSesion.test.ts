import { describe, expect, it } from 'vitest'
import { armarCuerpoRetomar, filtrarSesionesViejas, idOperacionRetomar, mensajeErrorRetomar } from './retomarSesion'

const sesion = {
  session_id: '6f1c1e0b-4a55-4e1d-9d33-1f3c2a7d9e10',
  titulo: 'API checkout',
  carpeta: '~/Proyectos/foo',
  ultimo_ts: '2026-01-01',
  ultima_frase: 'seguimos mañana',
}

describe('filtrarSesionesViejas', () => {
  it('filtra por título, carpeta y frase', () => {
    expect(filtrarSesionesViejas([sesion], 'checkout')).toHaveLength(1)
    expect(filtrarSesionesViejas([sesion], 'proyectos')).toHaveLength(1)
    expect(filtrarSesionesViejas([sesion], 'mañana')).toHaveLength(1)
    expect(filtrarSesionesViejas([sesion], 'zzz')).toHaveLength(0)
  })
})

describe('mensajeErrorRetomar', () => {
  it('mapea status conocidos', () => {
    expect(mensajeErrorRetomar(429, '')).toContain('tope')
    expect(mensajeErrorRetomar(409, 'ya abierta')).toContain('abierta')
    expect(mensajeErrorRetomar(404, '')).toContain('retomar')
    expect(mensajeErrorRetomar(500, '')).toBe('No pude retomarla')
  })
})

describe('armarCuerpoRetomar', () => {
  it('arma con grupo o tarjeta nueva', () => {
    const id = idOperacionRetomar()
    const conGrupo = armarCuerpoRetomar(sesion, 'Mi sesión', 'g1', '', id)
    expect(conGrupo?.grupo).toBe('g1')
    const nueva = armarCuerpoRetomar(sesion, 'Mi sesión', '', 'Tarjeta', id)
    expect(nueva?.nombre_tarjeta).toBe('Tarjeta')
  })
})
