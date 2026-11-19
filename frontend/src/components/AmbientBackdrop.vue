<template>
  <div class="ambient" aria-hidden="true">
    <i class="blob a loop" />
    <i class="blob b loop" />
    <i class="blob c loop" />
    <i class="grid" />
  </div>
</template>

<style scoped>
.ambient {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
  contain: strict;
}
.blob {
  position: absolute;
  width: 70vmax;
  height: 70vmax;
  border-radius: 50%;
  opacity: var(--amb-o, 0.55);
  backface-visibility: hidden;
}
.a {
  left: -28vmax;
  top: -36vmax;
  background: radial-gradient(closest-side, var(--accent-soft), transparent 70%);
  animation: drift-a 46s ease-in-out infinite alternate;
}
.b {
  right: -34vmax;
  bottom: -40vmax;
  background: radial-gradient(closest-side, var(--st-working-soft), transparent 70%);
  animation: drift-b 58s ease-in-out infinite alternate;
}
.c {
  left: 30vw;
  top: 40vh;
  width: 46vmax;
  height: 46vmax;
  background: radial-gradient(closest-side, color-mix(in srgb, var(--accent) 6%, transparent), transparent 70%);
  animation: drift-c 37s ease-in-out infinite alternate;
}
.grid {
  position: absolute;
  inset: 0;
  opacity: var(--amb-grid, 0.5);
  background-image: radial-gradient(var(--line) 1px, transparent 1.2px);
  background-size: 26px 26px;
  -webkit-mask-image: radial-gradient(120% 80% at 50% 0%, #000 0%, transparent 70%);
  mask-image: radial-gradient(120% 80% at 50% 0%, #000 0%, transparent 70%);
}
@keyframes drift-a {
  to { transform: translate3d(18vmax, 14vmax, 0) scale(1.15); }
}
@keyframes drift-b {
  to { transform: translate3d(-16vmax, -12vmax, 0) scale(0.9); }
}
@keyframes drift-c {
  to { transform: translate3d(-22vw, -18vh, 0) scale(1.2); }
}
:root[data-theme='light'] .ambient {
  --amb-o: 0.8;
  --amb-grid: 0.7;
}
@media (prefers-reduced-motion: no-preference) and (hover: hover) {
  .a,
  .b,
  .c {
    will-change: transform;
  }
}
@media (hover: none) {
  .a,
  .b,
  .c {
    animation: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .a,
  .b,
  .c {
    animation: none;
    will-change: auto;
  }
}
</style>
