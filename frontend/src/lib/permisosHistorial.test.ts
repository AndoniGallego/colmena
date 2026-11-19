import { describe, expect, it } from 'vitest'
import type { RegistroPermiso } from '../api/types'
import { filasHistorial } from './permisosHistorial'

const h = '2026-11-14T10:00:00Z'

describe('filasHistorial', () => {
  it('muestra quién decidió, con filas viejas y desconocidas', () => {
    const f = filasHistorial([
      { quien: 'centinela', decision: 'permitir', herramienta: 'Bash', hora: h },
      { herramienta: 'Edit', hora: h } as RegistroPermiso,
    ])
    expect(f.map((x) => x.quien)).toEqual(['Centinela (antes)', '—'])
  })

  it('las decisiones del usuario salen como "Vos" con el texto de la decisión', () => {
    const [a, b, c] = filasHistorial([
      { quien: 'usuario', decision: 'rechazar', herramienta: 'Bash', entrada: { command: 'rm -rf x' }, hora: h, sesion: 'Tienda · Back' },
      { quien: 'usuario', decision: 'siempre', herramienta: 'Edit', entrada: { file_path: '/a/b.php' }, hora: h },
      { quien: 'politica', categoria: 'auto', herramienta: 'Read', hora: h, session_id: 'abcdefghijkl' },
    ])
    expect(a).toMatchObject({ quien: 'Vos', decision: 'Rechazado', herramienta: 'Bash', detalle: 'rm -rf x', sesion: 'Tienda · Back' })
    expect(b).toMatchObject({ decision: 'Permitido siempre', detalle: '/a/b.php' })
    expect(c).toMatchObject({ quien: 'Política (antes)', decision: 'Aprobado', sesion: 'abcdefgh' })
  })

  it('no rompe con filas sin hora, sin herramienta o con entrada rara', () => {
    const f = filasHistorial([{ quien: 'zzz' as never, entrada: { command: 5 } } as RegistroPermiso, { hora: 'no-es-fecha' } as RegistroPermiso])
    expect(f).toHaveLength(2)
    expect(f[0]).toMatchObject({ quien: '—', herramienta: '', detalle: '', hora: '', sesion: '—' })
    expect(f[1].hora).toBe('')
  })
})
