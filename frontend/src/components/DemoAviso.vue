<script setup lang="ts">
import { URL_REPO } from '../lib/modoDemo'
import Icon from './Icon.vue'
</script>

<template>
  <aside class="demo" aria-label="Aviso de demo">
    <span class="demo-dot" aria-hidden="true" />
    <span class="demo-txt">Demo con datos de ejemplo</span>
    <a class="demo-link" :href="URL_REPO" target="_blank" rel="noopener noreferrer">
      Repo <Icon name="external" :size="12" />
    </a>
  </aside>
</template>

<style scoped>
.demo {
  position: fixed;
  z-index: 40;
  right: max(12px, env(safe-area-inset-right));
  bottom: max(12px, env(safe-area-inset-bottom));
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: calc(100vw - 24px);
  padding: 0 4px 0 12px;
  height: var(--h-sm);
  border-radius: var(--r-pill);
  font-size: var(--t-sm);
  color: var(--text-2);
  background: color-mix(in srgb, var(--surface) 92%, transparent);
  backdrop-filter: blur(10px);
  box-shadow: 0 0 0 1px var(--line-2);
}
.demo-dot {
  width: 6px;
  height: 6px;
  border-radius: var(--r-pill);
  background: var(--accent);
}
.demo-txt {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.demo-link {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 24px;
  padding: 0 10px;
  border-radius: var(--r-pill);
  font-weight: 540;
  color: var(--text);
  text-decoration: none;
  touch-action: manipulation;
  transition: background 0.2s, scale 0.15s var(--ease-out);
}
.demo-link::before {
  content: '';
  position: absolute;
  inset: -10px -4px;
}
.demo-link:active {
  scale: var(--press-scale);
}
.demo-link:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
@media (hover: hover) and (pointer: fine) {
  .demo-link:hover {
    background: var(--surface-hover);
  }
}
@media (max-width: 1023px) {
  .demo {
    bottom: calc(84px + max(0px, env(safe-area-inset-bottom)));
  }
}
@media (prefers-reduced-motion: reduce) {
  .demo-link {
    transition: none;
  }
}
</style>
