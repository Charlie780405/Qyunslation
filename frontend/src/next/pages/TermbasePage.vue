<template>
  <AppShell>
    <section class="qy-page-head">
      <div><span class="qy-eyebrow">CONTROLLED VOCABULARY</span><h1>专业词库</h1><p>统一维护批准译名、禁用表达和高风险术语。</p></div>
      <div class="qy-page-head-actions">
        <button
          class="qy-secondary-button"
          :class="{ 'is-locked': !canManageTerms }"
          type="button"
          data-term-action="import"
          :aria-disabled="!canManageTerms"
          :aria-describedby="!canManageTerms ? 'term-permission-description' : undefined"
          :title="!canManageTerms ? permissionMessage : undefined"
          @click="handleImportClick"
        >
          <LockClosedIcon v-if="!canManageTerms" aria-hidden="true" />
          <ArrowUpTrayIcon v-else aria-hidden="true" />
          导入 CSV
        </button>
        <button
          class="qy-primary-button"
          :class="{ 'is-locked': !canManageTerms }"
          type="button"
          data-term-action="create"
          :aria-disabled="!canManageTerms"
          :aria-describedby="!canManageTerms ? 'term-permission-description' : undefined"
          :title="!canManageTerms ? permissionMessage : undefined"
          @click="handleNewTermClick"
        >
          <LockClosedIcon v-if="!canManageTerms" aria-hidden="true" />
          <PlusIcon v-else aria-hidden="true" />
          新建术语
        </button>
      </div>
    </section>

    <p v-if="permissionNotice" id="term-permission-notice" class="qy-callout qy-callout-warning" role="status" data-term-permission-notice>
      <LockClosedIcon aria-hidden="true" /> <span>{{ permissionNotice }}</span>
    </p>
    <span id="term-permission-description" class="qy-visually-hidden">{{ permissionMessage }}</span>

    <p v-if="loadError" class="qy-panel qy-inline-error" role="alert" data-term-load-error>{{ loadError }} <button type="button" class="qy-link-button" @click="loadTerms">重试</button></p>

    <div class="qy-term-layout">
      <section class="qy-panel qy-term-panel">
        <div class="qy-saved-views" role="tablist" aria-label="语言资产类型">
          <button v-for="tab in assetTabs" :key="tab.key" type="button" :class="{ active: activeAsset === tab.key }" @click="activeAsset = tab.key">{{ tab.label }} <span>{{ tab.count }}</span></button>
        </div>
        <div class="qy-saved-views" role="tablist" aria-label="词库视图">
          <button v-if="activeAsset === 'terms'" v-for="view in views" :key="view.key" type="button" :class="{ active: activeView === view.key }" @click="activeView = view.key">{{ view.label }} <span>{{ view.count }}</span></button>
        </div>
        <div v-if="activeAsset === 'terms'" class="qy-term-toolbar">
          <label class="qy-search-field"><MagnifyingGlassIcon aria-hidden="true" /><span class="qy-visually-hidden">搜索术语</span><input v-model="query" type="search" placeholder="搜索源术语、译名或定义" /></label>
          <select v-model="risk" aria-label="按风险筛选"><option value="all">全部风险</option><option value="high">高风险</option><option value="normal">常规</option></select>
          <button class="qy-icon-button" type="button" aria-label="更多筛选"><FunnelIcon aria-hidden="true" /></button>
        </div>
        <div v-if="activeAsset === 'terms' && filteredTerms.length" class="qy-term-table-wrap">
          <table class="qy-term-table"><thead><tr><th scope="col">源术语</th><th scope="col">批准译名</th><th scope="col">状态</th><th scope="col">风险</th><th scope="col">维护人</th><th scope="col"><span class="qy-visually-hidden">操作</span></th></tr></thead><tbody><tr v-for="term in filteredTerms" :key="term.id" @click="selectedTerm = term"><td><strong>{{ term.source }}</strong><small>{{ term.domain }}</small></td><td>{{ term.target }}</td><td><span class="qy-status-badge" :class="`is-${term.status}`"><CheckCircleIcon v-if="term.status === 'approved'" aria-hidden="true" /><ClockIcon v-else aria-hidden="true" />{{ term.statusLabel }}</span></td><td><span :class="term.risk === 'high' ? 'qy-risk-high' : 'qy-risk-normal'">{{ term.risk === 'high' ? '高风险' : '常规' }}</span></td><td>{{ term.owner }}</td><td><ChevronRightIcon aria-hidden="true" /></td></tr></tbody></table>
        </div>
        <div v-else-if="activeAsset === 'terms'" class="qy-empty-state qy-term-empty"><BookOpenIcon aria-hidden="true" /><strong>当前视图还没有术语</strong><span>导入 CSV 或在翻译任务中提交候选术语，建立第一条可审计记录。</span><button class="qy-link-button" type="button" @click="handleImportClick">查看导入格式</button></div>
        <div v-else class="qy-asset-list">
          <article v-for="item in activeAssetItems" :key="item.id || item.code" class="qy-review-item">
            <strong>{{ item.name || item.code || item.item_key }}</strong>
            <p>{{ item.text || item.trigger || item.payload?.text || item.payload?.trigger || '已发布语言资产' }}</p>
            <small>{{ item.status || 'published' }} · {{ item.version ? `v${item.version}` : '可追溯发布' }}</small>
          </article>
          <div v-if="!activeAssetItems.length" class="qy-empty-state qy-term-empty"><BookOpenIcon aria-hidden="true" /><strong>暂无已发布资产</strong><span>由术语管理员创建并发布后，这里会显示版本化内容。</span></div>
        </div>
      </section>

      <aside class="qy-term-detail">
        <div v-if="selectedTerm" class="qy-panel qy-detail-card"><div class="qy-detail-heading"><div><span class="qy-eyebrow">TERM DETAIL</span><h2>{{ selectedTerm.source }}</h2></div><button class="qy-icon-button" type="button" aria-label="关闭详情" @click="selectedTerm = null"><XMarkIcon aria-hidden="true" /></button></div><div class="qy-detail-translation"><span>批准译名</span><strong>{{ selectedTerm.target }}</strong></div><dl class="qy-detail-list"><div><dt>领域</dt><dd>{{ selectedTerm.domain }}</dd></div><div><dt>状态</dt><dd>{{ selectedTerm.statusLabel }}</dd></div><div><dt>维护人</dt><dd>{{ selectedTerm.owner }}</dd></div></dl><div class="qy-callout qy-callout-info"><InformationCircleIcon aria-hidden="true" /><span>术语更新不会改写已完成任务；重新应用后才进入新的任务版本。</span></div></div>
        <div v-else class="qy-panel qy-detail-placeholder"><BookOpenIcon aria-hidden="true" /><strong>选择一个术语查看详情</strong><span>这里会显示定义、禁用表达、来源和版本历史。</span></div>
      </aside>
    </div>

    <section v-if="showNewTerm" class="qy-panel qy-term-form" data-new-term-form aria-labelledby="new-term-heading">
      <div class="qy-panel-heading">
        <div><span class="qy-eyebrow">STAGING TERM</span><h2 id="new-term-heading">新建术语</h2><p>新术语先进入待审核状态，批准后才会进入运行时词库。</p></div>
        <button class="qy-icon-button" type="button" aria-label="关闭新建术语" @click="showNewTerm = false"><XMarkIcon aria-hidden="true" /></button>
      </div>
      <form class="qy-term-form-grid" @submit.prevent="createTerm">
        <label class="qy-field"><span>源术语</span><input v-model.trim="newTerm.source" required maxlength="512" autocomplete="off" /></label>
        <label class="qy-field"><span>批准译名</span><input v-model.trim="newTerm.target" required maxlength="512" autocomplete="off" /></label>
        <label class="qy-field"><span>领域（可选）</span><input v-model.trim="newTerm.domain" maxlength="64" placeholder="clinical" /></label>
        <label class="qy-field"><span>风险等级</span><select v-model="newTerm.risk"><option value="normal">常规</option><option value="high">高风险</option></select></label>
        <label class="qy-field qy-term-form-wide"><span>禁用表达（可选，用逗号分隔）</span><input v-model.trim="newTerm.forbidden" maxlength="2000" placeholder="不推荐译法1,不推荐译法2" /></label>
        <div class="qy-review-actions qy-term-form-wide"><button class="qy-primary-button" type="submit" :disabled="creatingTerm || !newTerm.source || !newTerm.target">{{ creatingTerm ? '保存中…' : '保存为待审核' }}</button><button class="qy-link-button" type="button" @click="showNewTerm = false">取消</button></div>
      </form>
    </section>

    <div v-if="showImport" class="qy-import-callout qy-panel">
      <div><strong>受控语言资产导入</strong><span>支持 CSV/TSV；首行字段按资产类型填写。提交前会展示条数和内容摘要，应用后仍需管理员发布。</span></div>
      <select v-model="importAssetType" aria-label="导入资产类型"><option value="termbase">术语库</option><option value="style">风格规则</option><option value="pitfall">错法表</option></select>
      <textarea v-model="importContent" rows="5" placeholder="source,target,domain,risk,forbidden&#10;primary endpoint,主要终点,clinical,high,主要终点评估" />
      <div class="qy-review-actions"><button class="qy-primary-button" type="button" :disabled="importing || !importContent.trim()" @click="previewImport">{{ importing ? '正在预览…' : '预览导入' }}</button><button v-if="importResult?.batch_id" class="qy-secondary-button" type="button" :disabled="importing" @click="applyImport">应用为草稿</button><button class="qy-link-button" type="button" @click="showImport = false">关闭</button></div>
      <p v-if="importResult" class="qy-callout qy-callout-info">已识别 {{ importResult.row_count }} 条。批次 {{ importResult.batch_id }} 可继续应用。</p>
    </div>
  </AppShell>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { api } from '../api.js';
import AppShell from '../components/AppShell.vue';
import { useSessionStore } from '../stores/session.js';
import {
  ArrowUpTrayIcon,
  BookOpenIcon,
  CheckCircleIcon,
  ChevronRightIcon,
  ClockIcon,
  FunnelIcon,
  InformationCircleIcon,
  LockClosedIcon,
  MagnifyingGlassIcon,
  PlusIcon,
  XMarkIcon,
} from '@heroicons/vue/24/outline';

const route = useRoute();
const session = useSessionStore();
const query = ref(typeof route.query.q === 'string' ? route.query.q : '');
const risk = ref('all');
const activeView = ref('company');
const activeAsset = ref('terms');
const showImport = ref(false);
const showNewTerm = ref(false);
const selectedTerm = ref(null);
const terms = ref([]);
const releases = ref([]);
const styleProfiles = ref([]);
const qualityRules = ref([]);
const importAssetType = ref('termbase');
const importContent = ref('');
const importResult = ref(null);
const importing = ref(false);
const loadError = ref('');
const permissionNotice = ref('');
const creatingTerm = ref(false);
const newTerm = ref({ source: '', target: '', domain: '', risk: 'normal', forbidden: '' });
const permissionMessage = '当前账号没有术语库管理员权限，请联系术语管理员。';
const canManageTerms = computed(() => session.hasCapability('can_manage_terms'));
const assetTabs = [
  { key: 'terms', label: '术语库', count: 0 },
  { key: 'style', label: '风格指南', count: 0 },
  { key: 'pitfall', label: '错法表', count: 0 },
  { key: 'releases', label: '发布版本', count: 0 },
];
const views = [
  { key: 'company', label: '公司术语', count: 0 },
  { key: 'pending', label: '待处理', count: 0 },
  { key: 'high-risk', label: '高风险', count: 0 },
  { key: 'forbidden', label: '禁用表达', count: 0 },
];
const filteredTerms = computed(() => terms.value.filter((term) => {
  const needle = query.value.trim().toLowerCase();
  const matchesText = !needle || `${term.source} ${term.target} ${term.domain}`.toLowerCase().includes(needle);
  const matchesRisk = risk.value === 'all' || term.risk === risk.value;
  return matchesText && matchesRisk;
}));
const activeAssetItems = computed(() => {
  if (activeAsset.value === 'style') return styleProfiles.value;
  if (activeAsset.value === 'pitfall') return qualityRules.value;
  if (activeAsset.value === 'releases') return releases.value;
  return [];
});

async function loadTerms() {
  loadError.value = '';
  try {
    const response = await api.listTerms();
    const rows = Array.isArray(response) ? response : response.items || [];
    terms.value = rows.map((row) => {
      const source = row.terms?.find((term) => term.role === 'preferred' && term.lang === 'en') || row.terms?.[0];
      const target = row.terms?.find((term) => term.role === 'preferred' && term.lang !== source?.lang);
      return {
        ...row,
        source: source?.text || '未命名术语',
        target: target?.text || '待补充',
        owner: row.authority || '术语管理员',
        risk: row.term_type === 'high_risk' ? 'high' : 'normal',
        statusLabel: row.status === 'curated' ? '已批准' : row.status === 'rejected' ? '已驳回' : '待审核',
      };
    });
  } catch (error) {
    terms.value = [];
    loadError.value = error?.network ? '连接中断，词库没能加载。请检查网络后重试。' : '词库加载失败，请稍后重试。';
  }
}

async function loadAssets() {
  try {
    const [releaseResponse, styleResponse, ruleResponse] = await Promise.all([
      api.listLanguageAssetReleases({ status: 'published' }),
      api.listStyleProfiles(),
      api.listQualityRules(),
    ]);
    releases.value = releaseResponse.items || [];
    styleProfiles.value = styleResponse.items || [];
    qualityRules.value = ruleResponse.items || [];
    assetTabs.find((tab) => tab.key === 'style').count = styleProfiles.value.length;
    assetTabs.find((tab) => tab.key === 'pitfall').count = qualityRules.value.length;
    assetTabs.find((tab) => tab.key === 'releases').count = releases.value.length;
  } catch (error) {
    // The existing termbase remains usable when a new asset endpoint is not yet deployed.
    if (!loadError.value) loadError.value = error?.network ? '语言资产服务暂时不可用。' : '语言资产加载失败，请稍后重试。';
  }
}

async function previewImport() {
  if (!canManageTerms.value) {
    explainPermission();
    return;
  }
  importing.value = true;
  importResult.value = null;
  try {
    importResult.value = await api.previewLanguageAssetImport({
      asset_type: importAssetType.value,
      filename: importAssetType.value === 'termbase' ? 'terms.csv' : `${importAssetType.value}.csv`,
      content: importContent.value,
      license: 'internal',
      provenance: 'manual-ui-import',
      scope: 'tenant',
    });
    await loadAssets();
  } catch (error) {
    loadError.value = error.message || '导入预览失败';
  } finally {
    importing.value = false;
  }
}

async function applyImport() {
  if (!canManageTerms.value) {
    explainPermission();
    return;
  }
  if (!importResult.value?.batch_id) return;
  importing.value = true;
  try {
    const applied = await api.applyLanguageAssetImport(importResult.value.batch_id);
    importResult.value = { ...importResult.value, ...applied, status: applied.release?.status };
    await loadAssets();
  } catch (error) {
    loadError.value = error.message || '导入应用失败';
  } finally {
    importing.value = false;
  }
}

function explainPermission() {
  permissionNotice.value = permissionMessage;
}

function handleImportClick() {
  if (!canManageTerms.value) {
    explainPermission();
    return;
  }
  permissionNotice.value = '';
  showImport.value = !showImport.value;
}

function handleNewTermClick() {
  if (!canManageTerms.value) {
    explainPermission();
    return;
  }
  permissionNotice.value = '';
  showNewTerm.value = true;
}

async function createTerm() {
  if (!canManageTerms.value) {
    explainPermission();
    return;
  }
  creatingTerm.value = true;
  try {
    await api.createConcept({
      preferred_source: newTerm.value.source,
      preferred_target: newTerm.value.target,
      domain: newTerm.value.domain,
      term_type: newTerm.value.risk === 'high' ? 'high_risk' : 'general',
      layer: 'session',
      forbidden: newTerm.value.forbidden
        .split(',')
        .map((text) => text.trim())
        .filter(Boolean)
        .map((text) => ({ lang: 'zh', text })),
    });
    showNewTerm.value = false;
    newTerm.value = { source: '', target: '', domain: '', risk: 'normal', forbidden: '' };
    await loadTerms();
  } catch (error) {
    loadError.value = error.message || '新建术语失败';
  } finally {
    creatingTerm.value = false;
  }
}

onMounted(async () => {
  await session.load();
  loadTerms();
  loadAssets();
});
</script>
