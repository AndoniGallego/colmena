import { describe, expect, it } from 'vitest'
import src from './RetomarSesionSheet.vue?raw'

describe('RetomarSesionSheet', () => {
  it('renderiza filas de sesiones en el template', () => {
    expect(src).toContain('v-for="s in listado"')
    expect(src).toContain('class="fila"')
    expect(src).toContain('Retomar sesión')
  })
})
