interface Area {
  scrollHeight: number
  style: { height: string; minHeight: string }
  parentElement: { offsetHeight: number; style: { minHeight: string } } | null
}

/**
 * Ajusta el alto del textarea a su contenido. Para medir hay que colapsarlo y eso fuerza un layout
 * con el composer más bajo: el chat de arriba se estira, el navegador recorta su scroll y al volver a crecer queda
 * despegado del fondo sin que ningún ResizeObserver se entere. Fijar el alto del contenedor mientras se mide lo evita.
 * Se mide colapsado a 0 (con auto se estiraría al alto de la fila fijada) y el resultado va como min-height, así el
 * textarea se sigue estirando a la fila como antes.
 */
export function autosizeArea(el: Area, max: number) {
  const box = el.parentElement
  if (box) box.style.minHeight = `${box.offsetHeight}px`
  el.style.minHeight = ''
  el.style.height = '0px'
  const h = Math.min(el.scrollHeight, max)
  el.style.height = ''
  el.style.minHeight = `${h}px`
  if (box) box.style.minHeight = ''
}
