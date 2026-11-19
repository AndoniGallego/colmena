import { describe, expect, it } from 'vitest'
import { ApiError } from '../api/types'
import {
  NO_LLEGO,
  claseCodigo,
  conEnlace,
  cuerpoLegible,
  esMetodoQueCambia,
  etiquetaEstado,
  explicarError,
  faseDe,
  haceTexto,
  lineaServicioProblema,
  mensajeErrorRed,
  puertosTunel,
  resumenEntornos,
  serviciosConProblema,
} from './entornos'
import { formatSize } from './attachments'

describe('entornos', () => {
  const t = (estado: 'abierto' | 'error', error: string | null = null) => ({
    estado,
    puertos: [8080, 8092],
    error,
  })

  it('faseDe respeta el orden de prioridad', () => {
    const s = {
      tuneles: { a: t('abierto'), b: t('error', 'murió'), c: t('abierto') },
      abriendo: ['c'],
      errores: { a: 'el puerto 8080 ya está en uso en esta PC' },
    }
    expect(['a', 'b', 'c', 'd'].map((n) => faseDe(n, s))).toEqual([
      { fase: 'error', error: 'el puerto 8080 ya está en uso en esta PC' },
      { fase: 'error', error: 'murió' },
      { fase: 'abriendo', error: null },
      { fase: 'cerrado', error: null },
    ])
  })

  it('explica los errores de red de ssh', () => {
    expect(explicarError('usuario@192.168.1.50: Permission denied (publickey).')).toEqual({
      texto: NO_LLEGO,
      original: 'usuario@192.168.1.50: Permission denied (publickey).',
    })
    expect(explicarError('ssh: connect to host 192.168.1.250 port 22: Connection timed out').texto).toBe(NO_LLEGO)
    expect(explicarError('ssh: connect to host 192.168.1.9 port 22: No route to host').texto).toBe(NO_LLEGO)
    expect(explicarError('ssh: connect to host 192.168.1.50 port 22: Connection refused').texto).toBe(NO_LLEGO)
    expect(
      explicarError(
        'ssh: Could not resolve hostname notebook.local: Temporary failure in name resolution',
      ).texto,
    ).toBe(NO_LLEGO)
    expect(explicarError('el puerto 8770 está bloqueado por seguridad')).toEqual({
      texto: 'el puerto 8770 está bloqueado por seguridad',
      original: null,
    })
  })

  it('resumenEntornos cuenta totales y abiertos', () => {
    const s = {
      tuneles: { a: t('abierto'), b: t('error', 'x'), c: t('error', 'y') },
      abriendo: [],
      errores: {},
    }
    expect(resumenEntornos([], s)).toEqual({ total: 0, abiertos: 0, texto: '' })
    expect(resumenEntornos(['a', 'b', 'c'], s).texto).toBe('3 entornos · 1 abierto')
    expect(resumenEntornos(['c'], s).texto).toBe('1 entorno · 0 abiertos')
    expect(resumenEntornos(['a', 'b'], { ...s, tuneles: { a: t('abierto'), b: t('abierto') } }).texto).toBe(
      '2 entornos · 2 abiertos',
    )
  })

  it('mensajeErrorRed traduce fallos de red y HTTP', () => {
    expect(mensajeErrorRed(new TypeError('Failed to fetch'))).toBe(
      'No llego a Colmena. Revisá la conexión y probá de nuevo.',
    )
    expect(mensajeErrorRed(new Error('NetworkError when attempting to fetch resource.'))).toBe(
      'No llego a Colmena. Revisá la conexión y probá de nuevo.',
    )
    expect(mensajeErrorRed(new ApiError(502, 'Bad Gateway'))).toBe('Colmena tuvo un problema. Probá de nuevo.')
    expect(mensajeErrorRed(new ApiError(401, 'Unauthorized'))).toBe('Tu sesión venció. Volvé a entrar.')
    expect(mensajeErrorRed(new ApiError(403, 'Forbidden'))).toBe('Tu sesión venció. Volvé a entrar.')
    expect(mensajeErrorRed(new ApiError(404, 'no encontrado'))).toBe('no encontrado')
  })

  it('haceTexto con división entera', () => {
    expect(haceTexto(null)).toBe('')
    expect(haceTexto(30)).toBe('hace segundos')
    expect(haceTexto(300)).toBe('hace 5 min')
    expect(haceTexto(7200)).toBe('hace 2 h')
    expect(haceTexto(86400)).toBe('hace 1 día')
    expect(haceTexto(172800)).toBe('hace 2 días')
  })

  it('etiquetaEstado con textos de UI', () => {
    expect(etiquetaEstado('corriendo')).toBe('Corriendo')
    expect(etiquetaEstado('arrancando')).toBe('Arrancando')
    expect(etiquetaEstado('enfermo')).toBe('Con problemas')
    expect(etiquetaEstado('reiniciando')).toBe('Reiniciándose')
    expect(etiquetaEstado('pausado')).toBe('En pausa')
    expect(etiquetaEstado('caido')).toBe('Caído')
    expect(etiquetaEstado('terminado')).toBe('Terminó')
  })

  it('serviciosConProblema excluye corriendo y terminado', () => {
    const servicios = [
      { servicio: 'web', estado: 'corriendo' as const, codigo: null, hace_s: null },
      { servicio: 'migrate', estado: 'terminado' as const, codigo: 0, hace_s: 3600 },
      { servicio: 'worker', estado: 'caido' as const, codigo: 1, hace_s: 300 },
    ]
    const probs = serviciosConProblema(servicios)
    expect(probs.map((s) => s.servicio)).toEqual(['worker'])
    expect(lineaServicioProblema(probs[0]!)).toBe('worker · Caído · hace 5 min · código 1')
  })

  it('solo los puertos abribles van al túnel y llevan enlace', () => {
    const e = {
      nombre: 'x',
      carpeta: '',
      principal: 5173,
      salud: null,
      apagado: false,
      servicios: [],
      puertos: [
        { puerto: 80, servicio: 'x', puerto_contenedor: null, abrible: false },
        { puerto: 5173, servicio: 'x', puerto_contenedor: null, abrible: true },
      ],
    }
    expect(puertosTunel(e)).toEqual([5173])
    const abierto = { fase: 'abierto' as const, error: null }
    expect(conEnlace(e.puertos[1], abierto, { estado: 'abierto', puertos: [5173], error: null })).toBe(true)
    expect(conEnlace(e.puertos[0], abierto, { estado: 'abierto', puertos: [5173], error: null })).toBe(false)
    expect(conEnlace(e.puertos[1], { fase: 'cerrado', error: null })).toBe(false)
  })

  it('esMetodoQueCambia', () => {
    expect(esMetodoQueCambia('GET')).toBe(false)
    expect(esMetodoQueCambia('HEAD')).toBe(false)
    expect(esMetodoQueCambia('POST')).toBe(true)
    expect(esMetodoQueCambia('PUT')).toBe(true)
    expect(esMetodoQueCambia('PATCH')).toBe(true)
    expect(esMetodoQueCambia('DELETE')).toBe(true)
  })

  it('cuerpoLegible', () => {
    expect(cuerpoLegible(null)).toBe('')
    expect(cuerpoLegible('hola')).toBe('hola')
    expect(cuerpoLegible('{"a":1}')).toBe('{\n  "a": 1\n}')
    expect(cuerpoLegible('x')).toBe('x')
  })

  it('claseCodigo', () => {
    expect(claseCodigo(200)).toBe('ok')
    expect(claseCodigo(299)).toBe('ok')
    expect(claseCodigo(301)).toBe('aviso')
    expect(claseCodigo(404)).toBe('mal')
    expect(claseCodigo(500)).toBe('mal')
  })

  it('formatSize del helper de adjuntos', () => {
    expect(formatSize(0)).toBe('0 B')
    expect(formatSize(512)).toBe('512 B')
    expect(formatSize(1536)).toBe('2 KB')
    expect(formatSize(1048576)).toBe('1 MB')
  })
})
