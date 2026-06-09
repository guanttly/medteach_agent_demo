<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{ value: number; decimals?: number; duration?: number }>(),
  { decimals: 0, duration: 750 }
)

const display = ref(0)
let raf = 0

function animate(to: number) {
  const from = display.value
  const start = performance.now()
  cancelAnimationFrame(raf)
  const tick = (t: number) => {
    const p = Math.min(1, (t - start) / props.duration)
    const e = 1 - Math.pow(1 - p, 3)
    display.value = from + (to - from) * e
    if (p < 1) raf = requestAnimationFrame(tick)
  }
  raf = requestAnimationFrame(tick)
}

watch(() => props.value, (v) => animate(v))
onMounted(() => animate(props.value))

const text = computed(() => display.value.toFixed(props.decimals))
</script>

<template>
  <span class="mono">{{ text }}</span>
</template>
