<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { desglose, fmtTokens } from '../lib/tokens'
import { detalleTokens, pctLabel, type DesgloseItem } from '../lib/usoClaude'
import type { DiosTokens } from '../api/types'

const props = defineProps<{ tokens?: DiosTokens; items?: DesgloseItem[]; label?: string }>()

const K_COLOR: Record<string, string> = { input: 'var(--k-input)', cache_write: 'var(--k-cache_write)', cache_read: 'var(--k-cache_read)', output: 'var(--k-output)' }
const tramos = computed<DesgloseItem[]>(() => {
  if (props.items) return props.items
  if (!props.tokens) return []
  return desglose(props.tokens).map((t) => ({ key: t.key, label: t.label, sub: '', n: t.n, pct: t.pct, color: K_COLOR[t.key], tipo: '' as const, tokens: props.tokens! }))
})
const rich = computed(() => !!props.items)
const hover = ref<string | null>(null)
const open = ref<string | null>(null)
watch(() => props.items, () => (open.value = null))
function toggle(key: string) {
  if (rich.value) open.value = open.value === key ? null : key
}
const ready = ref(false)
onMounted(() => requestAnimationFrame(() => requestAnimationFrame(() => (ready.value = true))))
</script>

<template>
  <div class="db" :data-ready="ready" :data-rich="rich" :data-hover="hover ?? undefined">
    <div class="bar" role="img" :aria-label="label ?? 'Desglose del uso de hoy'">
      <i
        v-for="(t, i) in tramos"
        :key="t.key"
        :class="{ z: !t.n, lit: hover === t.key }"
        :style="{ '--w': `${t.pct}%`, '--d': `${0.15 + Math.min(i, 8) * 0.08}s`, '--c': t.color }"
        @mouseenter="hover = t.key"
        @mouseleave="hover = null"
      />
    </div>
    <ul class="legend">
      <li
        v-for="(t, i) in tramos"
        :key="t.key"
        :class="{ lit: hover === t.key, open: open === t.key }"
        :data-tipo="t.tipo || undefined"
        :style="{ '--c': t.color, '--i': i }"
        @mouseenter="hover = t.key"
        @mouseleave="hover = null"
      >
        <component :is="rich ? 'button' : 'div'" class="li-main" :type="rich ? 'button' : undefined" :aria-expanded="rich ? open === t.key : undefined" @click="toggle(t.key)">
          <i class="dot" />
          <span class="lbl">
            <span class="nm">{{ t.label }}</span>
            <small v-if="t.sub" class="sub">{{ t.sub }}</small>
          </span>
          <b class="mono">{{ fmtTokens(t.n) }}</b>
          <span class="p mono">{{ pctLabel(t.pct, t.n) }}%</span>
        </component>
        <template v-if="rich">
          <span class="tip mono" role="tooltip">{{ detalleTokens(t.tokens) }}</span>
          <div class="more"><p class="mono">{{ detalleTokens(t.tokens) }}</p></div>
        </template>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.db {
  --k-input: var(--st-working);
  --k-cache_write: var(--st-blocked);
  --k-cache_read: var(--accent);
  --k-output: #a78bfa;
  display: grid;
  gap: 14px;
  min-width: 0;
}
:root[data-theme='light'] .db { --k-output: #7a5bd6; --k-cache_write: #b98414; }
.bar { display: flex; gap: 3px; height: 14px; padding: 2px; border-radius: 99px; background: var(--bg-2); box-shadow: inset 0 0 0 1px var(--line); overflow: hidden; }
.bar i { flex: 0 0 auto; width: 0; min-width: 0; border-radius: 99px; background: var(--c); transition: width 1s var(--ease-out) var(--d), opacity 0.25s, filter 0.25s; }
.db[data-ready='true'] .bar i { width: max(var(--w), 0px); }
.bar i.z { display: none; }
.db[data-hover] .bar i:not(.lit) { opacity: 0.35; }
.bar i.lit { filter: brightness(1.15); }
.legend { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }
.legend li { position: relative; font-size: 13px; color: var(--text-2); }
.legend li:not(:last-child) { border-bottom: 1px solid var(--line); }
.li-main { width: 100%; display: grid; grid-template-columns: 10px minmax(0, 1fr) auto 44px; align-items: center; gap: 9px; padding: 5px 0; text-align: left; font: inherit; color: inherit; }
.db[data-rich='true'] .li-main { padding: 8px 4px; cursor: pointer; border-radius: 8px; transition: background 0.2s, scale 0.3s var(--spring); }
.db[data-rich='true'] .li-main:active { scale: 0.99; }
.db[data-rich='true'] li.lit .li-main { background: color-mix(in srgb, var(--c) 9%, transparent); }
.dot { width: 10px; height: 10px; border-radius: 3px; background: var(--c); transition: scale 0.3s var(--spring); }
li.lit .dot { scale: 1.25; }
.lbl { min-width: 0; display: grid; gap: 1px; }
.nm { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
li[data-tipo='otras'] .nm { color: var(--text-3); }
.sub { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--t-sm); color: var(--text-4); }
b { font-weight: 600; color: var(--text); font-variant-numeric: tabular-nums; }
.p { text-align: right; font-size: var(--t-sm); color: var(--text-4); }
.more { display: grid; grid-template-rows: 0fr; transition: grid-template-rows 0.35s var(--ease-out); }
.more p { overflow: hidden; margin: 0; padding: 0 4px 0 23px; font-size: var(--t-sm); line-height: 1.5; color: var(--text-3); }
li.open .more { grid-template-rows: 1fr; }
li.open .more p { padding-bottom: 8px; }
.tip { display: none; }
@media (hover: hover) and (min-width: 1024px) {
  .more { display: none; }
  .tip {
    display: block;
    position: absolute;
    right: 52px;
    bottom: calc(100% - 4px);
    z-index: 5;
    padding: 6px 10px;
    border-radius: var(--r-md);
    font-size: var(--t-sm);
    white-space: nowrap;
    color: var(--text-2);
    background: var(--surface-2);
    box-shadow: inset 0 0 0 1px var(--line-2), 0 10px 26px -12px rgb(0 0 0 / 0.45);
    opacity: 0;
    translate: 0 4px;
    pointer-events: none;
    transition: opacity 0.2s, translate 0.25s var(--ease-out);
  }
  li.lit .tip { opacity: 1; translate: 0 0; }
}
:root[data-motion='soft'] .bar i { transition: width 0.2s linear; }
:root[data-motion='soft'] .more { transition: none; }
</style>
