import { ApiError } from './types'

export interface ComentarioBody {
  path: string
  lado: 'nuevo' | 'viejo'
  desde: number
  hasta: number
  fragmento: string
  texto: string
}

export interface ComentariosBody {
  id: string
  comentarios: ComentarioBody[]
}

export async function postComentariosDiff(sid: string, body: ComentariosBody): Promise<{ ok: boolean; enviados: number }> {
  let res: Response
  try {
    res = await fetch(`/api/sesiones/${encodeURIComponent(sid)}/cambios/comentarios`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'Se cortó la conexión con el servidor')
  }
  if (!res.ok) {
    let detail = res.status === 401 ? 'La sesión venció, volvé a entrar' : 'No pude mandar los comentarios'
    try {
      const d = await res.json()
      if (typeof d?.detail === 'string') detail = d.detail
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, detail)
  }
  const out = await res.json().catch(() => ({}))
  return { ok: true, enviados: typeof out?.enviados === 'number' ? out.enviados : 0 }
}
