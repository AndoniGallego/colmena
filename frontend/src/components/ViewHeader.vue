<script setup lang="ts">
import Icon from './Icon.vue'

withDefaults(
  defineProps<{
    title?: string
    subtitle?: string
    compact?: boolean
    sticky?: boolean
    showBack?: boolean
    backLabel?: string
    backIcon?: 'back' | 'close'
    showBackText?: boolean
  }>(),
  {
    sticky: true,
    showBack: false,
    backIcon: 'back',
    showBackText: false,
  },
)

const emit = defineEmits<{ back: [] }>()
</script>

<template>
  <header class="vh" :class="{ compact, sticky }">
    <div class="vh-start">
      <slot name="back">
        <button
          v-if="showBack"
          type="button"
          class="btn btn-back btn-icon"
          :class="{ 'btn-back--wide': showBackText }"
          :aria-label="backLabel ?? 'Volver'"
          @click="emit('back')"
        >
          <Icon :name="backIcon" :size="compact ? 18 : 19" />
          <span v-if="showBackText" class="vh-back-txt"><slot name="backText" /></span>
        </button>
      </slot>
      <div class="vh-titles">
        <slot name="title">
          <h1 v-if="title" class="vh-title">{{ title }}</h1>
        </slot>
        <slot name="meta">
          <p v-if="subtitle" class="vh-sub mono">{{ subtitle }}</p>
        </slot>
      </div>
    </div>
    <div v-if="$slots.actions" class="vh-actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.vh {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 12px var(--gutter) 10px;
  padding-top: max(12px, env(safe-area-inset-top));
  border-bottom: 1px solid var(--line);
  background: var(--head-bg);
  backdrop-filter: blur(var(--head-blur));
}

.vh.sticky {
  position: sticky;
  top: 0;
  z-index: 4;
}

.vh-start {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}

.vh-titles {
  min-width: 0;
  flex: 1;
}

.vh-title {
  margin: 0;
  font-family: var(--font-display);
  font-size: var(--t-view-size);
  font-weight: var(--t-view-weight);
  letter-spacing: var(--t-view-track);
  line-height: 1.15;
  text-transform: uppercase;
  color: var(--text-2);
}

.vh-sub {
  margin: 0;
  font-size: var(--t-sub-size);
  color: var(--text-4);
}

.vh-actions {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
}

.vh.compact {
  padding: 10px var(--gutter) 8px;
  padding-top: max(10px, env(safe-area-inset-top));
}

.vh.compact .vh-title {
  font-size: 16px;
  font-weight: 620;
  letter-spacing: -0.02em;
  text-transform: none;
  color: var(--text);
}

.vh.compact .vh-sub {
  font-size: 12px;
  color: var(--text-3);
}

.vh:not(.compact) .vh-titles {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 10px;
}

.vh:not(.compact) .vh-title,
.vh:not(.compact) :slotted(h1) {
  flex: none;
}

.vh:not(.compact) .vh-sub,
.vh:not(.compact) :slotted(p) {
  min-width: 0;
  flex: 1 1 auto;
}

.vh:not(.compact) :slotted(h1) {
  margin: 0;
  font-family: var(--font-display);
  font-weight: 600;
  font-size: var(--t-view-size);
  letter-spacing: var(--t-view-track);
  line-height: 1.15;
  text-transform: uppercase;
  color: var(--text-2);
}

.vh-back-txt {
  font-size: 13px;
  font-weight: 580;
}

@media (min-width: 1024px) {
  .vh:not(.compact).sticky {
    padding: 14px var(--gutter) 12px;
  }
}

.vh:not(.sticky) {
  padding: 0;
  border-bottom: 0;
  background: none;
  backdrop-filter: none;
}

.vh:not(.compact) {
  flex-wrap: wrap;
  row-gap: 10px;
}

.vh:not(.compact) .vh-start {
  flex: 1 1 160px;
}

.vh:not(.compact) .vh-actions {
  flex-wrap: wrap;
  max-width: 100%;
}
</style>
