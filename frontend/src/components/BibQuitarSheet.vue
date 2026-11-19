<script setup lang="ts">
import { ref } from 'vue'
import { useFocusTrap } from '../lib/focusTrap'
import Icon from './Icon.vue'

const props = defineProps<{ open: boolean; count: number; name?: string; busy?: boolean }>()
const emit = defineEmits<{ confirm: []; cancel: [] }>()

const panel = ref<HTMLElement | null>(null)
const cancelBtn = ref<HTMLButtonElement | null>(null)
const { onKeydown } = useFocusTrap(panel, () => props.open, {
  onEscape: () => {
    if (!props.busy) emit('cancel')
  },
  initial: () => cancelBtn.value,
})
</script>

<template>
  <Teleport to="body">
    <Transition name="qs">
      <div v-if="open" class="sheet-root qs-bg" @keydown="onKeydown">
        <div class="sheet-scrim" @click="!busy && emit('cancel')" />
        <div ref="panel" class="sheet-panel qs" role="alertdialog" aria-modal="true" aria-labelledby="qs-t" aria-describedby="qs-d">
          <span class="qs-ic"><Icon name="trash" :size="20" /></span>
          <h3 id="qs-t" class="sheet-title">{{ count === 1 ? 'Quitar de la Biblioteca' : `Quitar ${count} de la Biblioteca` }}</h3>
          <p id="qs-d">
            <template v-if="count === 1 && name"><b>{{ name }}</b> deja de aparecer acá y no vuelve con un reindexado. </template>
            <template v-else>Dejan de aparecer acá y no vuelven con un reindexado. </template>
            No se borra ningún archivo tuyo.
          </p>
          <div class="sheet-actions qs-actions">
            <button ref="cancelBtn" type="button" class="btn btn-ghost" :disabled="busy" @click="emit('cancel')">Cancelar</button>
            <button type="button" class="btn btn-danger" :disabled="busy" @click="emit('confirm')">
              <Icon name="trash" :size="14" /> {{ busy ? 'Quitando…' : count === 1 ? 'Quitar' : `Quitar ${count}` }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.qs-bg {
  z-index: 90;
}
.qs {
  width: 100%;
  box-sizing: border-box;
  display: grid;
  justify-items: start;
  gap: 10px;
}
.qs-ic {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: var(--r-lg);
  color: var(--danger);
  background: var(--danger-soft);
}
p {
  margin: 0;
  font-size: 14px;
  line-height: 1.5;
  color: var(--text-2);
  overflow-wrap: anywhere;
}
p b {
  color: var(--text);
  font-weight: 600;
}
.qs-actions {
  justify-self: stretch;
  margin-top: 8px;
}
@media (min-width: 720px) {
  .qs {
    width: 400px;
  }
  .qs-actions {
    justify-content: flex-end;
  }
}
.qs-enter-active { transition: opacity 0.22s; }
.qs-enter-active .qs { transition: transform 0.48s var(--ease-sheet); }
.qs-leave-active { transition: opacity 0.18s; }
.qs-enter-from, .qs-leave-to { opacity: 0; }
.qs-enter-from .qs { transform: translateY(36px); }
@media (min-width: 720px) {
  .qs-enter-from .qs { transform: scale(0.94); }
}
:root[data-motion='soft'] .qs-enter-from .qs { transform: none; }
</style>
