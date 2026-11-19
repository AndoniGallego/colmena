import { ref } from 'vue'

const mq = window.matchMedia('(min-width: 1024px)')
export const desktop = ref(mq.matches)
mq.addEventListener('change', () => (desktop.value = mq.matches))
