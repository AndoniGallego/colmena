<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import type { AgentCtx } from '../api/types'
import { gsap, isSoft, useGsap } from '../motion'
import RollingNumber from './RollingNumber.vue'

const props = defineProps<{ ctx: AgentCtx }>()
const { run } = useGsap()
const root = ref<HTMLElement | null>(null)
const svg = ref<SVGSVGElement | null>(null)
const arc = ref<SVGCircleElement | null>(null)

const span = (pct: number) => `0% ${Math.max(0, Math.min(100, pct))}%`

onMounted(() => {
  if (arc.value) gsap.set(arc.value, { drawSVG: span(props.ctx.pct) })
})

watch(
  () => props.ctx.pct,
  (v, o) => {
    if (!arc.value) return
    if (isSoft()) {
      gsap.set(arc.value, { drawSVG: span(v) })
      if (root.value) run(() => gsap.fromTo(root.value, { opacity: 0.35 }, { opacity: 1, duration: 0.18 }))
      return
    }
    run(() => {
      gsap.to(arc.value, { drawSVG: span(v), duration: 0.6, ease: 'orq.spring', overwrite: 'auto' })
      // Bajar solo pasa al compactar: el anillo se vacía con un respiro.
      if (v < o && svg.value) gsap.fromTo(svg.value, { scale: 1 }, { keyframes: { scale: [1, 0.85, 1] }, duration: 0.5, ease: 'power2.inOut' })
    })
  },
)
</script>

<template>
  <span ref="root" class="ctx" :aria-label="`Contexto al ${ctx.pct}%`">
    <svg ref="svg" class="ring" width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <circle class="track" cx="7" cy="7" r="5.5" />
      <circle ref="arc" class="arc" cx="7" cy="7" r="5.5" transform="rotate(-90 7 7)" />
    </svg>
    <span class="num mono"><RollingNumber :value="ctx.pct" />%</span>
  </span>
</template>

<style scoped>
.ctx {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex: none;
  color: var(--text-3);
}
.ring {
  flex: none;
  overflow: visible;
}
.track,
.arc {
  stroke-width: 2;
  fill: none;
}
.track {
  stroke: var(--line-2);
}
.arc {
  stroke: var(--text-3);
  stroke-linecap: round;
}
.num {
  display: inline-flex;
  font-size: 11px;
  line-height: 14px;
  font-variant-numeric: tabular-nums;
}
</style>
