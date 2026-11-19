export interface Draft {
  t: string
  ts: number
}
export type Drafts = Record<string, Draft>

export const DRAFT_MAX_CHARS = 8000
export const DRAFT_MAX_AGE_MS = 7 * 24 * 3600 * 1000
export const DRAFT_MAX_KEYS = 50

export const sessionDraft = (paneId: string) => `s:${paneId}`

function prune(all: Drafts, now: number): Drafts {
  const fresh = Object.entries(all).filter(([, d]) => d && typeof d.t === 'string' && now - d.ts < DRAFT_MAX_AGE_MS)
  fresh.sort((a, b) => b[1].ts - a[1].ts)
  return Object.fromEntries(fresh.slice(0, DRAFT_MAX_KEYS))
}

export function getDraft(all: Drafts, key: string, now = Date.now()): string {
  const d = all[key]
  return d && typeof d.t === 'string' && now - d.ts < DRAFT_MAX_AGE_MS ? d.t : ''
}

export function putDraft(all: Drafts, key: string, text: string, now = Date.now()): Drafts {
  const next = { ...all }
  if (!text.trim()) delete next[key]
  else next[key] = { t: text.slice(0, DRAFT_MAX_CHARS), ts: now }
  return prune(next, now)
}
