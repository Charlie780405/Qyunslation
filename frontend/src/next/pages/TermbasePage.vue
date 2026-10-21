<template>
  <AppShell>
    <section class="qy-page-head">
      <div><span class="qy-eyebrow">CONTROLLED VOCABULARY</span><h1>专业词库</h1><p>统一维护批准译名、禁用表达和高风险术语。</p></div>
      <div class="qy-page-head-actions"><button class="qy-secondary-button" type="button" @click="showImport = !showImport"><ArrowUpTrayIcon aria-hidden="true" /> 导入 CSV</button><button class="qy-primary-button" type="button"><PlusIcon aria-hidden="true" /> 新建术语</button></div>
    </section>

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
        <div v-else-if="activeAsset === 'terms'" class="qy-empty-state qy-term-empty"><BookOpenIcon aria-hidden="true" /><strong>当前视图还没有术语</strong><span>导入 CSV 或在翻译任务中提交候选术语，建立第一条可审计记录。</span><button class="qy-link-button" type="button" @click="showImport = true">查看导入格式</button></div>
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
import {
  ArrowUpTrayIcon,
  BookOpenIcon,
  CheckCircleIcon,
  ChevronRightIcon,
  ClockIcon,
  FunnelIcon,
  InformationCircleIcon,
  MagnifyingGlassIcon,
  PlusIcon,
  XMarkIcon,
} from '@heroicons/vue/24/outline';

const route = useRoute();
const query = ref(typeof route.query.q === 'string' ? route.query.q : '');
const risk = ref('all');
const activeView = ref('company');
const activeAsset = ref('terms');
const showImport = ref(false);
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

onMounted(() => { loadTerms(); loadAssets(); });
</script>
