<template>
  <AppShell>
    <section class="qy-page-head"><div><span class="qy-eyebrow">WORKSPACE PREFERENCES</span><h1>参数设置</h1><p>把常用偏好留给个人，把敏感策略交给管理员。</p></div><div class="qy-page-head-actions"><span class="qy-save-state"><span class="qy-status-dot" :class="{ 'is-saving': saving }" aria-hidden="true"></span> {{ saveLabel }}</span></div></section>
    <div class="qy-settings-layout">
      <aside class="qy-settings-nav" aria-label="设置分组"><button v-for="section in sections" :key="section.key" type="button" :class="{ active: activeSection === section.key }" @click="activeSection = section.key"><component :is="section.icon" aria-hidden="true" /><span>{{ section.label }}</span><ChevronRightIcon aria-hidden="true" /></button></aside>
      <section class="qy-settings-content">
        <div class="qy-panel qy-settings-section"><div class="qy-section-heading"><div><span class="qy-eyebrow">PERSONAL DEFAULTS</span><h2>个人偏好</h2><p>只影响你之后创建的新任务。</p></div><span class="qy-source-label">来源：个人</span></div><div class="qy-settings-form"><label class="qy-field"><span>默认语言方向</span><select v-model="preferences.direction"><option>English → 简体中文</option><option>简体中文 → English</option></select><small>创建任务时可以单独覆盖。</small></label><label class="qy-field"><span>默认文档模板</span><select v-model="preferences.profile"><option>临床研究文档</option><option>监管申报材料</option><option>通用医药文档</option></select></label><label class="qy-check-field"><input v-model="preferences.bilingual" type="checkbox" /><span>默认生成源译对照稿</span></label></div></div>
        <div class="qy-panel qy-settings-section"><div class="qy-section-heading"><div><span class="qy-eyebrow">ACCESSIBILITY</span><h2>阅读与交互</h2><p>让长文档复核更舒适。</p></div></div><div class="qy-settings-form"><label class="qy-field"><span>界面密度</span><select v-model="preferences.density"><option value="comfortable">舒适</option><option value="compact">紧凑</option></select></label><label class="qy-check-field"><input v-model="preferences.reduceMotion" type="checkbox" /><span>减少动效</span></label><label class="qy-check-field"><input v-model="preferences.largeText" type="checkbox" /><span>放大辅助文字</span></label></div></div>
        <div v-if="admin" class="qy-panel qy-settings-section qy-admin-section"><div class="qy-section-heading"><div><span class="qy-eyebrow">SYSTEM POLICY</span><h2>系统策略</h2><p>仅管理员可见；密钥只显示配置状态。</p></div><span class="qy-lock-label"><LockClosedIcon aria-hidden="true" /> 管理员策略</span></div><div class="qy-policy-list"><div><span>翻译网关</span><strong>由部署配置管理</strong><small>应用中不可直接查看密钥</small></div><div><span>并发上限</span><strong>策略锁定</strong><small>如需调整，请联系系统管理员</small></div></div></div>
      </section>
    </div>
  </AppShell>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { api } from '../api.js';
import AppShell from '../components/AppShell.vue';
import { AdjustmentsHorizontalIcon, ChevronRightIcon, LockClosedIcon, PaintBrushIcon, ShieldCheckIcon } from '@heroicons/vue/24/outline';

defineProps({ admin: { type: Boolean, default: false } });
const activeSection = ref('personal');
const saving = ref(false);
const saveError = ref(false);
const hydrating = ref(true);
let saveTimer;
const sections = [
  { key: 'personal', label: '个人偏好', icon: AdjustmentsHorizontalIcon },
  { key: 'accessibility', label: '阅读与交互', icon: PaintBrushIcon },
  { key: 'security', label: '系统策略', icon: ShieldCheckIcon },
];
const preferences = reactive({ direction: 'English → 简体中文', profile: '临床研究文档', bilingual: true, density: 'comfortable', reduceMotion: false, largeText: false });
const saveLabel = computed(() => saveError.value ? '保存失败，请重试' : saving.value ? '正在保存…' : hydrating.value ? '正在读取偏好…' : '所有修改已保存');

async function loadPreferences() {
  try {
    const response = await api.getPreferences();
    Object.assign(preferences, response.preferences || {});
  } catch {
    saveError.value = true;
  } finally {
    hydrating.value = false;
  }
}

function scheduleSave() {
  if (hydrating.value) return;
  window.clearTimeout(saveTimer);
  saveTimer = window.setTimeout(async () => {
    saving.value = true;
    saveError.value = false;
    try {
      await api.savePreferences({ ...preferences });
    } catch {
      saveError.value = true;
    } finally {
      saving.value = false;
    }
  }, 500);
}

watch(preferences, scheduleSave, { deep: true });
onMounted(loadPreferences);
</script>
