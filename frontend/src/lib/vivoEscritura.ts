export const TECLAS_BARRA = [
  'esc',
  'tab',
  'izquierda',
  'arriba',
  'abajo',
  'derecha',
  'enter',
  'ctrl-c',
  '1',
  '2',
  '3',
] as const

export type TeclaBarra = (typeof TECLAS_BARRA)[number]

export function mensajeEntrada(token: string, texto: string): { tipo: 'entrada'; token: string; texto: string } {
  return { tipo: 'entrada', token, texto }
}

export function mensajeTecla(token: string, tecla: TeclaBarra): { tipo: 'tecla'; token: string; tecla: TeclaBarra } {
  return { tipo: 'tecla', token, tecla }
}

export function formatoVentana(segundos: number): string {
  const s = Math.max(0, Math.floor(segundos))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/** Modo escritura encendido: si la ventana ya está abierta, no hace falta PIN otra vez. */
export function debeAbrirPin(ventanaAbierta: boolean, activarEscritura: boolean): boolean {
  return activarEscritura && !ventanaAbierta
}

export function manejarErrorEscritura(codigo: 'ventana' | 'apagado' | 'caido'): {
  soloLectura: boolean
  forget: boolean
  aviso: string
} {
  if (codigo === 'ventana') {
    return { soloLectura: true, forget: true, aviso: 'Se cerró la ventana de escritura' }
  }
  if (codigo === 'apagado') {
    return { soloLectura: true, forget: false, aviso: 'La escritura remota está apagada' }
  }
  return { soloLectura: true, forget: false, aviso: 'No pude escribir en la terminal' }
}

const ROTULOS: Record<TeclaBarra, string> = {
  esc: 'Esc',
  tab: 'Tab',
  izquierda: '←',
  arriba: '↑',
  abajo: '↓',
  derecha: '→',
  enter: 'Enter',
  'ctrl-c': 'Ctrl-C',
  '1': '1',
  '2': '2',
  '3': '3',
}

export function rotuloTecla(t: TeclaBarra): string {
  return ROTULOS[t]
}

export const MAX_TANDA = 4096

/** Agrupa lo que tipea xterm para no mandar un mensaje por tecla (el servidor tiene tope de mensajes). */
export function agrupadorEntrada(enviar: (texto: string) => void, ms = 30): { push(t: string): void; cancelar(): void } {
  let buf = ''
  let timer: ReturnType<typeof setTimeout> | null = null
  const vaciar = () => {
    timer = null
    for (let i = 0; i < buf.length; i += MAX_TANDA) enviar(buf.slice(i, i + MAX_TANDA))
    buf = ''
  }
  return {
    push(t: string) {
      buf += t
      if (timer === null) timer = setTimeout(vaciar, ms)
    },
    cancelar() {
      if (timer !== null) clearTimeout(timer)
      timer = null
      buf = ''
    },
  }
}
