<template>
  <RouterView v-slot="{ Component }">
    <component :is="Component" />
  </RouterView>
</template>

<script setup>
import { RouterView } from 'vue-router';
</script>
