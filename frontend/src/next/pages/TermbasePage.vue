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
    <p v-if="actionNotice" class="qy-callout qy-callout-info" role="status" data-term-action-notice><InformationCircleIcon aria-hidden="true" /> <span>{{ actionNotice }}</span></p>

    <!-- 新建/导入面板放在列表上方：点击后立刻在视野内，不会掉到长表格下面看不见。 -->
    <section v-if="showNewTerm" ref="newTermPanel" class="qy-panel qy-term-form" data-new-term-form aria-labelledby="new-term-heading">
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

    <div v-if="showImport" ref="importPanel" class="qy-import-callout qy-panel">
      <div><strong>受控语言资产导入</strong><span>支持 CSV/TSV；首行字段按资产类型填写。提交前会展示条数和内容摘要，应用后仍需管理员发布。</span></div>
      <select v-model="importAssetType" aria-label="导入资产类型"><option value="termbase">术语库</option><option value="style">风格规则</option><option value="pitfall">错法表</option></select>
      <label class="qy-secondary-button qy-file-pick"><ArrowUpTrayIcon aria-hidden="true" /> 选择 CSV/TSV 文件<input type="file" accept=".csv,.tsv,text/csv,text/tab-separated-values" data-term-import-file @change="onImportFile" /></label>
      <p v-if="importFileName" class="qy-import-file" data-term-import-filename>已读取文件：{{ importFileName }}</p>
      <textarea v-model="importContent" rows="5" placeholder="source,target,domain,risk,forbidden&#10;primary endpoint,主要终点,clinical,high,主要终点评估" />
      <div class="qy-review-actions"><button class="qy-primary-button" type="button" :disabled="importing || !importContent.trim()" @click="previewImport">{{ importing ? '正在预览…' : '预览导入' }}</button><button v-if="importResult?.batch_id" class="qy-secondary-button" type="button" :disabled="importing" @click="applyImport">应用为草稿</button><button class="qy-link-button" type="button" @click="showImport = false">关闭</button></div>
      <p v-if="importResult" class="qy-callout qy-callout-info">已识别 {{ importResult.row_count }} 条。批次 {{ importResult.batch_id }} 可继续应用。</p>
    </div>

    <div class="qy-term-layout">
      <section class="qy-panel qy-term-panel">
        <div class="qy-saved-views" role="tablist" aria-label="语言资产类型">
          <button v-for="tab in assetTabs" :key="tab.key" type="button" :class="{ active: activeAsset === tab.key }" @click="activeAsset = tab.key">{{ tab.label }} <span>{{ tab.count }}</span></button>
        </div>
        <div v-if="activeAsset === 'terms'" class="qy-saved-views" role="tablist" aria-label="词库视图">
          <button v-for="view in views" :key="view.key" type="button" :class="{ active: activeView === view.key }" :data-term-view="view.key" @click="activeView = view.key">{{ view.label }} <span>{{ view.count }}</span></button>
        </div>
        <div v-if="activeAsset === 'terms'" class="qy-term-toolbar">
          <label class="qy-search-field"><MagnifyingGlassIcon aria-hidden="true" /><span class="qy-visually-hidden">搜索术语</span><input v-model="query" type="search" placeholder="搜索源术语、译名或定义" /></label>
          <select v-model="risk" aria-label="按风险筛选"><option value="all">全部风险</option><option value="high">高风险</option><option value="normal">常规</option></select>
          <button
            class="qy-icon-button qy-filter-button"
            :class="{ 'is-active': showFilters || activeFilterCount }"
            type="button"
            aria-label="更多筛选"
            :aria-expanded="showFilters"
            aria-controls="term-filter-panel"
            data-term-filter-toggle
            @click="showFilters = !showFilters"
          >
            <FunnelIcon aria-hidden="true" />
            <span v-if="activeFilterCount" class="qy-filter-count" data-term-filter-count>{{ activeFilterCount }}</span>
          </button>
        </div>
        <div v-if="activeAsset === 'terms' && showFilters" id="term-filter-panel" class="qy-term-filters" data-term-filter-panel>
          <label class="qy-field"><span>领域</span><select v-model="filters.domain" aria-label="按领域筛选"><option value="">全部领域</option><option v-for="item in domainOptions" :key="item" :value="item">{{ item }}</option></select></label>
          <label class="qy-field"><span>层级</span><select v-model="filters.layer" aria-label="按层级筛选"><option value="">全部层级</option><option v-for="item in layerOptions" :key="item" :value="item">{{ item }}</option></select></label>
          <label class="qy-field"><span>译名状态</span><select v-model="filters.targetState" aria-label="按译名状态筛选"><option value="">全部</option><option value="translated">已有译名</option><option value="keep_source">保持原文（不翻译）</option><option value="missing">待补充译名</option></select></label>
          <div class="qy-term-filter-actions"><button class="qy-link-button" type="button" :disabled="!activeFilterCount" data-term-filter-reset @click="resetFilters">清除筛选</button></div>
        </div>

        <div v-if="activeAsset === 'terms' && canManageTerms && selectedIds.length" class="qy-term-bulkbar" role="region" aria-label="批量操作" data-term-bulkbar>
          <strong>已选 {{ selectedIds.length }} 条</strong>
          <button v-if="activeView !== 'rejected'" class="qy-secondary-button qy-danger-button" type="button" :disabled="bulkBusy" data-term-bulk-reject @click="bulkSetStatus('rejected')">驳回所选</button>
          <button v-else class="qy-secondary-button" type="button" :disabled="bulkBusy" data-term-bulk-restore @click="bulkSetStatus('restore')">恢复所选</button>
          <button class="qy-link-button" type="button" @click="selectedIds = []">取消选择</button>
        </div>

        <p v-if="activeAsset === 'terms' && terms.length" class="qy-term-count" data-term-count>
          显示 {{ filteredTerms.length }} / 共 {{ terms.length }} 条<span v-if="activeView === 'suspect'">；“疑似不合规”只是依据项目入库规则的提示，驳回后可在“已驳回”恢复。</span>
        </p>

        <div v-if="activeAsset === 'terms' && filteredTerms.length" class="qy-term-table-wrap qy-term-scroll" tabindex="0" role="region" aria-label="术语列表（可滚动）" data-term-scroll>
          <table class="qy-term-table">
            <thead>
              <tr>
                <th v-if="canManageTerms" scope="col" class="qy-term-check"><input type="checkbox" aria-label="选择当前列表全部术语" :checked="allVisibleSelected" data-term-select-all @change="toggleAll" /></th>
                <th scope="col">源术语</th><th scope="col">批准译名</th><th scope="col">状态</th><th scope="col">风险</th><th scope="col">维护人</th><th scope="col"><span class="qy-visually-hidden">操作</span></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="term in filteredTerms" :key="term.id" :class="{ 'is-selected': selectedTerm?.id === term.id }" data-term-row @click="selectTerm(term)">
                <td v-if="canManageTerms" class="qy-term-check" @click.stop><input type="checkbox" :aria-label="`选择 ${term.source}`" :checked="selectedIds.includes(term.id)" @change="toggleSelect(term.id)" /></td>
                <td class="qy-term-wrap">
                  <strong>{{ term.source }}</strong><small>{{ term.domain }}</small>
                  <span v-if="term.compliance" class="qy-suspect-tag" :title="term.compliance.label" data-term-suspect><ExclamationTriangleIcon aria-hidden="true" />疑似不合规</span>
                </td>
                <td class="qy-term-wrap">
                  <span v-if="term.targetState === 'keep_source'" class="qy-target-keep" data-target-keep>保持原文（不翻译）</span>
                  <template v-else-if="term.targetState === 'missing'">
                    <span class="qy-target-missing" data-target-missing>待补充</span>
                    <button v-if="canManageTerms" class="qy-link-button" type="button" data-term-fill @click.stop="selectTerm(term, true)">补充译名</button>
                  </template>
                  <template v-else>{{ term.target }}</template>
                </td>
                <td><span class="qy-status-badge" :class="`is-${term.badge}`"><CheckCircleIcon v-if="term.status === 'curated'" aria-hidden="true" /><ClockIcon v-else aria-hidden="true" />{{ term.statusLabel }}</span></td>
                <td><span :class="term.risk === 'high' ? 'qy-risk-high' : 'qy-risk-normal'">{{ term.risk === 'high' ? '高风险' : '常规' }}</span></td>
                <td>{{ term.owner }}</td>
                <td><ChevronRightIcon aria-hidden="true" /></td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else-if="activeAsset === 'terms'" class="qy-empty-state qy-term-empty"><BookOpenIcon aria-hidden="true" /><strong>{{ terms.length ? '没有符合条件的术语' : '当前视图还没有术语' }}</strong><span>{{ terms.length ? '换个视图，或清除筛选条件再试。' : '导入 CSV 或在翻译任务中提交候选术语，建立第一条可审计记录。' }}</span><button v-if="terms.length && activeFilterCount" class="qy-link-button" type="button" @click="resetFilters">清除筛选</button><button v-else-if="!terms.length" class="qy-link-button" type="button" @click="handleImportClick">查看导入格式</button></div>
        <div v-else class="qy-asset-list">
          <article v-for="item in activeAssetItems" :key="item.id || item.code" class="qy-review-item">
            <strong>{{ item.name || item.code || item.item_key }}</strong>
            <p>{{ item.text || item.trigger || item.payload?.text || item.payload?.trigger || '已发布语言资产' }}</p>
            <small>{{ item.status || 'published' }} · {{ item.version ? `v${item.version}` : '可追溯发布' }}</small>
          </article>
          <div v-if="!activeAssetItems.length" class="qy-empty-state qy-term-empty"><BookOpenIcon aria-hidden="true" /><strong>暂无已发布资产</strong><span>由术语管理员创建并发布后，这里会显示版本化内容。</span></div>
        </div>
      </section>

      <aside ref="detailPanel" class="qy-term-detail">
        <div v-if="selectedTerm" class="qy-panel qy-detail-card">
          <div class="qy-detail-heading"><div><span class="qy-eyebrow">TERM DETAIL</span><h2>{{ selectedTerm.source }}</h2></div><button class="qy-icon-button" type="button" aria-label="关闭详情" @click="selectedTerm = null"><XMarkIcon aria-hidden="true" /></button></div>
          <div class="qy-detail-translation">
            <span>批准译名</span>
            <strong v-if="selectedTerm.targetState === 'keep_source'">保持原文（不翻译）</strong>
            <strong v-else-if="selectedTerm.targetState === 'missing'">待补充</strong>
            <strong v-else>{{ selectedTerm.target }}</strong>
          </div>
          <p v-if="selectedTerm.targetState === 'keep_source'" class="qy-detail-hint" data-keep-source-hint>该术语按原文保留，不需要译名。如需翻译，在下方填写译名即可。</p>
          <p v-if="selectedTerm.compliance" class="qy-callout qy-callout-warning" data-term-compliance><ExclamationTriangleIcon aria-hidden="true" /><span>疑似不合规：{{ selectedTerm.compliance.label }}</span></p>
          <form v-if="canManageTerms && selectedTerm.status !== 'rejected'" class="qy-term-edit" data-term-edit @submit.prevent="saveTarget">
            <label class="qy-field"><span>{{ selectedTerm.targetState === 'translated' ? '修改译名' : '补充译名' }}</span><input ref="targetInput" v-model.trim="targetDraft" maxlength="512" autocomplete="off" data-term-target-input /></label>
            <button class="qy-primary-button" type="submit" :disabled="savingTarget || !targetDraft || targetDraft === selectedTerm.target" data-term-save-target>{{ savingTarget ? '保存中…' : '保存译名' }}</button>
          </form>
          <dl class="qy-detail-list"><div><dt>领域</dt><dd>{{ selectedTerm.domain || '—' }}</dd></div><div><dt>层级</dt><dd>{{ selectedTerm.layer || '—' }}</dd></div><div><dt>状态</dt><dd>{{ selectedTerm.statusLabel }}</dd></div><div><dt>维护人</dt><dd>{{ selectedTerm.owner }}</dd></div></dl>
          <div v-if="canManageTerms" class="qy-review-actions qy-term-detail-actions">
            <button v-if="selectedTerm.status !== 'rejected'" class="qy-secondary-button qy-danger-button" type="button" :disabled="statusBusy" data-term-reject @click="setSelectedStatus('rejected')">驳回此术语</button>
            <button v-else class="qy-secondary-button" type="button" :disabled="statusBusy" data-term-restore @click="setSelectedStatus('restore')">恢复此术语</button>
          </div>
          <div class="qy-callout qy-callout-info"><InformationCircleIcon aria-hidden="true" /><span>术语更新不会改写已完成任务；重新应用后才进入新的任务版本。</span></div>
        </div>
        <div v-else class="qy-panel qy-detail-placeholder"><BookOpenIcon aria-hidden="true" /><strong>选择一个术语查看详情</strong><span>这里会显示定义、禁用表达、来源和版本历史。</span></div>
      </aside>
    </div>
  </AppShell>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { api } from '../api.js';
import AppShell from '../components/AppShell.vue';
import { confirmDialog } from '../lib/confirm.js';
import { useSessionStore } from '../stores/session.js';
import {
  ArrowUpTrayIcon,
  BookOpenIcon,
  CheckCircleIcon,
  ChevronRightIcon,
  ClockIcon,
  ExclamationTriangleIcon,
  FunnelIcon,
  InformationCircleIcon,
  LockClosedIcon,
  MagnifyingGlassIcon,
  PlusIcon,
  XMarkIcon,
} from '@heroicons/vue/24/outline';

const TERM_LIST_LIMIT = 2000;
const route = useRoute();
const session = useSessionStore();
const query = ref(typeof route.query.q === 'string' ? route.query.q : '');
const risk = ref('all');
const activeView = ref('company');
const activeAsset = ref('terms');
const showImport = ref(false);
const showNewTerm = ref(false);
const showFilters = ref(false);
const filters = ref({ domain: '', layer: '', targetState: '' });
const selectedTerm = ref(null);
const selectedIds = ref([]);
const terms = ref([]);
const releases = ref([]);
const styleProfiles = ref([]);
const qualityRules = ref([]);
const importAssetType = ref('termbase');
const importContent = ref('');
const importFileName = ref('');
const importResult = ref(null);
const importing = ref(false);
const loadError = ref('');
const actionNotice = ref('');
const permissionNotice = ref('');
const creatingTerm = ref(false);
const savingTarget = ref(false);
const statusBusy = ref(false);
const bulkBusy = ref(false);
const targetDraft = ref('');
const targetInput = ref(null);
const detailPanel = ref(null);
const newTermPanel = ref(null);
const importPanel = ref(null);
const newTerm = ref({ source: '', target: '', domain: '', risk: 'normal', forbidden: '' });
const assetCounts = ref({ style: 0, pitfall: 0, releases: 0 });
const permissionMessage = '当前账号没有术语库管理员权限，请联系术语管理员。';
const canManageTerms = computed(() => session.hasCapability('can_manage_terms'));

const STATUS_LABELS = { curated: '已批准', rejected: '已驳回', staging: '待审核' };
const STATUS_BADGES = { curated: 'approved', rejected: 'rejected', staging: 'pending' };

const activeTerms = computed(() => terms.value.filter((term) => term.status !== 'rejected'));
const assetTabs = computed(() => [
  { key: 'terms', label: '术语库', count: activeTerms.value.length },
  { key: 'style', label: '风格指南', count: assetCounts.value.style },
  { key: 'pitfall', label: '错法表', count: assetCounts.value.pitfall },
  { key: 'releases', label: '发布版本', count: assetCounts.value.releases },
]);
const VIEW_RULES = {
  company: (term) => term.status === 'curated',
  pending: (term) => term.status === 'staging',
  'high-risk': (term) => term.status !== 'rejected' && term.risk === 'high',
  forbidden: (term) => term.status !== 'rejected' && term.forbidden.length > 0,
  suspect: (term) => term.status !== 'rejected' && Boolean(term.compliance),
  rejected: (term) => term.status === 'rejected',
};
const VIEW_LABELS = [
  ['company', '公司术语'],
  ['pending', '待处理'],
  ['high-risk', '高风险'],
  ['forbidden', '禁用表达'],
  ['suspect', '疑似不合规'],
  ['rejected', '已驳回'],
];
const views = computed(() => VIEW_LABELS.map(([key, label]) => ({
  key,
  label,
  count: terms.value.filter(VIEW_RULES[key]).length,
})));
const domainOptions = computed(() => [...new Set(terms.value.map((term) => term.domain).filter(Boolean))].sort());
const layerOptions = computed(() => [...new Set(terms.value.map((term) => term.layer).filter(Boolean))].sort());
const activeFilterCount = computed(() => Object.values(filters.value).filter(Boolean).length);

const filteredTerms = computed(() => terms.value.filter((term) => {
  if (!VIEW_RULES[activeView.value](term)) return false;
  const needle = query.value.trim().toLowerCase();
  const matchesText = !needle || `${term.source} ${term.target} ${term.domain}`.toLowerCase().includes(needle);
  const matchesRisk = risk.value === 'all' || term.risk === risk.value;
  const matchesDomain = !filters.value.domain || term.domain === filters.value.domain;
  const matchesLayer = !filters.value.layer || term.layer === filters.value.layer;
  const matchesTarget = !filters.value.targetState || term.targetState === filters.value.targetState;
  return matchesText && matchesRisk && matchesDomain && matchesLayer && matchesTarget;
}));
const allVisibleSelected = computed(() => filteredTerms.value.length > 0 && filteredTerms.value.every((term) => selectedIds.value.includes(term.id)));
const activeAssetItems = computed(() => {
  if (activeAsset.value === 'style') return styleProfiles.value;
  if (activeAsset.value === 'pitfall') return qualityRules.value;
  if (activeAsset.value === 'releases') return releases.value;
  return [];
});

// 视图、搜索或筛选变了，之前勾选的行可能已不在列表里：清空，避免对看不见的行做批量操作。
watch([activeView, query, risk, filters], () => { selectedIds.value = []; }, { deep: true });
watch(selectedTerm, (term) => { targetDraft.value = term && term.targetState === 'translated' ? term.target : ''; });

function mapTerm(row) {
  const source = row.terms?.find((term) => term.role === 'preferred' && term.lang === 'en') || row.terms?.[0];
  const target = row.terms?.find((term) => term.role === 'preferred' && term.lang !== source?.lang);
  const status = row.status || 'staging';
  return {
    ...row,
    source: source?.text || '未命名术语',
    target: target?.text || '',
    targetState: row.target_state || (target?.text ? 'translated' : 'missing'),
    forbidden: row.forbiddens || [],
    compliance: row.compliance || null,
    owner: row.authority || '术语管理员',
    risk: row.term_type === 'high_risk' ? 'high' : 'normal',
    badge: STATUS_BADGES[status] || 'pending',
    statusLabel: STATUS_LABELS[status] || '待审核',
  };
}

async function loadTerms() {
  loadError.value = '';
  try {
    const response = await api.listTerms({ limit: TERM_LIST_LIMIT });
    const rows = Array.isArray(response) ? response : response.items || [];
    terms.value = rows.map(mapTerm);
    if (selectedTerm.value) selectedTerm.value = terms.value.find((term) => term.id === selectedTerm.value.id) || null;
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
    assetCounts.value = { style: styleProfiles.value.length, pitfall: qualityRules.value.length, releases: releases.value.length };
  } catch (error) {
    // The existing termbase remains usable when a new asset endpoint is not yet deployed.
    if (!loadError.value) loadError.value = error?.network ? '语言资产服务暂时不可用。' : '语言资产加载失败，请稍后重试。';
  }
}

function resetFilters() {
  filters.value = { domain: '', layer: '', targetState: '' };
}

function selectTerm(term, focusTarget = false) {
  selectedTerm.value = term;
  nextTick(() => {
    // 窄屏上详情在列表上方，选中后把它带到视野内。
    if (window.innerWidth <= 860) detailPanel.value?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
    if (focusTarget) targetInput.value?.focus?.();
  });
}

function toggleSelect(id) {
  selectedIds.value = selectedIds.value.includes(id) ? selectedIds.value.filter((item) => item !== id) : [...selectedIds.value, id];
}

function toggleAll() {
  selectedIds.value = allVisibleSelected.value ? [] : filteredTerms.value.map((term) => term.id);
}

function explainPermission() {
  permissionNotice.value = permissionMessage;
}

function revealPanel(panelRef) {
  nextTick(() => {
    const el = panelRef.value;
    el?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
    el?.querySelector?.('input, textarea, select')?.focus?.({ preventScroll: true });
  });
}

function handleImportClick() {
  if (!canManageTerms.value) {
    explainPermission();
    return;
  }
  permissionNotice.value = '';
  showImport.value = !showImport.value;
  if (showImport.value) revealPanel(importPanel);
}

function handleNewTermClick() {
  if (!canManageTerms.value) {
    explainPermission();
    return;
  }
  permissionNotice.value = '';
  showNewTerm.value = true;
  revealPanel(newTermPanel);
}

async function readTextFile(file) {
  const buffer = await file.arrayBuffer();
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(buffer);
  } catch {
    // 常见的 Excel 导出是 GBK/GB18030，不是 UTF-8。
    return new TextDecoder('gb18030').decode(buffer);
  }
}

async function onImportFile(event) {
  const file = event.target?.files?.[0];
  if (!file) return;
  try {
    importContent.value = await readTextFile(file);
    importFileName.value = file.name;
    importResult.value = null;
  } catch (error) {
    loadError.value = error?.message || '文件读取失败';
  } finally {
    if (event.target) event.target.value = '';
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
      filename: importFileName.value || (importAssetType.value === 'termbase' ? 'terms.csv' : `${importAssetType.value}.csv`),
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
    activeView.value = 'pending';
    actionNotice.value = '已保存为待审核术语，可在“待处理”中查看。';
    await loadTerms();
  } catch (error) {
    loadError.value = error.message || '新建术语失败';
  } finally {
    creatingTerm.value = false;
  }
}

async function saveTarget() {
  if (!canManageTerms.value) {
    explainPermission();
    return;
  }
  if (!selectedTerm.value || !targetDraft.value) return;
  savingTarget.value = true;
  try {
    await api.updateConcept(selectedTerm.value.id, { preferred_target: targetDraft.value });
    actionNotice.value = `已保存“${selectedTerm.value.source}”的译名。`;
    await loadTerms();
  } catch (error) {
    loadError.value = error.message || '保存译名失败';
  } finally {
    savingTarget.value = false;
  }
}

async function setSelectedStatus(status) {
  if (!canManageTerms.value || !selectedTerm.value) {
    explainPermission();
    return;
  }
  const reject = status === 'rejected';
  const ok = await confirmDialog({
    title: reject ? `驳回“${selectedTerm.value.source}”？` : `恢复“${selectedTerm.value.source}”？`,
    body: reject ? '被驳回的术语不再参与新任务的术语匹配，已完成的任务不受影响。可在“已驳回”中随时恢复。' : '恢复后回到驳回前的状态。',
    confirmLabel: reject ? '驳回' : '恢复',
    danger: reject,
  });
  if (!ok) return;
  statusBusy.value = true;
  try {
    await api.updateConcept(selectedTerm.value.id, { status });
    actionNotice.value = reject ? '已驳回，可在“已驳回”视图恢复。' : '已恢复。';
    await loadTerms();
  } catch (error) {
    loadError.value = error.message || '操作失败';
  } finally {
    statusBusy.value = false;
  }
}

async function bulkSetStatus(status) {
  if (!canManageTerms.value) {
    explainPermission();
    return;
  }
  const ids = [...selectedIds.value];
  if (!ids.length) return;
  const reject = status === 'rejected';
  const ok = await confirmDialog({
    title: `${reject ? '驳回' : '恢复'}所选 ${ids.length} 条术语？`,
    body: reject ? '被驳回的术语不再参与新任务的术语匹配，已完成的任务不受影响。可在“已驳回”中随时恢复。' : '恢复后回到驳回前的状态。',
    confirmLabel: reject ? '驳回' : '恢复',
    danger: reject,
  });
  if (!ok) return;
  bulkBusy.value = true;
  try {
    const result = await api.batchConceptStatus({ ids, status });
    const skipped = result.skipped?.length || 0;
    actionNotice.value = `已${reject ? '驳回' : '恢复'} ${result.changed?.length || 0} 条${skipped ? `，${skipped} 条因无权限或已不存在被跳过` : ''}。`;
    selectedIds.value = [];
    await loadTerms();
  } catch (error) {
    loadError.value = error.message || '批量操作失败';
  } finally {
    bulkBusy.value = false;
  }
}

onMounted(async () => {
  await session.load();
  loadTerms();
  loadAssets();
});
</script>
