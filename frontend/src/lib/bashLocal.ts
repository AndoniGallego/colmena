export interface BashLocal {
  tipo: 'comando' | 'salida'
  texto: string
  error: string
}

const COMANDO = /^\s*<bash-input>([\s\S]*)<\/bash-input>\s*$/
const SALIDA = /^\s*<bash-stdout>([\s\S]*?)<\/bash-stdout>\s*(?:<bash-stderr>([\s\S]*?)<\/bash-stderr>)?\s*$/

/** Comando corrido con `!` en Claude Code y su salida, que el transcript guarda como mensajes del usuario. */
export function bashLocal(text: string): BashLocal | null {
  const c = COMANDO.exec(text)
  if (c) return { tipo: 'comando', texto: c[1].trim(), error: '' }
  const s = SALIDA.exec(text)
  if (s) return { tipo: 'salida', texto: s[1].replace(/\s+$/, ''), error: (s[2] ?? '').trim() }
  return null
}
