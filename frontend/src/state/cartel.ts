import { reactive } from 'vue'

/** Demora del primer cartel con el mouse; el siguiente, si hay uno abierto o recién cerrado, sale sin demora. */
export const DEMORA_MS = 150
const CALIENTE_MS = 400

export const cartel = reactive({
  visible: false,
  nombre: '',
  desc: '',
  /** centro horizontal y borde de abajo del botón, en px de ventana */
  x: 0,
  y: 0,
})

let dueno: HTMLElement | null = null
let demora: ReturnType<typeof setTimeout> | undefined
let enfria: ReturnType<typeof setTimeout> | undefined
let caliente = false

function poner(el: HTMLElement, nombre: string, desc: string) {
  const r = el.getBoundingClientRect()
  Object.assign(cartel, { visible: true, nombre, desc, x: r.left + r.width / 2, y: r.bottom })
  dueno = el
}

export function mostrarCartel(el: HTMLElement, nombre: string, desc: string, enseguida: boolean) {
  clearTimeout(demora)
  clearTimeout(enfria)
  if (enseguida || cartel.visible || caliente) return poner(el, nombre, desc)
  demora = setTimeout(() => poner(el, nombre, desc), DEMORA_MS)
}

export function ocultarCartel(el: HTMLElement) {
  clearTimeout(demora)
  if (dueno !== el || !cartel.visible) return
  cartel.visible = false
  dueno = null
  caliente = true
  enfria = setTimeout(() => (caliente = false), CALIENTE_MS)
}

/** Refresca el texto si el botón dueño cambió (p. ej. Tema claro/oscuro). */
export function actualizarCartel(el: HTMLElement, nombre: string, desc: string) {
  if (dueno === el && cartel.visible) Object.assign(cartel, { nombre, desc })
}

export function reiniciarCartel() {
  clearTimeout(demora)
  clearTimeout(enfria)
  caliente = false
  dueno = null
  cartel.visible = false
}
