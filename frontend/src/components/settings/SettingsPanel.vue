<template>
    <div class="settings-panel">
        <div class="d-flex justify-content-between align-items-center mb-3">
            <div class="d-flex align-items-center">
                <img src="/static/quanxin-logo.svg" alt="荃信翻译 Qyunslation" class="me-3" style="height: 36px;" :title="t('pageTitle')" />
                <div class="btn-group">
                    <button type="button" class="btn btn-sm btn-outline-info" @click="showTutorial = true">
                        <Heroicon name="QuestionMarkCircleIcon" class="w-4 h-4 me-1" solid />
                        <span>{{ t('tutorialBtn') }}</span>
                    </button>
                    <!-- 隐藏「项目协作」：开源贡献入口对荃信翻译无意义 -->
                    <!-- <button type="button" class="btn btn-sm btn-outline-warning" @click="showContributors = true">
                        <Heroicon name="UserGroupIcon" class="w-4 h-4 me-1" solid />
                        <span>{{ t('projectContributeBtn') }}</span>
                    </button> -->
                </div>
            </div>
        </div>

        <form id="translateForm" @submit.prevent>
            <div class="border rounded" style="border-color: var(--bs-border-color);">

                <WorkflowConfig
                    :t="t"
                    :enginList="enginList"
                    :showMineruToken="showMineruToken"
                    :showIdentityOption="showIdentityOption"
                    @update:showMineruToken="val => emit('update:showMineruToken', val)"
                    @openDefaultWorkflowModal="openDefaultWorkflowModal" />

                <!-- 隐藏「翻译模型」配置：内置大模型引擎，API/baseURL 不对用户开放 -->
                <!-- <AISettings
                    :t="t" /> -->

                <TranslationSettings
                    :t="t" />

                <GlossarySettings
                    :t="t" />

            </div>
        </form>

        <!-- Import/Export -->
        <div class="d-flex justify-content-center gap-2 mt-4">
            <button type="button" class="btn btn-outline-primary" @click="configFile.click()">
                <Heroicon name="ArrowUpTrayIcon" class="w-4 h-4 me-1" />
                <span>{{ t('importConfigBtn') }}</span>
            </button>
            <button type="button" class="btn btn-outline-secondary" @click="handleExportConfig">
                <Heroicon name="ArrowDownTrayIcon" class="w-4 h-4 me-1" />
                <span>{{ t('exportConfigBtn') }}</span>
            </button>
        </div>
        <input type="file" ref="configFile" class="d-none" accept=".json" @change="handleImportConfig">

        <!-- Project Info -->
        <div class="mt-4 text-center text-muted small">
            <p class="mb-0">version:<span>{{ version ? 'v' + version : '' }}</span></p>
            <p class="mb-1 mt-1">© 荃信生物 Qyunslation</p>
            <!-- Status Flags -->
            <div v-if="webSkipValidation || envForceOverride" class="status-flags mt-2">
                <span v-if="webSkipValidation" :title="t('webSkipValidation')" class="status-flag">
                    <Heroicon name="CheckBadgeIcon" class="w-4 h-4" />
                </span>
                <span v-if="envForceOverride" :title="t('envForceOverride')" class="status-flag status-flag-warning">
                    <Heroicon name="LockClosedIcon" class="w-4 h-4" />
                </span>
            </div>
        </div>
    </div>

    <!-- Tutorial Modal -->
    <Modal v-model="showTutorial" :title="t('tutorialModalTitle')" size="xl">
        <TutorialContent :t="t" @close="showTutorial = false" />
    </Modal>

    <!-- Contributors Modal -->
    <Modal v-model="showContributors" :title="t('contributorsModalTitle')" size="lg">
        <ContributorsContent :t="t" @close="showContributors = false" />
    </Modal>

    <!-- Default Workflow Modal -->
    <DefaultWorkflowModal
        ref="defaultWorkflowModal"
        :t="t"
        @save="saveDefaultWorkflows" />
</template>

<script setup>
import { ref, inject } from 'vue';
import WorkflowConfig from './WorkflowConfig.vue';
import AISettings from './AISettings.vue';
import TranslationSettings from './TranslationSettings.vue';
import GlossarySettings from './GlossarySettings.vue';
import Modal from '../ui/Modal.vue';
import TutorialContent from '../modals/TutorialContent.vue';
import ContributorsContent from '../modals/ContributorsContent.vue';
import DefaultWorkflowModal from '../modals/DefaultWorkflowModal.vue';
import Heroicon from '../ui/Heroicon.vue';

const props = defineProps({
    t: Function,
    enginList: Array,
    showMineruToken: Boolean,
    showIdentityOption: Boolean,
    version: String,
});

const emit = defineEmits([
    'update:showMineruToken',
]);

// Inject from parent
const form = inject('form');
const workflowParams = inject('workflowParams');
const errors = inject('errors');
const defaultParams = inject('defaultParams');
const glossaryCount = inject('glossaryCount');
const saveSetting = inject('saveSetting');
const saveSettingArray = inject('saveSettingArray');
const saveWorkflowParam = inject('saveWorkflowParam');
const clearError = inject('clearError');
const handleGlossaryFiles = inject('handleGlossaryFiles');
const clearGlossary = inject('clearGlossary');
const openGlossaryModal = inject('openGlossaryModal');
const downloadGlossaryTemplate = inject('downloadGlossaryTemplate');
const exportConfig = inject('exportConfig');
const importConfig = inject('importConfig');
const saveDefaultWorkflows = inject('saveDefaultWorkflows');
const webSkipValidation = inject('webSkipValidation');
const envForceOverride = inject('envForceOverride');

const configFile = ref(null);
const showTutorial = ref(false);
const showContributors = ref(false);
const defaultWorkflowModal = ref(null);

const handleExportConfig = () => {
    exportConfig();
};

const handleImportConfig = (e) => {
    importConfig(e, props.t);
};

const openDefaultWorkflowModal = () => {
    defaultWorkflowModal.value?.show();
};
</script>

<style scoped>
.status-flags {
    display: flex;
    justify-content: center;
    gap: 8px;
}
.status-flag {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border-radius: 4px;
    background: rgba(59, 130, 246, 0.1);
    color: #3b82f6;
    cursor: help;
}
.status-flag:hover {
    background: rgba(59, 130, 246, 0.2);
}
.status-flag-warning {
    background: rgba(245, 158, 11, 0.1);
    color: #f59e0b;
}
.status-flag-warning:hover {
    background: rgba(245, 158, 11, 0.2);
}
</style>
