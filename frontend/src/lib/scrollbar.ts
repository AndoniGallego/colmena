/** Ancho real de la barra de scroll (0 en celu, donde se superpone al contenido). */
export function medirBarraScroll(doc: Document): number {
  const d = doc.createElement('div')
  d.style.cssText = 'position:absolute;top:-9999px;width:100px;height:100px;overflow:scroll;'
  doc.body.appendChild(d)
  const w = Math.max(0, d.offsetWidth - d.clientWidth)
  d.remove()
  return w
}

export function aplicarBarraScroll(doc: Document): void {
  doc.documentElement.style.setProperty('--sbw', `${medirBarraScroll(doc)}px`)
}
