import { extOf } from './attachments'

const MIME_EXT: Record<string, string> = {
  'image/png': 'png',
  'image/jpeg': 'jpg',
  'image/gif': 'gif',
  'image/webp': 'webp',
  'image/heic': 'heic',
  'application/pdf': 'pdf',
  'text/plain': 'txt',
}

// Lo que el navegador inventa al pegar una captura: "image.png" o sin nombre.
const GENERIC = /^(image|imagen|blob|clipboard)?(\.[a-z0-9]+)?$/i

const pad = (n: number) => String(n).padStart(2, '0')

export function stamp(d: Date): string {
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
}

interface FileLike {
  name: string
  type: string
}

/** Archivo con nombre real se respeta; el genérico de una captura pasa a captura-AAAAMMDD-HHMMSS.ext. */
export function pastedName(file: FileLike, now: Date, n = 0): string {
  const name = file.name.trim()
  if (name && !GENERIC.test(name) && extOf(name)) return name
  const ext = MIME_EXT[file.type] ?? (extOf(name) || 'png')
  const base = file.type.startsWith('image/') || !file.type ? 'captura' : 'pegado'
  return `${base}-${stamp(now)}${n ? `-${n + 1}` : ''}.${ext}`
}

interface TransferLike {
  types?: ReadonlyArray<string>
  items?: ArrayLike<{ kind: string; getAsFile(): File | null }>
  files?: ArrayLike<File>
  getData?(format: string): string
}

export function filesFrom(dt: TransferLike | null | undefined, now = new Date()): File[] {
  if (!dt) return []
  let raw: File[] = []
  if (dt.items?.length) {
    for (const it of Array.from(dt.items)) {
      if (it.kind !== 'file') continue
      const f = it.getAsFile()
      if (f) raw.push(f)
    }
  }
  if (!raw.length && dt.files?.length) raw = Array.from(dt.files)
  let generic = 0
  return raw.map((f) => {
    const name = pastedName(f, now, generic)
    if (name === f.name) return f
    generic++
    return new File([f], name, { type: f.type, lastModified: f.lastModified })
  })
}

export const hasText = (dt: TransferLike | null | undefined) =>
  !!dt?.types?.includes('text/plain') && !!dt.getData?.('text/plain')

export const carriesFiles = (dt: TransferLike | null | undefined) => !!dt?.types?.includes('Files')
