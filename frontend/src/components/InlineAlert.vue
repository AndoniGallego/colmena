<script setup lang="ts">
import Icon from './Icon.vue'

defineProps<{
  tone?: 'danger' | 'soft' | 'warn'
  detalle?: string | null
}>()
</script>

<template>
  <p class="alert" :class="tone ?? 'danger'" role="alert">
    <Icon name="warn" :size="14" />
    <span class="alert-body">
      <span><slot /></span>
      <details v-if="detalle" class="alert-det">
        <summary>Ver detalle</summary>
        <code data-copiable>{{ detalle }}</code>
      </details>
    </span>
    <slot name="action" />
  </p>
</template>

<style scoped>
.alert {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 0;
  padding: 10px 12px;
  border-radius: var(--r-btn);
  font-size: 13px;
  line-height: 1.4;
  color: var(--danger);
  background: var(--danger-soft);
  border: 1px solid color-mix(in srgb, var(--danger) 40%, transparent);
}

.alert.soft {
  color: var(--text-2);
  background: var(--surface-2);
  border-color: var(--line-2);
}

.alert.warn {
  color: var(--st-blocked);
  background: var(--st-blocked-soft);
  border-color: color-mix(in srgb, var(--st-blocked) 35%, transparent);
}

.alert span {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}

.alert-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.alert-det {
  font-size: 11px;
  color: var(--text-3);
}

.alert-det summary {
  cursor: pointer;
  user-select: none;
}

.alert-det code {
  display: block;
  margin-top: 4px;
  font-size: 11px;
  white-space: pre-wrap;
  word-break: break-word;
}

.alert :deep(svg) {
  flex: none;
  margin-top: 2px;
}
</style>
