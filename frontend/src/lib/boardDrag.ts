/** Desplazamiento Y de la tarjeta levantada respecto al punto de agarre. */
export function deltaArrastreY(clientY: number, startClientY: number): number {
  return clientY - startClientY
}

/** Índices de tarjetas que se corren para abrir hueco (excluye la levantada). */
export function indicesCorrimientoArrastre(desde: number, hasta: number, total: number): number[] {
  if (desde === hasta || desde < 0 || hasta < 0 || desde >= total || hasta >= total) return []
  const out: number[] = []
  if (hasta > desde) {
    for (let i = desde + 1; i <= hasta; i++) out.push(i)
  } else {
    for (let i = hasta; i < desde; i++) out.push(i)
  }
  return out
}

/** px que corre una tarjeta en índice i; step = alto de tarjeta + gap. */
export function corrimientoPx(desde: number, hasta: number, indice: number, step: number): number {
  if (desde === hasta) return 0
  if (hasta > desde && indice > desde && indice <= hasta) return -step
  if (hasta < desde && indice >= hasta && indice < desde) return step
  return 0
}
