<template>
    <!-- 3. Translation Settings（精简版：只保留目标语言，中英日） -->
    <Collapse v-show="!form.skip_translate" v-model="isOpen">
        <template #header>
            <strong>
                <Heroicon name="LanguageIcon" class="w-5 h-5 inline-block mr-2" />
                <span>{{ t('translationSettingsTitleText') }}</span>
            </strong>
        </template>

        <div class="mb-3">
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{{ t('targetLanguageLabel') }}</label>
            <select class="w-full px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary" v-model="form.to_lang"
                    @change="saveSetting('translator_to_lang', form.to_lang)">
                <option value="Simplified Chinese">中文(简体)</option>
                <option value="English">英文(English)</option>
                <option value="Japanese">日文(日本語)</option>
            </select>
            <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">如需其他语言，请联系管理员。</p>
        </div>
    </Collapse>
</template>

<script setup>
import { ref, inject } from 'vue';
import Collapse from '../ui/Collapse.vue';
import Heroicon from '../ui/Heroicon.vue';

const props = defineProps({
    t: Function,
});

// Collapse state
const isOpen = ref(false);

// Inject from parent
const form = inject('form');
const saveSetting = inject('saveSetting');
</script>
