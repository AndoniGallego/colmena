export interface Atajo {
  /** Si se puede cambiar: el id con el que se guarda (ver lib/teclas.ts). */
  id?: string
  teclas: string[]
  /** Otra forma de hacer lo mismo. */
  tambien?: string[]
  /** Ctrl en Windows y Linux, ⌘ en Mac. */
  mod?: boolean
  que: string
  donde: string
  grupo: string
}

const TODA = 'En toda la app'
const ESCRIBIR = 'Al escribirle a una sesión'
const PREGUNTA = 'En Te pregunta'
const CAMBIOS = 'En Cambios'
const TERMINAL = 'En Nueva terminal'
const BIBLIOTECA = 'En la Biblioteca'
const WINDOWS = 'En la app de Windows'
const DIAGRAMA = 'En un diagrama'

export const ATAJOS: Atajo[] = [
  { grupo: TODA, id: 'buscador', teclas: ['Ctrl', 'K'], mod: true, que: 'Abrir el buscador', donde: 'En toda la app' },
  { grupo: TODA, teclas: ['Esc'], que: 'Cerrar paneles y hojas', donde: 'En toda la app' },
  { grupo: TODA, teclas: ['↑'], tambien: ['↓'], que: 'Moverte entre los resultados', donde: 'Con el buscador abierto' },
  { grupo: TODA, teclas: ['Enter'], que: 'Abrir el resultado elegido', donde: 'Con el buscador abierto' },
  { grupo: TODA, teclas: ['Tab'], que: 'Saltar al grupo siguiente (con Shift, al anterior)', donde: 'Con el buscador abierto' },

  { grupo: ESCRIBIR, teclas: ['Enter'], que: 'Mandar el mensaje', donde: 'Al escribirle a una sesión, con teclado' },
  { grupo: ESCRIBIR, teclas: ['Shift', 'Enter'], que: 'Salto de línea', donde: 'Al escribirle a una sesión' },
  { grupo: ESCRIBIR, id: 'dictar', teclas: ['Ctrl', 'Shift', 'Espacio'], mod: true, que: 'Dictar por voz (y terminar el dictado)', donde: 'Al escribirle a una sesión' },
  { grupo: ESCRIBIR, teclas: ['Esc'], que: 'Cancelar el dictado', donde: 'Mientras dictás' },

  { grupo: PREGUNTA, teclas: ['Enter'], que: 'Confirmar la respuesta', donde: 'En Te pregunta' },
  { grupo: PREGUNTA, teclas: ['←'], tambien: ['Retroceso'], que: 'Volver a la pregunta anterior', donde: 'En Te pregunta' },
  { grupo: PREGUNTA, teclas: ['→'], que: 'Pasar a la pregunta siguiente', donde: 'En Te pregunta' },
  { grupo: PREGUNTA, teclas: ['1', '–', '6'], que: 'Elegir esa opción', donde: 'En Te pregunta' },
  { grupo: PREGUNTA, id: 'minimizar-preguntas', teclas: ['M'], que: 'Minimizar las preguntas', donde: 'En Te pregunta' },
  { grupo: PREGUNTA, teclas: ['Esc'], que: 'Cerrar las preguntas', donde: 'En Te pregunta' },

  { grupo: CAMBIOS, teclas: ['J'], tambien: ['↓'], que: 'Pasar al cambio siguiente', donde: 'En Cambios' },
  { grupo: CAMBIOS, teclas: ['K'], tambien: ['↑'], que: 'Pasar al cambio anterior', donde: 'En Cambios' },
  { grupo: CAMBIOS, id: 'comentar', teclas: ['Ctrl', 'Enter'], mod: true, que: 'Agregar el comentario', donde: 'Al comentar un cambio' },

  { grupo: TERMINAL, id: 'crear-terminal', teclas: ['Ctrl', 'Enter'], mod: true, que: 'Crear la terminal', donde: 'En Nueva terminal' },

  { grupo: BIBLIOTECA, teclas: ['/'], que: 'Buscar', donde: 'En la Biblioteca' },
  { grupo: BIBLIOTECA, teclas: ['J'], tambien: ['↓'], que: 'Mover la selección hacia abajo (K o ↑, hacia arriba; H L o ← →, a los costados)', donde: 'En la Biblioteca' },
  { grupo: BIBLIOTECA, teclas: ['Enter'], que: 'Abrir el archivo', donde: 'En la Biblioteca' },
  { grupo: BIBLIOTECA, teclas: ['Espacio'], que: 'Vista rápida', donde: 'En la Biblioteca' },
  { grupo: BIBLIOTECA, teclas: ['['], tambien: [']'], que: 'Archivo anterior / siguiente', donde: 'En la Biblioteca' },
  { grupo: BIBLIOTECA, teclas: ['F'], que: 'Pantalla completa', donde: 'En la Biblioteca' },
  { grupo: BIBLIOTECA, teclas: ['G'], que: 'Pasar de grilla a lista', donde: 'En la Biblioteca' },
  { grupo: BIBLIOTECA, teclas: ['1', '–', '9'], que: 'Filtrar por tipo de archivo', donde: 'En la Biblioteca' },
  { grupo: BIBLIOTECA, teclas: ['O'], que: 'Abrir en claude.ai', donde: 'En la Biblioteca' },
  { grupo: BIBLIOTECA, teclas: ['S'], que: 'Ir a la sesión del archivo', donde: 'En la Biblioteca' },
  { grupo: BIBLIOTECA, teclas: ['C'], que: 'Copiar la ruta', donde: 'En la Biblioteca' },
  { grupo: BIBLIOTECA, teclas: ['R'], que: 'Recargar el visor', donde: 'En la Biblioteca' },
  { grupo: BIBLIOTECA, teclas: ['Supr'], que: 'Quitar de la Biblioteca (pide confirmación)', donde: 'En la Biblioteca' },
  { grupo: BIBLIOTECA, teclas: ['?'], que: 'Ver esta lista de teclas', donde: 'En la Biblioteca' },

  { grupo: DIAGRAMA, teclas: ['F'], que: 'Pantalla completa', donde: 'En un diagrama' },
  { grupo: DIAGRAMA, teclas: ['+'], tambien: ['-'], que: 'Acercar / alejar (0 lo encaja)', donde: 'En un diagrama a pantalla completa' },
  { grupo: DIAGRAMA, teclas: ['←'], tambien: ['→'], que: 'Pasar al elemento anterior / siguiente', donde: 'En un diagrama' },

  { grupo: WINDOWS, teclas: [], que: 'Los atajos de la app de Windows se cambian desde el ícono de Colmena junto al reloj → Atajos → Cambiar atajos…', donde: 'En la app de Windows' },
]

export function gruposDeAtajos(lista: Atajo[] = ATAJOS): { grupo: string; items: Atajo[] }[] {
  const out: { grupo: string; items: Atajo[] }[] = []
  for (const a of lista) {
    const g = out.find((x) => x.grupo === a.grupo)
    if (g) g.items.push(a)
    else out.push({ grupo: a.grupo, items: [a] })
  }
  return out
}
