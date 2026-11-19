<script setup lang="ts">
defineProps<{
  name: 'arrow-up' | 'arrow-right' | 'stop' | 'plus' | 'minus' | 'sun' | 'moon' | 'target' | 'chevron' | 'warn' | 'lock' | 'pen' | 'check' | 'down' | 'board' | 'chat' | 'refresh' | 'dots' | 'power' | 'doc' | 'ask' | 'pulse' | 'clip' | 'back' | 'close' | 'search' | 'terminal' | 'monitor' | 'image' | 'play' | 'pause' | 'prev' | 'next' | 'expand' | 'shrink' | 'diagrama' | 'library' | 'grid' | 'list' | 'external' | 'copy' | 'keyboard' | 'film' | 'trash' | 'mic' | 'calendar' | 'sparkle' | 'broom' | 'clock' | 'bell' | 'bell-off' | 'link' | 'brain' | 'merge' | 'branch' | 'users' | 'hex'
  size?: number
}>()
</script>

<template>
  <svg
    :width="size ?? 16"
    :height="size ?? 16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.9"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <template v-if="name === 'arrow-up'"><path d="M12 19V5M5.5 11.5 12 5l6.5 6.5" /></template>
    <template v-else-if="name === 'arrow-right'"><path d="M5 12h14M13 6l6 6-6 6" /></template>
    <template v-else-if="name === 'stop'"><rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" stroke="none" /></template>
    <template v-else-if="name === 'plus'"><path d="M12 5v14M5 12h14" /></template>
    <template v-else-if="name === 'minus'"><path d="M5 12h14" /></template>
    <template v-else-if="name === 'sun'"><circle cx="12" cy="12" r="4" /><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4" /></template>
    <template v-else-if="name === 'moon'"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" /></template>
    <template v-else-if="name === 'target'"><circle cx="12" cy="12" r="7.5" /><circle cx="12" cy="12" r="2.5" fill="currentColor" stroke="none" /><path d="M12 1.5v3M12 19.5v3M1.5 12h3M19.5 12h3" /></template>
    <template v-else-if="name === 'chevron'"><path d="m9 6 6 6-6 6" /></template>
    <template v-else-if="name === 'warn'"><path d="M12 3.5 2.5 20h19L12 3.5Z" /><path d="M12 10v4.5M12 17.2v.1" /></template>
    <template v-else-if="name === 'lock'"><rect x="5" y="10.5" width="14" height="10" rx="2.5" /><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5" /></template>
    <template v-else-if="name === 'pen'"><path d="M4 20h4L19 9l-4-4L4 16v4Z" /><path d="m13.5 6.5 4 4" /></template>
    <template v-else-if="name === 'broom'"><path d="M19.5 3.5 12.5 11" /><path d="M8.5 11.5h7.2l2.8 8.5h-13z" /><path d="M9.8 20l.7-4.2M12 20v-4.2M14.2 20l-.7-4.2" /></template>
    <template v-else-if="name === 'check'"><path d="m5 12.5 4.5 4.5L19 7.5" /></template>
    <template v-else-if="name === 'down'"><path d="M12 5v14M5.5 12.5 12 19l6.5-6.5" /></template>
    <template v-else-if="name === 'board'"><rect x="3.5" y="4" width="7" height="16" rx="1.8" /><rect x="13.5" y="4" width="7" height="9" rx="1.8" /><rect x="13.5" y="16" width="7" height="4" rx="1.4" /></template>
    <template v-else-if="name === 'chat'"><path d="M4 5.5h16v11H10l-4.5 3.5v-3.5H4z" /></template>
    <template v-else-if="name === 'refresh'"><path d="M20 11.5A8 8 0 1 0 17.6 17.6M20 4.5v7h-7" /></template>
    <template v-else-if="name === 'dots'"><circle cx="5.5" cy="12" r="1.4" fill="currentColor" /><circle cx="12" cy="12" r="1.4" fill="currentColor" /><circle cx="18.5" cy="12" r="1.4" fill="currentColor" /></template>
    <template v-else-if="name === 'power'"><path d="M12 3.5v8M6.7 6.6a7.5 7.5 0 1 0 10.6 0" /></template>
    <template v-else-if="name === 'ask'"><circle cx="12" cy="12" r="8.5" /><path d="M9.6 9.6a2.5 2.5 0 1 1 3.4 2.3c-.7.3-1 .8-1 1.6M12 16.6v.1" /></template>
    <template v-else-if="name === 'pulse'"><path d="M3 12h4l2.5-6 4 12 2.5-6H21" /></template>
    <template v-else-if="name === 'doc'"><path d="M6.5 3.5h7.5l4 4v13h-11.5z" /><path d="M9.5 12h6M9.5 15.5h6" /></template>
    <template v-else-if="name === 'clip'"><path d="m20 11.5-8.2 8.2a5 5 0 0 1-7.1-7.1l8.6-8.6a3.4 3.4 0 0 1 4.8 4.8l-8.6 8.6a1.8 1.8 0 0 1-2.5-2.5l7.9-7.9" /></template>
    <template v-else-if="name === 'back'"><path d="M19 12H5M11 6l-6 6 6 6" /></template>
    <template v-else-if="name === 'close'"><path d="M6 6l12 12M18 6 6 18" /></template>
    <template v-else-if="name === 'search'"><circle cx="10.5" cy="10.5" r="6" /><path d="m15 15 5 5" /></template>
    <template v-else-if="name === 'terminal'"><path d="m5 8 4 4-4 4M12 17h7" /></template>
    <template v-else-if="name === 'monitor'"><rect x="3" y="4.5" width="18" height="12" rx="2.2" /><path d="M8 20h8M12 16.5V20" /></template>
    <template v-else-if="name === 'image'"><rect x="3.5" y="4.5" width="17" height="15" rx="2.5" /><circle cx="9" cy="10" r="1.6" /><path d="m4 17 5-4.5 4 3.5 3-2.5 4 3.5" /></template>
    <template v-else-if="name === 'play'"><path d="M8 5.5v13l11-6.5z" fill="currentColor" /></template>
    <template v-else-if="name === 'pause'"><rect x="6.5" y="5" width="4" height="14" rx="1.2" fill="currentColor" stroke="none" /><rect x="13.5" y="5" width="4" height="14" rx="1.2" fill="currentColor" stroke="none" /></template>
    <template v-else-if="name === 'prev'"><path d="M18 6v12l-8-6zM6 6v12" /></template>
    <template v-else-if="name === 'next'"><path d="M6 6v12l8-6zM18 6v12" /></template>
    <template v-else-if="name === 'expand'"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" /></template>
    <template v-else-if="name === 'shrink'"><path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5" /></template>
    <template v-else-if="name === 'diagrama'"><circle cx="5.5" cy="6.5" r="2" /><circle cx="18.5" cy="12" r="2" /><circle cx="5.5" cy="17.5" r="2" /><path d="M7.4 7.2c4 .6 6.5 2.4 9 4M7.4 16.8c4-.6 6.5-2.4 9-4" /></template>
    <template v-else-if="name === 'library'"><rect x="3.5" y="4" width="5" height="16" rx="1.4" /><rect x="10.5" y="4" width="5" height="16" rx="1.4" /><path d="m18.2 6 3 12.7" /></template>
    <template v-else-if="name === 'grid'"><rect x="4" y="4" width="7" height="7" rx="1.6" /><rect x="13" y="4" width="7" height="7" rx="1.6" /><rect x="4" y="13" width="7" height="7" rx="1.6" /><rect x="13" y="13" width="7" height="7" rx="1.6" /></template>
    <template v-else-if="name === 'list'"><path d="M9 6.5h11M9 12h11M9 17.5h11" /><circle cx="4.6" cy="6.5" r="1" fill="currentColor" /><circle cx="4.6" cy="12" r="1" fill="currentColor" /><circle cx="4.6" cy="17.5" r="1" fill="currentColor" /></template>
    <template v-else-if="name === 'external'"><path d="M14 4h6v6M20 4l-8.5 8.5M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10" /></template>
    <template v-else-if="name === 'calendar'"><rect x="3.5" y="5" width="17" height="15" rx="3" /><path d="M3.5 10h17M8 3v4M16 3v4" /></template>
    <template v-else-if="name === 'bell'"><path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.6 2H4.4L6 16.5ZM10 20.5a2.2 2.2 0 0 0 4 0" /></template>
    <template v-else-if="name === 'bell-off'"><path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.6 2H4.4L6 16.5ZM10 20.5a2.2 2.2 0 0 0 4 0M3.5 3.5l17 17" /></template>
    <template v-else-if="name === 'link'"><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" /><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" /></template>
    <template v-else-if="name === 'brain'"><path d="M12 5.2a3 3 0 0 0-5.6-1.2A3 3 0 0 0 4 8.5a3.2 3.2 0 0 0 .3 5.6A3.3 3.3 0 0 0 8 19.6a2.8 2.8 0 0 0 4 .4z" /><path d="M12 5.2a3 3 0 0 1 5.6-1.2A3 3 0 0 1 20 8.5a3.2 3.2 0 0 1-.3 5.6 3.3 3.3 0 0 1-3.7 5.5 2.8 2.8 0 0 1-4 .4" /><path d="M8.5 9.5a2 2 0 0 1 2 2M15.5 9.5a2 2 0 0 0-2 2M8 14.5h1.5M16 14.5h-1.5" /></template>
    <template v-else-if="name === 'merge'"><circle cx="6.5" cy="5.5" r="2.2" /><circle cx="17.5" cy="17.5" r="2.2" /><path d="M6.5 20.5V7.7M6.5 8.5a9 9 0 0 0 8.8 9" /></template>
    <template v-else-if="name === 'branch'"><circle cx="6.5" cy="18.5" r="2.2" /><circle cx="6.5" cy="5.5" r="2.2" /><circle cx="17.5" cy="7.5" r="2.2" /><path d="M6.5 7.7v8.6M17.5 9.7c0 4.3-4.6 4-8.8 7" /></template>
    <template v-else-if="name === 'users'"><circle cx="9" cy="8.5" r="3.2" /><path d="M3.5 19.5a5.5 5.5 0 0 1 11 0M15.5 5.6a3.2 3.2 0 0 1 0 6M17 14.2a5.5 5.5 0 0 1 3.5 5.3" /></template>
    <template v-else-if="name === 'hex'"><path d="M12 3.2 19.6 7.6v8.8L12 20.8 4.4 16.4V7.6Z" /><path d="M12 9.4 14.3 10.7v2.6L12 14.6 9.7 13.3v-2.6Z" fill="currentColor" stroke="none" /></template>
    <template v-else-if="name === 'clock'"><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></template>
    <template v-else-if="name === 'sparkle'"><path d="M12 3.5c.6 4.4 2.1 5.9 6.5 6.5-4.4.6-5.9 2.1-6.5 6.5-.6-4.4-2.1-5.9-6.5-6.5C9.9 9.4 11.4 7.9 12 3.5Z" /><path d="M18.5 15.5c.2 1.6.8 2.2 2.4 2.4-1.6.2-2.2.8-2.4 2.4-.2-1.6-.8-2.2-2.4-2.4 1.6-.2 2.2-.8 2.4-2.4Z" /></template>
    <template v-else-if="name === 'copy'"><rect x="8.5" y="8.5" width="11" height="11" rx="2.2" /><path d="M15.5 8.5V6.2a2 2 0 0 0-2-2H6.2a2 2 0 0 0-2 2v7.3a2 2 0 0 0 2 2h2.3" /></template>
    <template v-else-if="name === 'keyboard'"><rect x="2.5" y="6" width="19" height="12" rx="2.4" /><path d="M6.5 10h.1M10 10h.1M13.5 10h.1M17 10h.1M7 14h10" /></template>
    <template v-else-if="name === 'trash'"><path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l.8 12.2a1.6 1.6 0 0 0 1.6 1.5h6.2a1.6 1.6 0 0 0 1.6-1.5L17.5 7M10 11v6M14 11v6" /></template>
    <template v-else-if="name === 'mic'"><rect x="9" y="3" width="6" height="11.5" rx="3" /><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3" /></template>
    <template v-else-if="name === 'film'"><rect x="3.5" y="4.5" width="17" height="15" rx="2.5" /><path d="M8 4.5v15M16 4.5v15M3.5 9h4.5M3.5 15h4.5M16 9h4.5M16 15h4.5" /></template>
  </svg>
</template>
