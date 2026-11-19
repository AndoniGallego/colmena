/** Si este cliente Colmena debe abrir la terminal al recibir abrir_terminal por SSE. */
export function debeAbrirTerminalLocal(ctx: { presenciaActiva: boolean; esEscritorio: boolean }): boolean {
  return ctx.presenciaActiva && ctx.esEscritorio
}

/** Tras abrir TerminalVivo con pedirPin: mostrar el sheet solo si la ventana de escritura está cerrada. */
export function debeMostrarPinAlAbrir(pedirPin: boolean, ventanaAbierta: boolean): boolean {
  return pedirPin && !ventanaAbierta
}
