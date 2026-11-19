import { coverHues } from './biblioteca'

export const hueDe = (workspace: string) => coverHues(workspace || '·')[0]

/** "Tienda · Backend" → "Tienda · Back": the phone chip only has room for a hint of the name. */
export function nombreCorto(nombre: string): string {
  const parts = nombre.split(' · ').map((p) => p.trim()).filter(Boolean)
  if (parts.length < 2) return nombre.length > 12 ? `${nombre.slice(0, 11).trimEnd()}…` : nombre
  const head = parts[0].length > 8 ? parts[0].slice(0, 7).trimEnd() : parts[0]
  const tail = parts[1].length > 6 ? parts[1].slice(0, 4).trimEnd() : parts[1]
  return `${head} · ${tail}`
}
