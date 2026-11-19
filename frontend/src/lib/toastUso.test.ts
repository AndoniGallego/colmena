import { describe, expect, it } from 'vitest'

const erroresEnLugar = [
  { file: '../state/biblioteca.ts?raw', pattern: /lib\.quitarErr = 'No pude quitarlo, probá de nuevo'/ },
  { file: '../state/mrs.ts?raw', pattern: /mrs\.pausaErr = mensaje/ },
  { file: '../state/mudanza.ts?raw', pattern: /mz\.error = mensajeError/ },
  { file: '../state/ordenTablero.ts?raw', pattern: /ordenError\.value = 'No pude guardar el orden'/ },
  { file: '../components/CopyBtn.vue?raw', pattern: /fallo\('No pude copiar'/ },
  { file: '../components/BibViewer.vue?raw', pattern: /fallo\('No se pudo copiar la ruta'/ },
  { file: '../components/CloseSheet.vue?raw', pattern: /copiaFallo\('No pude copiar el comando'/ },
]

describe('errores en el lugar (sin píldora)', () => {
  for (const { file, pattern } of erroresEnLugar) {
    it(`${file} reporta el fallo en estado o botón`, async () => {
      const src = (await import(/* @vite-ignore */ file)).default as string
      expect(src).toMatch(pattern)
    })
  }
})
