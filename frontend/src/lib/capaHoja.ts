export type EstiloHoja = Record<string, string>

/** Estilo de una hoja inferior: alto del teclado del celu y, si va sobre otra capa, su z-index. */
export function estiloHoja(teclado: EstiloHoja | undefined, capa: number | undefined): EstiloHoja | undefined {
  if (capa === undefined) return teclado
  return { ...(teclado ?? {}), zIndex: String(capa) }
}
