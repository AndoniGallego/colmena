<script setup lang="ts">
import { computed, ref, useId } from 'vue'
import type { Subagente } from '../api/types'
import { elapsed, heading, latest, shown, stepOf } from '../lib/subagentes'
import Icon from './Icon.vue'

const props = defineProps<{ items: Subagente[] }>()

const open = ref(false)
const all = ref(false)
const listId = `subs-${useId()}`
const rows = computed(() => shown(props.items, all.value))
const extra = computed(() => props.items.length - rows.value.length)
const live = computed(() => props.items.some((a) => a.estado === 'trabajando'))
const now = computed(() => {
  const a = latest(props.items)
  return a ? stepOf(a) : ''
})
</script>

<template>
  <Transition name="subs">
    <section v-if="items.length" class="subs" :class="{ live, open }" aria-label="Agentes" @keydown.esc="open = false">
      <div class="drawer" :inert="!open">
        <div class="clip">
          <ul :id="listId" class="list" data-noswipe>
            <li v-for="a in rows" :key="a.id" class="row" :class="a.estado" :data-estado="a.estado">
              <span class="mark" aria-hidden="true">
                <i v-if="a.estado === 'trabajando'" class="orb" />
                <Icon v-else-if="a.estado === 'termino'" name="check" :size="12" />
                <i v-else class="idle" />
              </span>
              <div class="body">
                <p class="line1">
                  <span class="desc" :title="a.descripcion">{{ a.descripcion }}</span>
                  <span v-if="a.modelo" class="chip mono">{{ a.modelo }}</span>
                  <span class="time mono">{{ elapsed(a.segundos) }}</span>
                </p>
                <p class="step">{{ stepOf(a) }}</p>
              </div>
            </li>
            <li v-if="extra > 0 || all" class="more">
              <button @click="all = !all">{{ all ? 'Ver menos' : `Ver todos (${items.length})` }}</button>
            </li>
          </ul>
        </div>
      </div>
      <button class="bar" :aria-expanded="open" :aria-controls="listId" @click="open = !open">
        <span class="lead" aria-hidden="true">
          <i v-if="live" class="orb" />
          <Icon v-else name="check" :size="12" />
        </span>
        <span class="count">{{ heading(items) }}</span>
        <Transition name="step" mode="out-in">
          <span v-if="now && !open" :key="now" class="now">{{ now }}</span>
        </Transition>
        <Icon class="chev" name="chevron" :size="13" />
      </button>
    </section>
  </Transition>
</template>

<style scoped>
.subs {
  margin: 0 0 6px;
  border-radius: 16px;
  background: var(--surface);
  border: 1px solid var(--line-2);
  overflow: hidden;
  transition: box-shadow 0.35s var(--ease-out);
}
.subs.open {
  box-shadow: 0 14px 34px -24px rgba(0, 0, 0, 0.45);
}

/* El cajón se abre hacia arriba: va antes de la barra y crece de 0fr a 1fr. */
.drawer {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.38s var(--ease-out);
}
.open .drawer {
  grid-template-rows: 1fr;
}
.clip {
  min-height: 0;
  overflow: hidden;
}
.list {
  list-style: none;
  margin: 0;
  padding: 6px 12px 4px;
  max-height: min(36dvh, 300px);
  overflow-y: auto;
  overscroll-behavior: contain;
  opacity: 0;
  translate: 0 6px;
  transition: opacity 0.2s, translate 0.38s var(--ease-out);
}
.open .list {
  opacity: 1;
  translate: 0 0;
  transition-delay: 0.06s;
}

.bar {
  width: 100%;
  min-height: 36px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  text-align: left;
  color: var(--text-3);
  transition: background 0.2s;
}
.bar:hover {
  background: var(--surface-hover);
}
.open .bar {
  border-top: 1px solid var(--line);
}
.lead {
  flex: none;
  width: 14px;
  height: 14px;
  display: grid;
  place-items: center;
  color: var(--st-done);
}
.count {
  flex: none;
  font-size: var(--t-md);
  font-weight: 600;
  color: var(--text-2);
}
.live .count {
  color: var(--st-working);
}
.now {
  flex: 1;
  min-width: 0;
  font-size: var(--t-md);
  color: var(--text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.now::before {
  content: '·';
  margin-right: 8px;
  color: var(--text-4);
}
.chev {
  flex: none;
  margin-left: auto;
  color: var(--text-4);
  rotate: -90deg;
  transition: rotate 0.35s var(--spring);
}
.open .chev {
  rotate: 90deg;
}

.orb {
  position: relative;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--st-working);
}
.orb::after {
  content: '';
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  background: var(--st-working-soft);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--st-working) 30%, transparent);
  animation: ping 1.8s var(--ease-out) infinite;
}
@keyframes ping {
  0% { opacity: 0.9; scale: 0.5; }
  80%, 100% { opacity: 0; scale: 1.5; }
}
.idle {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--st-idle);
}

.row {
  display: flex;
  gap: 9px;
  padding: 7px 0;
}
.row + .row {
  border-top: 1px solid var(--line);
}
.row.termino {
  opacity: 0.62;
}
.row.sin_actividad {
  opacity: 0.8;
}
.mark {
  flex: none;
  width: 14px;
  height: 18px;
  display: grid;
  place-items: center;
  color: var(--st-done);
}
.body {
  flex: 1;
  min-width: 0;
}
.line1 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  min-width: 0;
}
.desc {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.chip {
  flex: none;
  padding: 1px 7px;
  border-radius: var(--r-pill);
  font-size: var(--t-xs);
  color: var(--text-3);
  box-shadow: inset 0 0 0 1px var(--line-2);
}
.time {
  flex: none;
  font-size: 11px;
  color: var(--text-4);
}
.step {
  margin: 1px 0 0;
  font-size: 12px;
  color: var(--text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.more {
  padding: 4px 0 4px 23px;
  border-top: 1px solid var(--line);
}
.more button {
  font-size: 12px;
  color: var(--text-2);
  text-decoration: underline;
  text-underline-offset: 2px;
}

.subs-enter-active {
  transition: opacity 0.3s, transform 0.5s var(--spring);
}
.subs-leave-active {
  transition: opacity 0.2s, transform 0.25s var(--ease-out);
}
.subs-enter-from {
  opacity: 0;
  transform: translateY(8px) scale(0.98);
}
.subs-leave-to {
  opacity: 0;
  transform: translateY(4px);
}
.step-enter-active {
  transition: opacity 0.25s, translate 0.3s var(--ease-out);
}
.step-leave-active {
  transition: opacity 0.12s;
}
.step-enter-from {
  opacity: 0;
  translate: 0 4px;
}
.step-leave-to {
  opacity: 0;
}

:root[data-motion='soft'] .orb::after { animation: none; opacity: 0; }
@media (prefers-reduced-motion: reduce) {
  .orb::after { animation: none; opacity: 0; }
  .drawer, .list, .chev { transition: none; }
}
</style>
