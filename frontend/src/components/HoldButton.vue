<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { createHold } from '../lib/hold'
import { HOLD_MS } from '../lib/limpieza'
import { haptic } from '../motion'

const props = withDefaults(defineProps<{ disabled?: boolean; ms?: number }>(), { ms: HOLD_MS })
const emit = defineEmits<{ confirm: [] }>()
const segundos = computed(() => `${props.ms / 1000}`.replace('.', ','))

const holding = ref(false)
const hold = createHold(
  props.ms,
  () => {
    haptic([12, 40, 20])
    emit('confirm')
  },
  (v) => (holding.value = v),
)
onBeforeUnmount(() => hold.cancel())

const down = (e: PointerEvent) => {
  if (props.disabled || e.button > 0) return
  ;(e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId)
  hold.start()
  haptic(6)
}
const key = (e: KeyboardEvent) => {
  if ((e.key !== 'Enter' && e.key !== ' ') || e.repeat) return
  e.preventDefault()
  if (!props.disabled) hold.start()
}
const keyUp = (e: KeyboardEvent) => {
  if (e.key === 'Enter' || e.key === ' ') hold.cancel()
}
</script>

<template>
  <button
    type="button"
    class="hold"
    :class="{ holding }"
    :disabled="disabled"
    :style="{ '--hold-ms': `${ms}ms` }"
    @pointerdown="down"
    @pointerup="hold.cancel"
    @pointercancel="hold.cancel"
    @lostpointercapture="hold.cancel"
    @keydown="key"
    @keyup="keyUp"
    @blur="hold.cancel"
    @contextmenu.prevent
  >
    <svg class="ring" aria-hidden="true" preserveAspectRatio="none">
      <rect x="1.5" y="1.5" rx="11" ry="11" pathLength="1" />
    </svg>
    <i class="bar" aria-hidden="true" />
    <span class="txt"><slot /></span>
    <span class="hint">{{ holding ? 'Seguí apretando…' : `Mantené apretado ${segundos} s` }}</span>
  </button>
</template>

<style scoped>
.hold {
  position: relative;
  display: grid;
  place-items: center;
  gap: 1px;
  min-height: 52px;
  padding: 7px 18px;
  border-radius: var(--r-lg);
  background: var(--danger);
  color: var(--danger-ink);
  font-weight: 600;
  font-size: 14px;
  overflow: hidden;
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
  -webkit-touch-callout: none;
  transition: scale 0.3s var(--spring), box-shadow 0.25s, background 0.2s, opacity 0.2s;
}
.hold:disabled {
  background: var(--surface-2);
  color: var(--text-4);
  box-shadow: inset 0 0 0 1px var(--line-2);
  cursor: not-allowed;
}
.hold:not(:disabled).holding {
  scale: 0.975;
  box-shadow: 0 0 0 4px var(--danger-soft), 0 10px 30px -10px var(--danger);
}
.txt {
  position: relative;
  z-index: 1;
}
.hint {
  position: relative;
  z-index: 1;
  font-size: 11px;
  font-weight: 500;
  opacity: 0.78;
}
.ring {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  overflow: visible;
}
.ring rect {
  width: calc(100% - 3px);
  height: calc(100% - 3px);
  fill: none;
  stroke: var(--danger-ink);
  stroke-width: 3;
  stroke-linecap: round;
  stroke-dasharray: 1;
  stroke-dashoffset: 1;
  opacity: 0;
  transition: stroke-dashoffset 0.18s ease-out, opacity 0.18s;
}
.holding .ring rect {
  stroke-dashoffset: 0;
  opacity: 0.95;
  transition: stroke-dashoffset var(--hold-ms) linear, opacity 0.1s;
}
.bar {
  display: none;
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 4px;
  background: var(--danger-ink);
  transform: scaleX(0);
  transform-origin: left;
  transition: transform 0.15s ease-out;
}
.holding .bar {
  transform: scaleX(1);
  transition: transform var(--hold-ms) linear;
}
:root[data-motion='soft'] .ring { display: none; }
:root[data-motion='soft'] .bar { display: block; }
@media (prefers-reduced-motion: reduce) {
  .ring { display: none; }
  .bar { display: block; }
}
</style>
