// Un solo observador para todas las tarjetas: las que salen de la vista quedan con data-fuera
// y el CSS pausa sus animaciones (no se paga batería por lo que no se ve).
let observador: IntersectionObserver | null = null

function compartido(): IntersectionObserver | null {
  if (typeof IntersectionObserver === 'undefined') return null
  observador ??= new IntersectionObserver(
    (entries) => {
      for (const e of entries) e.target.toggleAttribute('data-fuera', !e.isIntersecting)
    },
    { rootMargin: '200px 0px' },
  )
  return observador
}

export function observarFueraDeVista(el: Element): () => void {
  const io = compartido()
  if (!io) return () => {}
  io.observe(el)
  return () => {
    io.unobserve(el)
    el.removeAttribute('data-fuera')
  }
}
