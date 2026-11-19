/** Medición liviana de LCP e INP con PerformanceObserver. Solo se llama desde main.ts en modo dev. */
export function medirVitalsDev(log: (...a: unknown[]) => void = console.log): void {
  if (typeof PerformanceObserver === 'undefined') return
  const observar = (type: string, cb: (e: PerformanceEntry[]) => void, extra: object = {}) => {
    try {
      new PerformanceObserver((l) => cb(l.getEntries())).observe({ type, buffered: true, ...extra } as PerformanceObserverInit)
    } catch {
      /* el navegador no soporta ese tipo de entrada */
    }
  }
  observar('largest-contentful-paint', (es) => {
    const e = es[es.length - 1]
    if (e) log('[vitals] LCP', Math.round(e.startTime), 'ms')
  })
  let peor = 0
  observar(
    'event',
    (es) => {
      for (const e of es as PerformanceEventTiming[]) {
        if (!e.interactionId || e.duration <= peor) continue
        peor = e.duration
        log('[vitals] INP (peor interaccion)', Math.round(peor), 'ms', e.name)
      }
    },
    { durationThreshold: 40 },
  )
}
