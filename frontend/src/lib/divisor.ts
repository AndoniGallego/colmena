import { computed, ref } from 'vue'

export interface Limites {
  min: number
  max: number
}

export interface OpcionesAncho {
  /** Clave de localStorage, por dispositivo. */
  clave: string
  /** Ancho mínimo del panel que se redimensiona. */
  min: number
  /** Lo que tiene que quedarle, como mínimo, al panel del otro lado. */
  minResto: number
  /** Ancho por defecto según el ancho disponible. */
  porDefecto: (contenedor: number) => number
  /** Paso del teclado en px. */
  paso?: number
}

export function limitesDe(contenedor: number, min: number, minResto: number): Limites {
  return { min, max: Math.max(min, Math.round(contenedor - minResto)) }
}

export function clampAncho(v: number, { min, max }: Limites): number {
  return Math.round(Math.min(max, Math.max(min, v)))
}

/** Ancho tras una tecla; null si la tecla no le corresponde al divisor. `sentido` -1 cuando el panel está a la derecha. */
export function anchoPorTecla(tecla: string, actual: number, lim: Limites, paso = 24, sentido: 1 | -1 = 1): number | null {
  switch (tecla) {
    case 'ArrowRight':
      return clampAncho(actual + paso * sentido, lim)
    case 'ArrowLeft':
      return clampAncho(actual - paso * sentido, lim)
    case 'Home':
      return lim.min
    case 'End':
      return lim.max
    default:
      return null
  }
}

export function cargarAncho(clave: string): number | null {
  try {
    const raw = localStorage.getItem(clave)
    if (raw === null) return null
    const n = Number(raw)
    return Number.isFinite(n) && n > 0 ? Math.round(n) : null
  } catch {
    return null
  }
}

export function guardarAncho(clave: string, v: number | null) {
  try {
    if (v === null) localStorage.removeItem(clave)
    else localStorage.setItem(clave, String(Math.round(v)))
  } catch {
    /* sin storage: el ancho vive solo en memoria */
  }
}

/**
 * Ancho de un panel redimensionable. Lo guardado es la intención del usuario;
 * lo que se muestra siempre queda dentro de los límites del contenedor actual.
 */
export function useAncho(o: OpcionesAncho) {
  const paso = o.paso ?? 24
  const contenedor = ref(0)
  const guardado = ref<number | null>(cargarAncho(o.clave))
  const provisorio = ref<number | null>(null)

  const limites = computed(() => limitesDe(contenedor.value, o.min, o.minResto))
  const porDefecto = computed(() => clampAncho(o.porDefecto(contenedor.value), limites.value))
  const ancho = computed(() => clampAncho(provisorio.value ?? guardado.value ?? o.porDefecto(contenedor.value), limites.value))

  /** Muestra un ancho sin guardarlo (arrastre, animaciones). */
  function ver(v: number) {
    provisorio.value = clampAncho(v, limites.value)
  }
  /** Fija y guarda el ancho. Sin argumento consolida lo que se está mostrando. */
  function fijar(v: number = ancho.value) {
    const n = clampAncho(v, limites.value)
    provisorio.value = null
    guardado.value = n
    guardarAncho(o.clave, n)
  }
  /** Vuelve al ancho por defecto y olvida lo guardado, así sigue la proporción al cambiar la ventana. */
  function restablecer() {
    provisorio.value = null
    guardado.value = null
    guardarAncho(o.clave, null)
  }
  function teclado(tecla: string, sentido: 1 | -1 = 1): boolean {
    const n = anchoPorTecla(tecla, ancho.value, limites.value, paso, sentido)
    if (n === null) return false
    fijar(n)
    return true
  }

  return { contenedor, ancho, limites, porDefecto, ver, fijar, restablecer, teclado }
}

export type Ancho = ReturnType<typeof useAncho>
