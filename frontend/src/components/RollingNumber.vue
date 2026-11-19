<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { gsap, isSoft, useGsap } from '../motion'

const props = defineProps<{ value: number }>()
const { run } = useGsap()
const cur = ref(props.value)
const prev = ref<number | null>(null)
const nowEl = ref<HTMLElement | null>(null)
const prevEl = ref<HTMLElement | null>(null)
let tl: gsap.core.Timeline | null = null

watch(
  () => props.value,
  async (v, o) => {
    tl?.progress(1)
    prev.value = o
    cur.value = v
    await nextTick()
    if (!nowEl.value || !prevEl.value) return
    const dir = v > o ? 1 : -1
    tl = run(() => {
      const t = gsap.timeline({ onComplete: () => (prev.value = null) })
      if (isSoft()) {
        t.fromTo(nowEl.value, { opacity: 0 }, { opacity: 1, duration: 0.2 }).set(prevEl.value, { opacity: 0 }, 0)
        return t
      }
      t.fromTo(prevEl.value, { yPercent: 0, opacity: 1 }, { yPercent: -100 * dir, opacity: 0, duration: 0.4, ease: 'power3.in' }, 0)
      t.fromTo(
        nowEl.value,
        { yPercent: 100 * dir, opacity: 0, filter: 'blur(2px)' },
        { yPercent: 0, opacity: 1, filter: 'blur(0px)', duration: 0.6, ease: 'back.out(2.4)' },
        0.12,
      )
      return t
    })
  },
)
</script>

<template>
  <span class="roll">
    <span ref="nowEl" class="d">{{ cur }}</span>
    <span v-if="prev !== null" ref="prevEl" class="d" aria-hidden="true">{{ prev }}</span>
  </span>
</template>

<style scoped>
.roll {
  display: inline-grid;
  overflow: hidden;
  vertical-align: bottom;
  font-variant-numeric: tabular-nums;
  line-height: inherit;
}
.d {
  grid-area: 1 / 1;
  text-align: center;
}
</style>
