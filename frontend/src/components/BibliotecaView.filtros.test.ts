import { describe, expect, it } from 'vitest'
import src from './BibliotecaView.vue?raw'

describe('BibliotecaView hoja de filtros', () => {
  it('cierra arrastrando la barrita con useSheetSwipe', () => {
    expect(src).toMatch(/import \{ useSheetSwipe \} from '\.\.\/lib\/useSheetSwipe'/)
    expect(src).toMatch(/useSheetSwipe\(filtersPanel, \(\) => \{\s*filtersOpen\.value = false\s*\}\)/)
    expect(src).toMatch(/ref="filtersPanel" class="sheet-panel sheet"/)
  })
})
