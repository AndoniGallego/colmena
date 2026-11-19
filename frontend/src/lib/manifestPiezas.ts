export interface Atajo {
  name: string
  short_name?: string
  description?: string
  url: string
}

export interface ManifestPieza {
  shortcuts?: Atajo[]
}

/** Parsea el manifest.json de una pieza; si es inválido, el error dice de qué pieza es. */
export function leerManifestPieza(pieza: string, texto: string): ManifestPieza {
  try {
    return JSON.parse(texto)
  } catch (e) {
    throw new Error(`manifest de pieza inválido (${pieza}/manifest.json): ${(e as Error).message}`)
  }
}

const esAtajo = (a: unknown, scope: string): a is Atajo => {
  const x = a as Partial<Atajo> | null
  return !!x && typeof x.name === 'string' && x.name.length > 0 && typeof x.url === 'string' && x.url.startsWith(scope)
}

/** Suma al manifest base los shortcuts que declaran las piezas montadas; sin piezas queda igual. */
export function fusionarManifest<T extends { scope?: string }>(
  base: T,
  piezas: ManifestPieza[],
  avisar: (m: string) => void = console.warn,
): T & { shortcuts?: Atajo[] } {
  const scope = base.scope ?? '/'
  const shortcuts: Atajo[] = []
  for (const p of piezas) {
    for (const a of Array.isArray(p.shortcuts) ? p.shortcuts : []) {
      if (esAtajo(a, scope)) shortcuts.push(a)
      else avisar(`manifest de pieza: shortcut inválido descartado (${JSON.stringify(a)})`)
    }
  }
  return shortcuts.length ? { ...base, shortcuts } : base
}
