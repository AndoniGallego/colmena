import { readFileSync } from 'node:fs'
import { compileScript, compileTemplate, parse, registerTS } from '@vue/compiler-sfc'
import ts from 'typescript'
import { describe, expect, it } from 'vitest'

registerTS(() => ts)
const fs = {
  fileExists: (f: string) => {
    try {
      readFileSync(f, 'utf8')
      return true
    } catch {
      return false
    }
  },
  readFile: (f: string) => readFileSync(f, 'utf8'),
  realpath: (f: string) => f,
}

const fuentes = import.meta.glob('./**/*.vue', { query: '?raw', import: 'default', eager: true }) as Record<string, string>
const archivos = Object.entries(fuentes)

// vitest y vue-tsc no detectaron un <Transition> con dos hijos: acá se compila cada .vue como lo haría el build.
describe('todos los .vue compilan', () => {
  it('encuentra componentes', () => {
    expect(archivos.length).toBeGreaterThan(20)
  })

  it.each(archivos)('%s', (nombre, source) => {
    const filename = new URL(nombre, import.meta.url).pathname
    const { descriptor, errors } = parse(source, { filename })
    const fallos: string[] = errors.map((e) => `parse: ${e.message}`)
    if (!fallos.length) {
      const id = 'sfc-test'
      let bindings
      if (descriptor.script || descriptor.scriptSetup) bindings = compileScript(descriptor, { id, fs }).bindings
      if (descriptor.template) {
        const t = compileTemplate({
          source: descriptor.template.content,
          filename,
          id,
          scoped: descriptor.styles.some((s) => s.scoped),
          compilerOptions: { bindingMetadata: bindings },
        })
        fallos.push(...t.errors.map((e) => `template: ${typeof e === 'string' ? e : e.message}`))
      }
    }
    expect(fallos).toEqual([])
  })
})
