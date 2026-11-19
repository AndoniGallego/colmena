<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { Voz } from '../state/voz'
import type { VozSnapshot } from '../lib/vozRecorder'
import { MAX_SECONDS, formatClock } from '../lib/voz'
import Icon from './Icon.vue'

const props = defineProps<{ voz: Voz }>()

const BARS = 44
const STEP_MS = 55

const snap = computed(() => props.voz.snap.value)
const open = computed(() => snap.value.phase !== 'idle')
// Al cerrarse, el contenido se queda hasta que termina de achicarse en vez de desaparecer de golpe.
const shown = ref<VozSnapshot>(snap.value)
watch(snap, (s) => {
  if (s.phase !== 'idle') shown.value = s
})

const secondsLeft = computed(() => Math.max(0, Math.ceil(MAX_SECONDS - shown.value.elapsed)))
const live = computed(() => {
  const s = snap.value
  if (s.phase === 'recording') return s.warn ? `Quedan ${secondsLeft.value} segundos` : 'Grabando'
  if (s.phase === 'requesting') return 'Esperando el permiso del micrófono'
  if (s.phase === 'transcribing') return s.preparing ? 'Preparando el modelo y transcribiendo' : 'Transcribiendo'
  if (s.phase === 'error' && s.error) return `${s.error.title} ${s.error.hint}`
  return ''
})

const canvas = ref<HTMLCanvasElement | null>(null)
const levels = new Array<number>(BARS).fill(0)
let raf = 0
let last = 0
let buffer: Uint8Array<ArrayBuffer> | null = null

function colors() {
  const cs = getComputedStyle(canvas.value!)
  return { bar: cs.getPropertyValue('--danger').trim() || '#ff7a66', dim: cs.getPropertyValue('--line-2').trim() || '#555' }
}

function draw(now: number) {
  const cv = canvas.value
  const meter = props.voz.meter.value
  if (!cv || !meter) return
  raf = requestAnimationFrame(draw)
  if (!buffer || buffer.length !== meter.analyser.fftSize) buffer = new Uint8Array(meter.analyser.fftSize)
  if (now - last >= STEP_MS) {
    last = now
    meter.analyser.getByteTimeDomainData(buffer)
    let sum = 0
    for (let i = 0; i < buffer.length; i++) {
      const v = (buffer[i] - 128) / 128
      sum += v * v
    }
    levels.push(Math.min(1, Math.sqrt(sum / buffer.length) * 3.2))
    levels.shift()
  }
  const dpr = window.devicePixelRatio || 1
  const w = cv.clientWidth
  const h = cv.clientHeight
  if (cv.width !== Math.round(w * dpr)) cv.width = Math.round(w * dpr)
  if (cv.height !== Math.round(h * dpr)) cv.height = Math.round(h * dpr)
  const g = cv.getContext('2d')!
  g.setTransform(dpr, 0, 0, dpr, 0, 0)
  g.clearRect(0, 0, w, h)
  const { bar, dim } = colors()
  const slot = w / BARS
  const bw = Math.max(2, Math.min(4, slot * 0.58))
  for (let i = 0; i < BARS; i++) {
    const v = levels[i]
    const bh = Math.max(3, v * h)
    g.fillStyle = v > 0.04 ? bar : dim
    g.globalAlpha = v > 0.04 ? 0.35 + 0.65 * (i / BARS) : 1
    g.beginPath()
    g.roundRect(i * slot + (slot - bw) / 2, (h - bh) / 2, bw, bh, bw / 2)
    g.fill()
  }
  g.globalAlpha = 1
}

function stopLoop() {
  cancelAnimationFrame(raf)
  raf = 0
}

watch(
  () => [props.voz.meter.value, canvas.value] as const,
  ([m, c]) => {
    stopLoop()
    levels.fill(0)
    if (m && c) raf = requestAnimationFrame(draw)
  },
  { flush: 'post' },
)
onBeforeUnmount(stopLoop)
</script>

<template>
  <div class="vwrap" :class="{ open }">
    <div class="vclip">
      <div class="vstrip" :class="[shown.phase, { warn: shown.warn }]" role="group" aria-label="Dictado por voz">
        <template v-if="shown.phase === 'recording'">
          <span class="dot" aria-hidden="true" />
          <canvas ref="canvas" class="wave" aria-hidden="true" />
          <span class="clock mono" aria-hidden="true">{{ formatClock(shown.elapsed) }}<i> / {{ formatClock(MAX_SECONDS) }}</i></span>
          <span v-if="shown.warn" class="left mono" aria-hidden="true">{{ secondsLeft }} s</span>
          <button type="button" class="x" aria-label="Cancelar la grabación" title="Cancelar (Esc)" @click.stop="voz.cancel()">
            <Icon name="close" :size="14" />
          </button>
        </template>
        <template v-else-if="shown.phase === 'requesting'">
          <span class="spin" aria-hidden="true" />
          <span class="msg">Esperando el permiso del micrófono…</span>
          <button type="button" class="x" aria-label="Cancelar" @click.stop="voz.cancel()"><Icon name="close" :size="14" /></button>
        </template>
        <template v-else-if="shown.phase === 'transcribing'">
          <span class="dots" aria-hidden="true"><i /><i /><i /></span>
          <span class="msg">
            {{ shown.preparing ? 'Preparando el modelo…' : 'Transcribiendo…' }}
            <small v-if="shown.preparing">La primera vez tarda unos segundos más.</small>
          </span>
          <button type="button" class="x" aria-label="Cancelar la transcripción" title="Cancelar" @click.stop="voz.cancel()">
            <Icon name="close" :size="14" />
          </button>
        </template>
        <template v-else-if="shown.phase === 'error' && shown.error">
          <Icon name="warn" :size="15" class="warn-ic" />
          <span class="msg">
            {{ shown.error.title }}
            <small>{{ shown.error.hint }}</small>
          </span>
          <button type="button" class="retry" @click.stop="voz.start()">Reintentar</button>
          <button type="button" class="x" aria-label="Cerrar el aviso" @click.stop="voz.dismiss()"><Icon name="close" :size="14" /></button>
        </template>
      </div>
    </div>
    <span class="sr-only" role="status" aria-live="polite">{{ live }}</span>
  </div>
</template>

<style scoped>
.vwrap {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.42s var(--ease-out);
}
.vwrap.open {
  grid-template-rows: 1fr;
}
.vclip {
  min-height: 0;
  overflow: hidden;
}
.vstrip {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  margin: 0 0 4px;
  padding: 6px 6px 6px 14px;
  border-radius: var(--r-lg);
  background: var(--surface);
  border: 1px solid var(--line-2);
  font-size: 13px;
  color: var(--text-2);
  transition: border-color 0.3s, background 0.3s;
}
.vstrip.recording {
  border-color: color-mix(in srgb, var(--danger) 45%, transparent);
  background: linear-gradient(90deg, var(--danger-soft), transparent 70%), var(--surface);
}
.vstrip.transcribing,
.vstrip.requesting {
  border-color: var(--accent-line);
}
.vstrip.error {
  border-color: color-mix(in srgb, var(--danger) 55%, transparent);
}
.dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--danger);
  animation: blink 1.2s ease-in-out infinite;
}
.wave {
  flex: 1;
  min-width: 0;
  height: 28px;
}
.clock {
  flex: none;
  font-size: 13px;
  color: var(--text);
  font-variant-numeric: tabular-nums;
}
.clock i {
  font-style: normal;
  color: var(--text-4);
}
.left {
  flex: none;
  padding: 2px 7px;
  border-radius: var(--r-pill);
  font-size: 11px;
  background: var(--st-blocked-soft);
  color: var(--st-blocked);
  animation: pop 0.4s var(--spring);
}
.msg {
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 1px;
  line-height: 1.35;
  color: var(--text);
}
.msg small {
  font-size: 12px;
  color: var(--text-3);
}
.warn-ic {
  flex: none;
  color: var(--danger);
}
.x,
.retry {
  flex: none;
  height: 32px;
  border-radius: var(--r-md);
  color: var(--text-3);
  transition: color 0.2s, background 0.2s, scale 0.3s var(--spring);
}
.x {
  width: 32px;
  display: grid;
  place-items: center;
}
.retry {
  padding: 0 12px;
  font-size: var(--t-md);
  color: var(--text);
  background: var(--surface-2);
}
.x:hover,
.retry:hover {
  color: var(--text);
  background: var(--surface-hover);
}
.x:active,
.retry:active {
  scale: var(--press-scale);
}
.spin {
  flex: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 1.5px solid var(--accent);
  border-right-color: transparent;
  animation: spin 0.8s linear infinite;
}
.dots {
  flex: none;
  display: flex;
  gap: 4px;
}
.dots i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  animation: bounce 1.1s ease-in-out infinite;
}
.dots i:nth-child(2) { animation-delay: 0.15s; }
.dots i:nth-child(3) { animation-delay: 0.3s; }
@keyframes blink {
  50% { opacity: 0.25; }
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
@keyframes bounce {
  0%, 70%, 100% { transform: translateY(0); opacity: 0.5; }
  35% { transform: translateY(-4px); opacity: 1; }
}
@keyframes pop {
  from { transform: scale(0.6); opacity: 0; }
}
@media (prefers-reduced-motion: reduce) {
  .dot, .dots i { animation: none; }
  .dots i { opacity: 0.8; }
}
:root[data-motion='soft'] .dot,
:root[data-motion='soft'] .dots i {
  animation: none;
}
</style>
