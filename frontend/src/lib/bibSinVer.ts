export type ItemSesion = { id: string; session_id: string | null }
/** id del ítem → sesión de donde salió. */
export type SinVer = Map<string, string | null>

export function sumarSinVer(sinVer: SinVer, items: ItemSesion[], sesionAbierta: string | null): SinVer {
  const out = new Map(sinVer)
  for (const it of items) if (!sesionAbierta || it.session_id !== sesionAbierta) out.set(it.id, it.session_id)
  return out
}

export function verSesion(sinVer: SinVer, sesion: string): SinVer {
  return new Map([...sinVer].filter(([, s]) => s !== sesion))
}

export function verItem(sinVer: SinVer, id: string): SinVer {
  if (!sinVer.has(id)) return sinVer
  const out = new Map(sinVer)
  out.delete(id)
  return out
}
