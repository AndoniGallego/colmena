<script setup lang="ts">
import { computed, ref } from 'vue'
import { useFocusTrap } from '../lib/focusTrap'
import { useKeyboard } from '../lib/keyboard'
import { useSheetSwipe } from '../lib/useSheetSwipe'

const props = defineProps<{ open: boolean; titulo: string; testId?: string }>()
const emit = defineEmits<{ close: [] }>()

const panel = ref<HTMLElement | null>(null)
const { onKeydown } = useFocusTrap(panel, () => props.open, { onEscape: () => emit('close') })
useSheetSwipe(panel, () => emit('close'))
const kb = useKeyboard()
// iOS tapa la hoja con el teclado: la raíz se ajusta a lo visible y la hoja queda arriba del teclado.
const layout = computed(() => (kb.open.value && kb.height.value ? { height: `${kb.height.value}px`, top: `${kb.top.value}px` } : undefined))
</script>

<template>
  <Teleport to="body">
    <Transition name="dcs">
      <div v-if="open" class="sheet-root dcs-root" :style="layout" @keydown="onKeydown">
        <div class="sheet-scrim" @click="emit('close')" />
        <div ref="panel" class="sheet-panel dcs" role="dialog" aria-modal="true" aria-labelledby="dcs-t" :data-test="testId">
          <i class="sheet-grip" aria-hidden="true" />
          <h3 id="dcs-t" class="sheet-title">{{ titulo }}</h3>
          <slot />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.dcs-root { z-index: 60; }
.dcs { box-sizing: border-box; display: grid; gap: 12px; max-height: min(94dvh, 720px, 100%); overflow-y: auto; overscroll-behavior: contain; padding-bottom: max(18px, env(safe-area-inset-bottom)); touch-action: pan-y; }
.dcs-enter-active { transition: opacity 0.22s; }
.dcs-enter-active .dcs { transition: transform 0.48s var(--ease-sheet); }
.dcs-leave-active { transition: opacity 0.18s; }
.dcs-enter-from, .dcs-leave-to { opacity: 0; }
.dcs-enter-from .dcs { transform: translateY(36px); }
@media (min-width: 640px) {
  .dcs { width: 520px; }
  .dcs-enter-from .dcs { transform: scale(0.96); }
}
:root[data-motion='soft'] .dcs-enter-from .dcs { transform: none; }
</style>
