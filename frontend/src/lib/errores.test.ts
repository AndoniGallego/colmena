import { describe, expect, it } from 'vitest'
import { ApiError } from '../api/types'
import { ErrorUsuario, detalleTecnico, mensajeError } from './errores'

const FB = 'fallback custom'

describe('mensajeError', () => {
  it('401 y 403 → sesión vencida', () => {
    expect(mensajeError(new ApiError(401, 'Unauthorized'))).toBe('Tu sesión venció. Volvé a entrar.')
    expect(mensajeError(new ApiError(403, 'Forbidden'))).toBe('Tu sesión venció. Volvé a entrar.')
  })

  it('404 con detail del backend lo conserva; sin cuerpo → no encontré', () => {
    expect(mensajeError(new ApiError(404, 'no encontrado'))).toBe('no encontrado')
    expect(mensajeError(new ApiError(404, 'Not Found', null, [], true))).toBe('No encontré eso. Puede que ya no exista.')
  })

  it('un Error crudo que no es ErrorUsuario no se muestra tal cual', () => {
    expect(mensajeError(new Error('Cannot read properties of undefined'))).toBe('Algo salió mal. Probá de nuevo.')
    expect(mensajeError(new Error('boom'), FB)).toBe(FB)
  })

  it('408 y timeouts → tardó demasiado', () => {
    expect(mensajeError(new ApiError(408, 'Request Timeout'))).toBe('Tardó demasiado en responder. Probá de nuevo.')
    expect(mensajeError(new DOMException('aborted', 'AbortError'))).toBe('Tardó demasiado en responder. Probá de nuevo.')
    expect(mensajeError(new DOMException('timeout', 'TimeoutError'))).toBe('Tardó demasiado en responder. Probá de nuevo.')
    expect(mensajeError(new Error('connection timed out'))).toBe('Tardó demasiado en responder. Probá de nuevo.')
  })

  it('429 → demasiados pedidos', () => {
    expect(mensajeError(new ApiError(429, 'Too Many Requests'))).toBe(
      'Demasiados pedidos seguidos. Esperá un momento y probá de nuevo.',
    )
  })

  it('5xx → problema en Colmena', () => {
    expect(mensajeError(new ApiError(502, 'Bad Gateway', null, [], true))).toBe('Colmena tuvo un problema. Probá de nuevo.')
  })

  it('detail del backend en castellano (sin sinCuerpo)', () => {
    expect(mensajeError(new ApiError(400, 'El pin no coincide'))).toBe('El pin no coincide')
  })

  it('sinCuerpo 400 → fallback', () => {
    expect(mensajeError(new ApiError(400, 'HTTP 400', null, [], true), FB)).toBe(FB)
    expect(mensajeError(new ApiError(400, 'HTTP 400', null, [], true))).toBe('Algo salió mal. Probá de nuevo.')
  })

  it('red: TypeError, Failed to fetch, NetworkError, Load failed', () => {
    expect(mensajeError(new TypeError('Failed to fetch'))).toBe('No llego a Colmena. Revisá la conexión y probá de nuevo.')
    expect(mensajeError(new Error('NetworkError when attempting to fetch resource.'))).toBe(
      'No llego a Colmena. Revisá la conexión y probá de nuevo.',
    )
    expect(mensajeError(new Error('Load failed'))).toBe('No llego a Colmena. Revisá la conexión y probá de nuevo.')
  })

  it('ErrorUsuario → mensaje tal cual', () => {
    expect(mensajeError(new ErrorUsuario('No se pudo activar'))).toBe('No se pudo activar')
  })

  it('cualquier otra cosa → fallback o genérico', () => {
    expect(mensajeError(42, FB)).toBe(FB)
    expect(mensajeError(42)).toBe('Algo salió mal. Probá de nuevo.')
  })
})

describe('detalleTecnico', () => {
  it('null si el mensaje mostrado ya es el original (backend)', () => {
    expect(detalleTecnico(new ApiError(400, 'El pin no coincide'))).toBeNull()
    expect(detalleTecnico(new ErrorUsuario('Hecho'))).toBeNull()
  })

  it('texto técnico si mensajeError tradujo', () => {
    expect(detalleTecnico(new ApiError(502, 'Bad Gateway', null, [], true))).toBe('502: Bad Gateway')
    expect(detalleTecnico(new TypeError('Failed to fetch'))).toBe('TypeError: Failed to fetch')
  })
})
