<script setup lang="ts">
import ViewHeader from './ViewHeader.vue'

defineEmits<{ back: [] }>()

withDefaults(
  defineProps<{
    title?: string
    subtitle?: string
    split?: boolean
    /** Scroll en todo el cuerpo (una columna). */
    bodyScroll?: boolean
    stickyHead?: boolean
    showBack?: boolean
    backLabel?: string
    backIcon?: 'back' | 'close'
    showBackText?: boolean
    ariaLabel?: string
  }>(),
  {
    split: false,
    bodyScroll: false,
    stickyHead: false,
    showBack: false,
    backIcon: 'back',
    showBackText: false,
  },
)
</script>

<template>
  <section class="vf" :class="{ split, 'head-sticky': stickyHead }" :aria-label="ariaLabel">
    <template v-if="split">
      <div class="vf-split">
        <div class="vf-aside">
          <header v-if="title || subtitle || $slots.title || $slots.actions || $slots.meta || showBack || $slots.toolbar" class="vf-head">
            <ViewHeader
              v-if="title || subtitle || $slots.title || $slots.actions || $slots.meta || showBack"
              :title="title"
              :subtitle="subtitle"
              :sticky="false"
              :show-back="showBack"
              :back-label="backLabel"
              :back-icon="backIcon"
              :show-back-text="showBackText"
              @back="$emit('back')"
            >
              <template v-if="$slots.back" #back><slot name="back" /></template>
              <template v-if="$slots.title" #title><slot name="title" /></template>
              <template v-if="$slots.meta" #meta><slot name="meta" /></template>
              <template v-if="$slots.actions" #actions><slot name="actions" /></template>
            </ViewHeader>
            <div v-if="$slots.toolbar" class="vf-toolbar"><slot name="toolbar" /></div>
          </header>
          <div class="vf-aside-scroll view-scroll">
            <slot name="aside" />
          </div>
        </div>
        <main class="vf-main">
          <slot />
        </main>
      </div>
    </template>
    <template v-else>
      <header v-if="title || subtitle || $slots.title || $slots.actions || $slots.meta || showBack || $slots.toolbar" class="vf-head">
        <ViewHeader
          v-if="title || subtitle || $slots.title || $slots.actions || $slots.meta || showBack"
          :title="title"
          :subtitle="subtitle"
          :sticky="false"
          :show-back="showBack"
          :back-label="backLabel"
          :back-icon="backIcon"
          :show-back-text="showBackText"
          @back="$emit('back')"
        >
          <template v-if="$slots.back" #back><slot name="back" /></template>
          <template v-if="$slots.title" #title><slot name="title" /></template>
          <template v-if="$slots.meta" #meta><slot name="meta" /></template>
          <template v-if="$slots.actions" #actions><slot name="actions" /></template>
        </ViewHeader>
        <div v-if="$slots.toolbar" class="vf-toolbar"><slot name="toolbar" /></div>
      </header>
      <div class="vf-body" :class="{ 'view-scroll': bodyScroll }">
        <slot />
      </div>
    </template>
  </section>
</template>

<style scoped>
.vf {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  min-width: 0;
  background: var(--bg);
}

.vf-head {
  flex: none;
  min-height: var(--view-head-min);
  padding: var(--view-head-pad-top) var(--gutter) var(--view-head-pad-bottom);
  padding-top: max(var(--view-head-pad-top), env(safe-area-inset-top));
  padding-left: max(var(--gutter), env(safe-area-inset-left));
  padding-right: max(var(--gutter), env(safe-area-inset-right));
  border-bottom: 1px solid var(--line);
  background: var(--head-bg);
  backdrop-filter: blur(var(--head-blur));
}

.vf.head-sticky .vf-head {
  position: sticky;
  top: 0;
  z-index: 4;
}

.vf-head :deep(.vh) {
  min-height: var(--h-md);
  align-items: flex-start;
}
/* Título en la misma y en todas las vistas, centrado contra la altura de un botón. */
.vf-head :deep(.vh-start) {
  align-items: flex-start;
  min-height: var(--h-md);
}
.vf-head :deep(.vh:not(.compact) .vh-titles) {
  padding-top: calc((var(--h-md) - 15px) / 2);
  line-height: 15px;
  align-items: center;
}
.vf-head :deep(.vh-titles > *) {
  line-height: 15px;
}

.vf-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 12px;
  padding-top: 10px;
  min-width: 0;
}
.vf-head:not(:has(.vh)) .vf-toolbar {
  padding-top: 0;
}

.vf-body {
  flex: 1;
  min-height: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--view-body-gap);
  padding: var(--view-pad-top) var(--gutter) calc(16px + env(safe-area-inset-bottom));
  padding-left: max(var(--gutter), env(safe-area-inset-left));
  padding-right: max(var(--gutter), env(safe-area-inset-right));
}

.vf-split {
  flex: 1;
  min-height: 0;
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  overflow: hidden;
}

.vf-aside {
  min-height: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.vf-aside-scroll {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: var(--view-body-gap);
  padding: var(--view-pad-top) var(--gutter) calc(16px + env(safe-area-inset-bottom));
  padding-left: max(var(--gutter), env(safe-area-inset-left));
  padding-right: max(var(--gutter), env(safe-area-inset-right));
}

.vf-main {
  min-height: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* La barra de scroll come ancho: el borde derecho se compensa para alinear con el título. */
.view-scroll {
  padding-right: var(--gutter-end);
}

@media (min-width: 1024px) {
  .vf.split .vf-split {
    grid-template-columns: var(--tablero, 40%) minmax(0, 1fr);
  }
  .vf.split .vf-aside {
    border-right: 1px solid var(--line);
  }
  .vf.split .vf-main {
    background: color-mix(in srgb, var(--bg-2) 45%, var(--bg));
  }
  .vf-body {
    padding-bottom: calc(24px + env(safe-area-inset-bottom));
  }
  .vf-aside-scroll {
    padding-bottom: calc(24px + env(safe-area-inset-bottom));
  }
}

/* táctil: sin vidrio (el blur de una barra fija se recalcula con cada scroll y gasta batería) */
@media (pointer: coarse) {
  .vf-head {
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
    background: color-mix(in srgb, var(--bg) 94%, transparent);
  }
}
</style>
