<script setup lang="ts">
import Icon from './Icon.vue'

type IconName = InstanceType<typeof Icon>['$props']['name']

defineProps<{
  icon?: IconName
  title?: string
}>()
</script>

<template>
  <div class="empty">
    <slot name="icon">
      <Icon v-if="icon" :name="icon" :size="26" />
    </slot>
    <p v-if="title" class="empty-title">{{ title }}</p>
    <p v-if="$slots.default" class="empty-text"><slot /></p>
    <div v-if="$slots.action" class="empty-action">
      <slot name="action" />
    </div>
  </div>
</template>

<style scoped>
.empty {
  display: grid;
  justify-items: center;
  gap: 10px;
  padding: 40px 16px;
  text-align: center;
  color: var(--text-4);
}

.empty-title {
  margin: 0;
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 600;
  color: var(--text-2);
}

.empty-text {
  margin: 0;
  max-width: 300px;
  font-size: var(--t-lg);
  line-height: 1.45;
  color: var(--text-3);
}

.empty-action {
  margin-top: 4px;
}
</style>
