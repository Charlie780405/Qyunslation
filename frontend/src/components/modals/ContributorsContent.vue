<template>
    <div>
        <p class="text-gray-700 dark:text-gray-300">{{ t('contributorsPara1') }}</p>
        <p class="text-gray-700 dark:text-gray-300 mt-2">{{ t('contributorsPara2') }}</p>
        <div class="mt-4 p-4 bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-300 rounded">
            <p>{{ t('contributorsWelcome') }}</p>
            <hr class="my-3 border-green-200 dark:border-green-700">
            <p>{{ t('contributorsNotice') }}</p>
        </div>
        <div class="mt-4 flex justify-end">
            <button type="button" class="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors" @click="$emit('close')">
                {{ t('closeBtn') }}
            </button>
        </div>
    </div>
</template>

<script setup>
defineProps(['t']);
defineEmits(['close']);
</script>
