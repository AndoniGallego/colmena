<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { renderMarkdown } from '../lib/markdown'
import { compactText } from '../lib/contexto'
import { clock } from '../lib/time'
import type { IndexedItem } from '../lib/transcript'
import { gsap, isSoft, useGsap } from '../motion'
import Icon from './Icon.vue'

const props = defineProps<{ item: IndexedItem; quiet?: boolean }>()

const open = ref(false)
const html = computed(() => (open.value ? renderMarkdown(props.item.text) : ''))
const when = computed(() => {
  const t = Date.parse(props.item.ts)
  return Number.isNaN(t) ? '' : clock(t)
})

const label = computed(() => {
  const c = props.item.compact
  if (!c || (!c.pre && !c.post)) return 'Contexto compactado'
  return `Compactada (${c.trigger === 'manual' ? 'manual' : 'auto'}) · ${compactText(c)}`
})

const { run } = useGsap()
const root = ref<HTMLElement | null>(null)
const body = ref<HTMLElement | null>(null)

onMounted(() => {
  const el = root.value
  if (!el || props.quiet) return
  if (isSoft()) return void run(() => gsap.from(el, { opacity: 0, duration: 0.25 }))
  run(() => gsap.from(el.querySelectorAll('.line'), { scaleX: 0, opacity: 0, duration: 0.7, ease: 'power3.out' }))
})

function toggle() {
  const el = body.value
  open.value = !open.value
  if (!el) return
  if (open.value) {
    el.hidden = false
    const soft = isSoft()
    run(() => gsap.fromTo(el, soft ? { opacity: 0 } : { height: 0, opacity: 0 }, { ...(soft ? {} : { height: 'auto' }), opacity: 1, duration: soft ? 0.18 : 0.4, ease: 'power3.out', clearProps: 'height,opacity' }))
  } else if (isSoft()) {
    el.hidden = true
  } else {
    run(() => gsap.to(el, { height: 0, opacity: 0, duration: 0.28, ease: 'power2.inOut', onComplete: () => void (el.hidden = true) }))
  }
}
</script>

<template>
  <div ref="root" class="compact" :class="{ open }">
    <button class="sep" :aria-expanded="open" @click="toggle">
      <i class="line" />
      <span class="label mono">
        {{ label }}<template v-if="when"> · {{ when }}</template>
        <Icon name="down" :size="11" class="chev" />
      </span>
      <i class="line" />
    </button>
    <div ref="body" class="body" hidden>
      <div class="md" v-html="html" />
    </div>
  </div>
</template>

<style scoped>
.compact {
  margin: 18px 0;
}
.sep {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 4px 0;
  color: var(--text-4);
  transition: color 0.2s;
}
.sep:hover {
  color: var(--text-2);
}
.line {
  flex: 1;
  height: 1px;
  background: var(--line-2);
}
.line:first-child {
  transform-origin: 100% 50%;
}
.line:last-child {
  transform-origin: 0 50%;
}
.label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  letter-spacing: 0.06em;
  white-space: nowrap;
}
.chev {
  transition: rotate 0.3s var(--spring);
}
.open .chev {
  rotate: 180deg;
}
.body {
  overflow: hidden;
}
.body[hidden] {
  display: none;
}
.md {
  margin-top: 10px;
  padding: 10px 14px;
  border-radius: 12px;
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--line);
  font-size: var(--t-lg);
  line-height: 1.55;
  color: var(--text-2);
}
</style>
