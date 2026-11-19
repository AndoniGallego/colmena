import { describe, expect, it } from 'vitest'
import { plainPreview } from './preview'

describe('plainPreview', () => {
  it('quita encabezados y los separa del texto que sigue', () => {
    expect(plainPreview('## Qué es\nEs una web que corre en la notebook.')).toBe('Qué es. Es una web que corre en la notebook.')
  })
  it('negritas, cursivas, código inline y links quedan como texto', () => {
    expect(plainPreview('**Listo**: corrí `composer test` y mirá [el doc](https://x.io/a) y *esto*.')).toBe('Listo: corrí composer test y mirá el doc y esto.')
  })
  it('listas en una línea con separador', () => {
    expect(plainPreview('Cambios:\n- timeouts a 8 s\n- reintento con backoff\n1. logs sin PAN')).toBe('Cambios: timeouts a 8 s · reintento con backoff · logs sin PAN')
  })
  it('bloques de código: queda el contenido sin las vallas, incluso sin cerrar', () => {
    expect(plainPreview('Falló:\n```php\nFAILURES! Tests: 214\n```\nRevisar el test.')).toBe('Falló: FAILURES! Tests: 214 Revisar el test.')
    expect(plainPreview('Salida:\n```\nlinea uno\nlinea dos')).toBe('Salida: linea uno linea dos')
  })
  it('marcas sin cerrar por un corte no quedan sueltas', () => {
    expect(plainPreview('Esto es **muy impor')).toBe('Esto es muy impor')
    expect(plainPreview('mirá `src/lib/x')).toBe('mirá src/lib/x')
  })
  it('no rompe snake_case ni rutas largas', () => {
    expect(plainPreview('usa my_var_name en /home/usuario/a_b/c_d.php')).toBe('usa my_var_name en /home/usuario/a_b/c_d.php')
  })
  it('imágenes, html, citas, tablas y reglas', () => {
    expect(plainPreview('![mapa](http://a/b.png) hola <b>x</b>')).toBe('mapa hola x')
    expect(plainPreview('> cita\n---\n| a | b |\n|---|---|\n| 1 | 2 |')).toBe('cita a · b 1 · 2')
  })
  it('colapsa espacios y maneja vacío', () => {
    expect(plainPreview('  a \n\n\n  b\t c ')).toBe('a b c')
    expect(plainPreview('')).toBe('')
    expect(plainPreview(null)).toBe('')
  })
})

describe('plainPreview with blocks', () => {
  it('never shows the JSON of diagrama or opciones blocks', () => {
    const d = JSON.stringify({ titulo: 'Cómo se conecta todo', nodos: [{ id: 'a' }] })
    const f = JSON.stringify({ titulo: 'Cocinar "un" bife', tipo: 'proceso', pasos: [] })
    const o = JSON.stringify({ pregunta: '¿Qué hacemos?', opciones: [] })
    const out = plainPreview(`Mirá esto\n\n\`\`\`diagrama\n${d}\n\`\`\`\n\n\`\`\`diagrama\n${f}\n\`\`\`\n\n\`\`\`opciones\n${o}\n\`\`\``)
    expect(out).toBe('Mirá esto Diagrama: Cómo se conecta todo. Diagrama: Cocinar "un" bife. ¿Qué hacemos?')
    expect(out).not.toContain('{')
  })

  it('handles unclosed blocks and blocks without title', () => {
    expect(plainPreview('Va\n```diagrama\n{"nodos": [')).toBe('Va Diagrama.')
    expect(plainPreview('```diagrama\n{"tipo": "proceso", "pasos": []}\n```')).toBe('Diagrama.')
  })
})
