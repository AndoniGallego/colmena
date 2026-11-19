<script setup lang="ts">
import { gsap, isSoft } from '../motion'
import type { Attachment } from '../state/attachments'
import AttachChip from './AttachChip.vue'

defineProps<{ items: Attachment[]; notice?: string | null }>()
defineEmits<{ remove: [key: string]; retry: [key: string] }>()

// El tray cambia de alto al aparecer/desaparecer; en modo suave solo corta.
function trayIn(el: Element, done: () => void) {
  if (isSoft()) return done()
  gsap.from(el, { height: 0, opacity: 0, duration: 0.38, ease: 'power3.out', onComplete: () => (gsap.set(el, { clearProps: 'height,opacity' }), done()) })
}
function trayOut(el: Element, done: () => void) {
  if (isSoft()) return done()
  gsap.to(el, { height: 0, opacity: 0, duration: 0.26, ease: 'power2.in', onComplete: done })
}
function tileIn(el: Element, done: () => void) {
  if (isSoft()) return done()
  gsap.from(el, { scale: 0.6, opacity: 0, y: 8, duration: 0.55, ease: 'back.out(2)', onComplete: () => (gsap.set(el, { clearProps: 'all' }), done()) })
}
function tileOut(el: Element, done: () => void) {
  if (isSoft()) return done()
  gsap.to(el, { scale: 0.6, opacity: 0, width: 0, marginRight: -8, duration: 0.26, ease: 'power2.in', onComplete: done })
}
</script>

<template>
  <Transition :css="false" @enter="trayIn" @leave="trayOut">
    <div v-if="items.length || notice" class="tray" @click.stop>
      <div v-if="items.length" class="scroller" :class="{ many: items.length > 4 }" data-noswipe>
        <TransitionGroup tag="ul" class="chips" :css="false" @enter="tileIn" @leave="tileOut">
          <AttachChip v-for="a in items" :key="a.key" :item="a" @remove="$emit('remove', a.key)" @retry="$emit('retry', a.key)" />
        </TransitionGroup>
      </div>
      <p v-if="notice" class="notice" role="alert">{{ notice }}</p>
    </div>
  </Transition>
</template>

<style scoped>
.tray {
  grid-column: 1 / -1;
  min-width: 0;
  overflow: hidden;
  padding: 8px 4px 6px;
  border-bottom: 1px solid var(--line);
  margin-bottom: 4px;
}
.scroller {
  min-width: 0;
  overflow-x: auto;
  scroll-snap-type: x proximity;
  scroll-padding-inline: 4px;
  scrollbar-width: none;
  overscroll-behavior-x: contain;
}
.scroller::-webkit-scrollbar {
  display: none;
}
.scroller.many {
  -webkit-mask-image: linear-gradient(90deg, #000 calc(100% - 28px), transparent);
  mask-image: linear-gradient(90deg, #000 calc(100% - 28px), transparent);
}
.chips {
  list-style: none;
  margin: 0;
  padding: 6px 10px 2px 2px;
  display: flex;
  gap: 8px;
  width: max-content;
}
.notice {
  margin: 6px 2px 0;
  font-size: 12px;
  color: var(--danger);
}
.scroller + .notice {
  margin-top: 4px;
}
</style>
