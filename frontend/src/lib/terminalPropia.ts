const TERMINAL_PROPIA = /^g\d+(:[pt]\d+)?$/

export function esTerminalPropia(paneId: string | null | undefined): boolean {
  return typeof paneId === 'string' && TERMINAL_PROPIA.test(paneId)
}

const SESION_TERMINAL = /^g\d+:p\d+$/

export function esSesionTerminal(paneId: string | null | undefined): boolean {
  return typeof paneId === 'string' && SESION_TERMINAL.test(paneId)
}
