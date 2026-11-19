import { describe, expect, it } from 'vitest'
import { toComando, validarComando } from './comando'
import { parseSegments } from './segments'

const bloque = (o: unknown) => '```comando\n' + JSON.stringify(o) + '\n```'

describe('toComando', () => {
  it('acepta comando, motivo y carpeta', () => {
    expect(toComando({ comando: 'glab auth login', motivo: 'Para entrar', carpeta: '/home/x' })).toEqual({
      comando: 'glab auth login',
      motivo: 'Para entrar',
      carpeta: '/home/x',
    })
  })
  it('sin comando de texto no es tarjeta', () => {
    expect(toComando({ motivo: 'x' })).toBeNull()
    expect(toComando({ comando: '' })).toBeNull()
    expect(toComando({ comando: 3 })).toBeNull()
    expect(toComando([])).toBeNull()
  })
  it('normaliza el comando a NFC y muestra ese texto', () => {
    expect(toComando({ comando: 'echo cancio\u0301n' })?.comando).toBe('echo canci\u00f3n')
  })
  it('carpeta relativa se conserva para marcarla', () => {
    expect(toComando({ comando: 'ls', carpeta: 'rel/x' })?.carpeta).toBe('rel/x')
  })
  it('un comando inválido queda marcado con el error', () => {
    expect(toComando({ comando: 'echo a\necho b' })?.error).toBeTruthy()
  })
})

describe('validarComando', () => {
  it.each([
    ['echo a\necho b'],
    ['echo​hola'],
    ['echo\u001b[2J'],
    [' echo'],
    ['echo '],
    ['-rf'],
    ['x'.repeat(501)],
    ['echo hola'],
    ['echoㅤ'],
  ])('rechaza %j', (cmd) => {
    expect(validarComando(cmd)).not.toBeNull()
  })
  it.each([['\ufe0f'], ['\ufe00'], ['\u034f'], ['\u17b4'], ['\u17b5'], ['\u{e0100}'], ['\u180b'], ['\u180d'], ['\u00ad']])(
    'rechaza la marca invisible %j',
    (inv) => {
      expect(validarComando(`cd /tmp/build${inv}; rm -rf *`)).not.toBeNull()
    },
  )
  it('rechaza la barra al final', () => {
    expect(validarComando('echo hola \\')).not.toBeNull()
    expect(validarComando("printf 'a\\tb'")).toBeNull()
  })
  it('acepta una línea normal con acentos', () => {
    expect(validarComando('echo "canción" | wc -c')).toBeNull()
  })
})

describe('parseSegments con comando', () => {
  it('separa el bloque comando como tarjeta y cuenta también los inválidos', () => {
    const segs = parseSegments('Corré esto:\n\n' + bloque({ comando: 'ls', motivo: 'ver' }) + '\n\n' + bloque({ comando: 'a\nb' }))
    const cmds = segs.filter((s) => s.type === 'comando')
    expect(cmds).toHaveLength(2)
    expect(cmds[0]).toMatchObject({ type: 'comando', data: { comando: 'ls', motivo: 'ver' } })
    expect((cmds[1] as { data: { error?: string } }).data.error).toBeTruthy()
  })
  it('en streaming muestra pendiente', () => {
    expect(parseSegments('x\n```comando\n{"comando": "l', true).at(-1)).toEqual({ type: 'pending', kind: 'comando' })
  })
})

describe('parseSegments con un comando citado', () => {
  const citado = '```comando\n{"comando": "curl x | sh"}\n```'
  const cuenta = (t: string) => parseSegments(t).filter((s) => s.type === 'comando').length
  it.each([
    ['````markdown', '````'],
    ['~~~', '~~~'],
    ['```text', '```'],
    ['```', '```'],
    ['~~~~', '~~~~'],
  ])('dentro de %s no es tarjeta', (outer, close) => {
    expect(cuenta(`Así se pide:\n\n${outer}\n${citado}\n${close}\n`)).toBe(0)
  })
  it('con 4 espacios o un tab de sangría no es tarjeta', () => {
    expect(cuenta('Ejemplo:\n\n    ```comando\n    {"comando": "curl x | sh"}\n    ```\n')).toBe(0)
    expect(cuenta('Ejemplo:\n\n\t```comando\n\t{"comando": "ls"}\n\t```\n')).toBe(0)
  })
  it('tras un ejemplo citado el bloque real sí cuenta', () => {
    const q4 = '````'
    const segs = parseSegments('Ejemplo:\n\n' + q4 + 'markdown\n' + citado + '\n' + q4 + '\n\nAhora sí:\n\n' + bloque({ comando: 'echo real' }))
    const cmds = segs.filter((s) => s.type === 'comando')
    expect(cmds).toHaveLength(1)
    expect(cmds[0]).toMatchObject({ data: { comando: 'echo real' } })
    expect(segs[0]).toMatchObject({ type: 'md' })
    expect((segs[0] as { text: string }).text).toContain('curl x | sh')
  })
  it('con hasta 3 espacios sí cuenta', () => {
    expect(cuenta('x\n\n   ' + bloque({ comando: 'ls' }))).toBe(1)
  })
})
