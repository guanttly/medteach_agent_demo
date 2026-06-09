<script setup lang="ts">
import { onMounted } from 'vue'
import { useDemoStore } from './stores/demo'

const store = useDemoStore()
onMounted(() => store.connect())
</script>

<template>
  <router-view />
</template>
