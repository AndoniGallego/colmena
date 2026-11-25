// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest'
import {
  armarCuerpoNueva,
  armarCuerpoTarea,
  esAtajoEnviar,
  guardarModo,
  guardarUltimoRepo,
  leerModo,
  leerUltimoRepo,
  repoInicial,
  soloRepos,
  validarRamaNueva,
  validarTarea,
  validarTicket,
  ramaDeTicket,
  carpetaSugerida,
  filtrarCarpetas,
  idOperacionNueva,
  placeholderNombre,
  validarNombreNueva,
  type GrupoItem,
} from './nuevaTerminal'

const CARPETAS = [
  { ruta: '~/Proyectos/orq', nombre: 'orq' },
  { ruta: '~/proyectos/acme', nombre: 'Acme' },
  { ruta: '~/Proyectos/acmekit', nombre: 'acmekit' },
]

describe('filtrarCarpetas', () => {
  it('sin buscador devuelve todo', () => {
    expect(filtrarCarpetas(CARPETAS, '')).toHaveLength(3)
  })
  it('filtra por nombre o ruta', () => {
    expect(filtrarCarpetas(CARPETAS, 'acme').map((c) => c.nombre)).toEqual(['Acme', 'acmekit'])
  })
})

describe('validarNombreNueva', () => {
  it('vacío es válido', () => {
    expect(validarNombreNueva('')).toBe('')
  })
  it('rechaza control y largo', () => {
    expect(validarNombreNueva('a'.repeat(61))).toMatch(/60/)
    expect(validarNombreNueva('x\x00y')).toMatch(/caracteres/)
  })
})

describe('armarCuerpoNueva', () => {
  it('usa nombre de carpeta si no hay nombre', () => {
    const c = CARPETAS[0]
    expect(armarCuerpoNueva(c, 'shell', '', 'abcdefgh1', null)).toEqual({
      carpeta: c.ruta,
      tipo: 'shell',
      id: 'abcdefgh1',
    })
  })
  it('incluye nombre si hay texto', () => {
    expect(armarCuerpoNueva(CARPETAS[0], 'claude', 'Mi cosa', 'abcdefgh2', null)).toMatchObject({
      nombre: 'Mi cosa',
      tipo: 'claude',
    })
  })
  it('incluye grupo si se eligió uno existente', () => {
    expect(armarCuerpoNueva(CARPETAS[0], 'shell', '', 'abcdefgh4', 'g2')).toMatchObject({ grupo: 'g2' })
    expect(armarCuerpoNueva(CARPETAS[0], 'shell', '', 'abcdefgh5', null)).not.toHaveProperty('grupo')
    expect(armarCuerpoNueva(CARPETAS[0], 'shell', '', 'abcdefgh6', '')).not.toHaveProperty('grupo')
  })
})

describe('carpetaSugerida', () => {
  const grupos: GrupoItem[] = [
    { id: 'g1', nombre: 'A', carpeta: '~/Proyectos/orq' },
    { id: 'g2', nombre: 'B', carpeta: null },
  ]
  it('devuelve la carpeta del grupo si está en la lista', () => {
    expect(carpetaSugerida('g1', grupos, CARPETAS)).toEqual(CARPETAS[0])
  })
  it('null si el grupo no tiene carpeta o no coincide', () => {
    expect(carpetaSugerida('g2', grupos, CARPETAS)).toBeNull()
    expect(carpetaSugerida('g9', grupos, CARPETAS)).toBeNull()
  })
})

describe('idOperacionNueva', () => {
  it('genera ids distintos', () => {
    const a = idOperacionNueva()
    const b = idOperacionNueva()
    expect(a).not.toBe(b)
    expect(a).toMatch(/^[A-Za-z0-9_-]{8,64}$/)
  })
})

describe('placeholderNombre', () => {
  it('usa el nombre de la carpeta elegida', () => {
    expect(placeholderNombre(CARPETAS[1])).toBe('Acme')
    expect(placeholderNombre(null)).toBe('')
  })
})


describe('modo nueva tarea', () => {
  beforeEach(() => localStorage.clear())

  it('recuerda el último modo y cae a terminal si hay basura', () => {
    expect(leerModo()).toBe('terminal')
    guardarModo('tarea')
    expect(leerModo()).toBe('tarea')
    localStorage.setItem('orq.nuevaModo', 'otra-cosa')
    expect(leerModo()).toBe('terminal')
  })

  it('recuerda el último repo', () => {
    expect(leerUltimoRepo()).toBe('')
    guardarUltimoRepo('~/Proyectos/orq')
    expect(leerUltimoRepo()).toBe('~/Proyectos/orq')
  })

  it('no se rompe si el almacenamiento falla', () => {
    const orig = Storage.prototype.getItem
    Storage.prototype.getItem = () => {
      throw new Error('bloqueado')
    }
    try {
      expect(leerModo()).toBe('terminal')
      expect(leerUltimoRepo()).toBe('')
    } finally {
      Storage.prototype.getItem = orig
    }
  })

  const REPOS = [
    { ruta: '~/Proyectos/orq', nombre: 'orq', repo: true },
    { ruta: '~/Proyectos/acmekit', nombre: 'acmekit', repo: true },
  ]

  it('soloRepos deja las carpetas que son raíz de un repo', () => {
    expect(soloRepos([...REPOS, { ruta: '~/Documents', nombre: 'Documents', repo: false }, { ruta: '~/x', nombre: 'x' }])).toEqual(REPOS)
  })

  it('repoInicial prefiere el del grupo, luego el último usado, luego el primero', () => {
    expect(repoInicial(REPOS, '~/Proyectos/orq', '~/Proyectos/acmekit')?.nombre).toBe('acmekit')
    expect(repoInicial(REPOS, '~/Proyectos/acmekit', null)?.nombre).toBe('acmekit')
    expect(repoInicial(REPOS, '~/borrado', '~/tampoco')?.nombre).toBe('orq')
    expect(repoInicial([], '', null)).toBeNull()
  })

  it('validarTarea pide texto y tiene tope', () => {
    expect(validarTarea('   ')).toBe('Contá qué hay que hacer')
    expect(validarTarea('Arreglar el login')).toBe('')
    expect(validarTarea('x'.repeat(4001))).toBe('Máximo 4000 caracteres')
  })

  it('validarTarea con ticket deja lugar al prefijo que arma el back', () => {
    expect(validarTarea('x'.repeat(3700), 'ABC-123')).toBe('')
    expect(validarTarea('x'.repeat(3701), 'ABC-123')).toBe('Máximo 3700 caracteres')
    expect(validarTarea('x'.repeat(3800), 'no-es-ticket')).toBe('')
  })

  it('validarRamaNueva: vacío vale (se deduce); formato estricto', () => {
    expect(validarRamaNueva('')).toBe('')
    expect(validarRamaNueva('feature/kit-algo')).toBe('')
    for (const mala of ['-x', 'a..b', 'a b', 'feature//x', 'feature/x.lock', 'x/']) expect(validarRamaNueva(mala)).not.toBe('')
  })

  it('armarCuerpoTarea manda solo lo que se editó', () => {
    const repo = { ruta: '~/Proyectos/orq', nombre: 'orq', repo: true }
    expect(armarCuerpoTarea(repo, '  Hacer algo  ', '', '', 'nt1234567890')).toEqual({ id: 'nt1234567890', repo: '~/Proyectos/orq', tarea: 'Hacer algo' })
    expect(armarCuerpoTarea(repo, 'Hacer', ' Mi tab ', ' feature/x ', 'nt1234567890')).toEqual({ id: 'nt1234567890', repo: '~/Proyectos/orq', tarea: 'Hacer', nombre: 'Mi tab', rama: 'feature/x' })
  })

  it('armarCuerpoTarea manda el grupo elegido, así la tarea se abre en ese workspace', () => {
    const repo = { ruta: '~/Proyectos/orq', nombre: 'orq', repo: true }
    expect(armarCuerpoTarea(repo, 'Hacer', '', '', 'nt1234567890', '', 'w2')).toEqual({ id: 'nt1234567890', repo: '~/Proyectos/orq', tarea: 'Hacer', grupo: 'w2' })
    expect(armarCuerpoTarea(repo, 'Hacer', '', '', 'nt1234567890', '', '')).not.toHaveProperty('grupo')
  })

  it('validarTicket: vacío vale; forma de clave de Jira, en cualquier caja', () => {
    expect(validarTicket('')).toBe('')
    expect(validarTicket('  abc-123 ')).toBe('')
    for (const malo of ['SITE-0', 'S-1', 'ABC-1234567', 'SITE-12; rm', 'SITE', 'SITE-01']) expect(validarTicket(malo)).toContain('ABC-123')
  })

  it('ramaDeTicket da la rama solo con ticket válido', () => {
    expect(ramaDeTicket('abc-123')).toBe('feature/ABC-123')
    expect(ramaDeTicket('')).toBe('')
    expect(ramaDeTicket('SITE-0')).toBe('')
  })

  it('validarTarea acepta vacío cuando hay ticket válido', () => {
    expect(validarTarea('', 'ABC-123')).toBe('')
    expect(validarTarea('', 'SITE-0')).toBe('Contá qué hay que hacer')
    expect(validarTarea('x'.repeat(4001), 'ABC-123')).toBe('Máximo 3700 caracteres')
  })

  it('armarCuerpoTarea con ticket lo normaliza y no manda la rama', () => {
    const repo = { ruta: '~/Proyectos/orq', nombre: 'orq', repo: true }
    expect(armarCuerpoTarea(repo, '', '', 'feature/x', 'nt1234567890', ' abc-123 ')).toEqual({ id: 'nt1234567890', repo: '~/Proyectos/orq', tarea: '', ticket: 'ABC-123' })
  })

  it('Ctrl o Cmd + Enter envía', () => {
    expect(esAtajoEnviar({ key: 'Enter', ctrlKey: true, metaKey: false })).toBe(true)
    expect(esAtajoEnviar({ key: 'Enter', ctrlKey: false, metaKey: true })).toBe(true)
    expect(esAtajoEnviar({ key: 'Enter', ctrlKey: false, metaKey: false })).toBe(false)
    expect(esAtajoEnviar({ key: 'a', ctrlKey: true, metaKey: false })).toBe(false)
  })
})

describe('esAtajoEnviar con la combinación cambiada', () => {
  it('usa la efectiva', () => {
    const e = { key: 'Enter', ctrlKey: true, metaKey: false, altKey: true }
    expect(esAtajoEnviar(e, 'mod+alt+enter')).toBe(true)
    expect(esAtajoEnviar({ ...e, altKey: false }, 'mod+alt+enter')).toBe(false)
  })
})
