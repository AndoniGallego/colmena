const esObjeto = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)

/** Igualdad estructural: devuelve `prev` si `next` es igual; si no, un valor nuevo que reutiliza las ramas iguales de `prev`. */
export function compartir<T>(prev: unknown, next: T): T {
  if (prev === next) return prev as T
  if (Array.isArray(prev) && Array.isArray(next)) {
    const out = next.map((x, i) => compartir(prev[i], x))
    return (prev.length === next.length && out.every((x, i) => x === prev[i]) ? prev : out) as T
  }
  if (esObjeto(prev) && esObjeto(next)) {
    const keys = Object.keys(next)
    const out: Record<string, unknown> = {}
    let igual = keys.length === Object.keys(prev).length
    for (const k of keys) {
      out[k] = compartir(prev[k], next[k])
      if (out[k] !== prev[k] || !(k in prev)) igual = false
    }
    return (igual ? prev : out) as T
  }
  return next
}
