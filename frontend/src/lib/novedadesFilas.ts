/** Referencia de sesión al final de una fila inyectada por el servidor. */
export type RefNovedad = { pane_id?: string; session_id?: string }

const REF = / ⟦sesión:([^|]+)(?:\|sid=([^⟧]*))?⟧$/

export function parseRefNovedad(fila: string): RefNovedad | null {
  const m = REF.exec(fila)
  if (!m) return null
  const pane = m[1]?.trim()
  const sid = m[2]?.trim()
  const out: RefNovedad = {}
  if (pane && pane !== '?') out.pane_id = pane
  if (sid) out.session_id = sid
  return out.pane_id || out.session_id ? out : null
}

export function quitarRefNovedad(fila: string): string {
  return fila.replace(REF, '').trim()
}

export type FilaNovedad = { texto: string; ref: RefNovedad | null }

export function parseFilasNovedades(filas: string[]): FilaNovedad[] {
  return filas.map((f) => {
    const ref = parseRefNovedad(f)
    return { texto: quitarRefNovedad(f), ref }
  })
}

/** Devuelve session_id si esa sesión está en el tablero actual. */
export function sessionEnTablero(
  board: { workspaces?: { tabs?: { agents?: { pane_id?: string; session_id?: string | null }[] }[] }[] } | null,
  ref: RefNovedad | null,
): string | null {
  if (!board || !ref) return null
  if (ref.session_id) {
    for (const ws of board.workspaces ?? []) {
      for (const tab of ws.tabs ?? []) {
        for (const a of tab.agents ?? []) {
          if (a.session_id === ref.session_id) return a.session_id
        }
      }
    }
  }
  if (ref.pane_id) {
    for (const ws of board.workspaces ?? []) {
      for (const tab of ws.tabs ?? []) {
        for (const a of tab.agents ?? []) {
          if (a.pane_id === ref.pane_id && a.session_id) return a.session_id
        }
      }
    }
  }
  return null
}
