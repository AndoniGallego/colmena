export interface Hold {
  start(): void
  cancel(): void
  readonly active: boolean
}

/** "Mantener apretado": confirma solo si se sostiene `ms` sin soltar; soltar antes lo cancela. */
export function createHold(ms: number, onDone: () => void, onChange: (active: boolean) => void = () => {}): Hold {
  let timer: ReturnType<typeof setTimeout> | undefined
  let active = false
  const set = (v: boolean) => {
    if (active === v) return
    active = v
    onChange(v)
  }
  return {
    start() {
      if (active) return
      set(true)
      timer = setTimeout(() => {
        timer = undefined
        set(false)
        onDone()
      }, ms)
    },
    cancel() {
      clearTimeout(timer)
      timer = undefined
      set(false)
    },
    get active() {
      return active
    },
  }
}
