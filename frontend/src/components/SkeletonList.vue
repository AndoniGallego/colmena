<script setup lang="ts">
withDefaults(
  defineProps<{
    count?: number
    rows?: number
    variant?: 'card' | 'line'
  }>(),
  { count: 4, rows: 3, variant: 'line' },
)
</script>

<template>
  <div class="skel-list" aria-hidden="true">
    <div v-for="n in count" :key="n" class="ui-skel item" :class="variant">
      <i v-for="r in rows" :key="r" />
    </div>
  </div>
</template>

<style scoped>
.ui-skel {
  display: grid;
  gap: 8px;
}

.ui-skel.line i {
  display: block;
  height: 12px;
  width: 35%;
  border-radius: 6px;
  background: var(--surface-2);
  animation: ui-pulse 1.4s ease-in-out infinite;
}

.ui-skel.line i:nth-child(2) {
  width: 85%;
  height: 15px;
}

.ui-skel.line i:nth-child(3) {
  width: 55%;
}

.ui-skel.card i {
  display: block;
  height: 14px;
  width: 40%;
  border-radius: 6px;
  background: var(--surface-2);
  animation: ui-pulse 1.4s ease-in-out infinite;
}

.ui-skel.card i + i {
  width: 80%;
}
:root[data-motion='soft'] .ui-skel i {
  animation: none;
}
</style>
