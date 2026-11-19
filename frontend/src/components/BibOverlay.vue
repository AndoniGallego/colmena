<script setup lang="ts">
import { ref } from 'vue'
import { useFocusTrap } from '../lib/focusTrap'
import { desktop } from '../lib/viewport'
import { closeOverlay, goToSession, openInLibrary, overlayItem } from '../state/biblioteca'
import BibViewer from './BibViewer.vue'

const panel = ref<HTMLElement | null>(null)
const { onKeydown } = useFocusTrap(panel, () => !!overlayItem.value, {
  onEscape: () => {
    if (!document.fullscreenElement) closeOverlay()
  },
})
</script>

<template>
  <Transition name="ov">
    <div v-if="overlayItem" class="ov" :class="{ desktop }" @click.self="closeOverlay" @keydown="onKeydown">
      <div ref="panel" class="card" role="dialog" aria-modal="true" aria-label="Visor">
        <BibViewer
          :item="overlayItem"
          :mode="desktop ? 'overlay' : 'mobile'"
          :has-prev="false"
          :has-next="false"
          @close="closeOverlay"
          @session="goToSession(overlayItem)"
          @library="openInLibrary(overlayItem.id)"
        />
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.ov {
  position: fixed;
  inset: 0;
  z-index: 80;
  background: var(--bg);
}
.ov.desktop {
  display: flex;
  justify-content: flex-end;
  background: color-mix(in srgb, var(--bg) 55%, transparent);
  backdrop-filter: blur(3px);
}
.card {
  width: 100%;
  height: 100%;
}
.desktop .card {
  width: min(78%, 1100px);
  box-shadow: -24px 0 60px -30px rgba(0, 0, 0, 0.6), -1px 0 0 var(--line);
}
.ov-enter-active { transition: opacity 0.25s; }
.ov-enter-active .card { transition: transform 0.55s var(--spring); }
.ov-leave-active { transition: opacity 0.2s; }
.ov-enter-from, .ov-leave-to { opacity: 0; }
.ov-enter-from .card { transform: translateX(40px); }
.ov:not(.desktop).ov-enter-from .card { transform: translateY(6%); }
:root[data-motion='soft'] .ov-enter-from .card { transform: none; }
</style>
