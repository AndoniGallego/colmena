export const MAX_FILES = 5
export const MAX_BYTES = 20 * 1024 * 1024
export const ACCEPT = 'image/*,application/pdf,.txt,.md,.log,.json,.csv,.yaml,.yml'

export type AttachKind = 'image' | 'pdf' | 'text'

const IMAGE = new Set(['png', 'jpg', 'jpeg', 'webp', 'gif', 'heic'])
const TEXT = new Set(['txt', 'md', 'log', 'json', 'csv', 'yaml', 'yml'])

export const extOf = (name: string) => (name.includes('.') ? name.slice(name.lastIndexOf('.') + 1).toLowerCase() : '')

export function kindOf(name: string): AttachKind | null {
  const ext = extOf(name)
  if (IMAGE.has(ext)) return 'image'
  if (ext === 'pdf') return 'pdf'
  return TEXT.has(ext) ? 'text' : null
}

export function checkFile(file: { name: string; size: number }, count: number): string | null {
  if (count >= MAX_FILES) return `Máximo ${MAX_FILES} adjuntos por mensaje`
  if (!kindOf(file.name)) return 'Solo imágenes, PDF o texto (txt, md, log, json, csv, yaml)'
  if (file.size === 0) return 'El archivo está vacío'
  return file.size > MAX_BYTES ? 'Pesa más de 20 MB' : null
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1).replace('.0', '')} MB`
}

let srcOf = (id: string) => `/api/uploads/${encodeURIComponent(id)}`
export const uploadSrc = (id: string) => srcOf(id)
export const setUploadSrc = (fn: (id: string) => string) => (srcOf = fn)

const ID = String.raw`\d{8}-\d{6}-[a-z0-9-]{1,70}\.[a-z0-9]{2,4}`
const ID_ONLY = new RegExp(`^${ID}$`)
export const isUploadId = (id: string) => ID_ONLY.test(id)
const WRAPPED = new RegExp(String.raw`\s*\(Adjunto: [^)]*?/(${ID})\)`, 'g')
const BARE = new RegExp(String.raw`^Te paso ((?:\S*/${ID}(?:, )?)+)$`)

/** The server writes attachments into the text as paths; the thread shows them as thumbnails instead. */
export function splitAttachments(raw: string): { text: string; ids: string[]; images: number } {
  const ids: string[] = []
  let text = raw
  const bare = BARE.exec(raw.trim())
  if (bare) {
    for (const m of bare[1].matchAll(new RegExp(`/(${ID})`, 'g'))) ids.push(m[1])
    text = ''
  } else {
    text = raw.replace(WRAPPED, (_, id) => (ids.push(id), ''))
  }
  const lines = text.split('\n')
  const images = lines.filter((l) => l.trim() === '[imagen]').length
  return { text: lines.filter((l) => l.trim() !== '[imagen]').join('\n').trim(), ids, images }
}

export const kindFromId = (id: string): AttachKind => kindOf(id) ?? 'text'

export const attachmentLabel = (id: string) => id.replace(/^\d{8}-\d{6}-/, '')
