import { onBeforeUnmount, ref } from 'vue'

const now = ref(Date.now())
let users = 0
let timer: ReturnType<typeof setInterval> | undefined

/** Shared ticking clock (30 s) for relative timestamps. */
export function useNow() {
  if (users++ === 0) timer = setInterval(() => (now.value = Date.now()), 30_000)
  onBeforeUnmount(() => {
    if (--users === 0) clearInterval(timer)
  })
  return now
}

export function ago(iso: string | null | undefined, at: number): string {
  if (!iso) return ''
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return ''
  const s = Math.max(0, Math.round((at - t) / 1000))
  if (s < 45) return 'recién'
  const m = Math.round(s / 60)
  if (m < 60) return `hace ${m} min`
  const h = Math.floor(m / 60)
  if (h < 24) return m % 60 && h < 6 ? `hace ${h} h ${m % 60} min` : `hace ${h} h`
  const d = Math.floor(h / 24)
  return d === 1 ? 'ayer' : `hace ${d} días`
}

export function clock(at: number): string {
  return new Date(at).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' })
}

export function fechaLarga(iso: string | null | undefined, opts?: Intl.DateTimeFormatOptions): string {
  if (!iso) return ''
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return ''
  return new Date(t).toLocaleString('es-AR', opts ?? {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
