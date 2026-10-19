import { computed, reactive, ref } from 'vue';
import { api } from '../api.js';

// The task list: server-side search, filters, sort and cursor pagination (PLAN-078d).
// The URL carries the filters so a refresh, a shared link and the back button all land on the
// same list; the store keeps a stale page on screen while a new one is loading or has failed.

export const PAGE_SIZE = 25;
const MAX_POLL_ROWS = 100;

export const DEFAULT_FILTERS = Object.freeze({
  q: '',
  lifecycle: [],
  format: '',
  direction: '',
  domain: '',
  archived: 'active',
  sort: 'created',
  order: 'desc',
});

const FILTER_KEYS = Object.keys(DEFAULT_FILTERS);

export function filtersFromQuery(query = {}) {
  const filters = { ...DEFAULT_FILTERS, lifecycle: [] };
  for (const key of FILTER_KEYS) {
    const raw = query[key];
    if (raw === undefined || raw === null || raw === '') continue;
    const value = Array.isArray(raw) ? raw.join(',') : String(raw);
    filters[key] = key === 'lifecycle' ? value.split(',').filter(Boolean) : value;
  }
  return filters;
}

// Only what differs from the defaults goes into the URL.
export function filtersToQuery(filters) {
  const query = {};
  for (const key of FILTER_KEYS) {
    const value = filters[key];
    if (key === 'lifecycle') {
      if (value.length) query.lifecycle = value.join(',');
    } else if (value && value !== DEFAULT_FILTERS[key]) {
      query[key] = value;
    }
  }
  return query;
}

export function hasActiveFilters(filters) {
  return FILTER_KEYS.some((key) => (key === 'lifecycle' ? filters.lifecycle.length > 0 : filters[key] !== DEFAULT_FILTERS[key] && !['sort', 'order'].includes(key)));
}

// The recycle bin is a view of the same list: `archived=trash` in the URL, `trash=true` on the wire.
function requestParams(filters, extra = {}) {
  const params = {};
  for (const key of FILTER_KEYS) {
    const value = filters[key];
    if (key === 'lifecycle') {
      if (value.length) params.lifecycle = value.join(',');
    } else if (key === 'archived' && value === 'trash') {
      params.trash = 'true';
    } else if (value) {
      params[key] = value;
    }
  }
  return { ...params, ...extra };
}

// The same filters as a body for POST /translation-runs/selection.
export function filtersToSelectionBody(filters) {
  const trash = filters.archived === 'trash';
  return {
    q: filters.q || null,
    lifecycle: [...filters.lifecycle],
    format: filters.format ? filters.format.split(',').filter(Boolean) : [],
    direction: filters.direction || null,
    domain: filters.domain || null,
    archived: trash ? 'all' : filters.archived,
    trash,
    group_versions: true,
  };
}

export const BATCH_CHUNK = 200;

export function createRunListStore() {
  const filters = reactive({ ...DEFAULT_FILTERS, lifecycle: [] });
  const items = ref([]);
  const nextCursor = ref(null);
  const total = ref(0);
  const facets = ref({ lifecycle: {}, total: 0 });
  // 'loading' = first load or a filter change in flight, 'ready', 'error'. Rows stay on screen
  // through all three, so a slow or failed request never blanks a list the person is reading.
  const status = ref('loading');
  const error = ref('');
  const loadingMore = ref(false);
  const loaded = ref(false);
  let sequence = 0; // orders load/refresh responses
  let epoch = 0; // bumps only when the filters change, which is what makes a cursor stale

  const filtered = computed(() => hasActiveFilters(filters));

  function applyFilters(next) {
    Object.assign(filters, { ...DEFAULT_FILTERS, ...next, lifecycle: [...(next.lifecycle || [])] });
  }

  async function load() {
    const mine = ++sequence;
    epoch += 1;
    status.value = 'loading';
    if (selectedIds.value.size || allMatching.value) clearSelection(selectionNotice.value);
    try {
      const response = await api.listRuns(requestParams(filters, { page_size: PAGE_SIZE }));
      if (mine !== sequence) return false;
      const page = Array.isArray(response) ? { items: response } : response;
      items.value = page.items || [];
      nextCursor.value = page.next_cursor || null;
      total.value = page.total ?? items.value.length;
      facets.value = page.facets || { lifecycle: {}, total: total.value };
      status.value = 'ready';
      error.value = '';
      loaded.value = true;
      return true;
    } catch (failure) {
      if (mine !== sequence) return false;
      status.value = 'error';
      error.value = failure.message || '任务列表加载失败';
      return false;
    }
  }

  async function loadMore() {
    if (!nextCursor.value || loadingMore.value || status.value === 'loading') return;
    const mine = epoch;
    loadingMore.value = true;
    try {
      const response = await api.listRuns(requestParams(filters, { page_size: PAGE_SIZE, cursor: nextCursor.value }));
      if (mine !== epoch) return;
      const seen = new Set(items.value.map((item) => item.id));
      items.value = [...items.value, ...(response.items || []).filter((item) => !seen.has(item.id))];
      nextCursor.value = response.next_cursor || null;
      total.value = response.total ?? total.value;
      facets.value = response.facets || facets.value;
    } catch (failure) {
      if (mine === epoch) {
        status.value = 'error';
        error.value = failure.message || '加载更多失败';
      }
    } finally {
      loadingMore.value = false;
    }
  }

  // Polling re-reads the rows already on screen (up to MAX_POLL_ROWS) so progress keeps moving
  // without throwing away the pages the person has scrolled through.
  async function refresh() {
    if (!loaded.value) return load();
    const mine = ++sequence;
    const shown = items.value.length;
    const size = Math.min(Math.max(shown, PAGE_SIZE), MAX_POLL_ROWS);
    try {
      const response = await api.listRuns(requestParams(filters, { page_size: size }));
      if (mine !== sequence) return false;
      const head = response.items || [];
      const fresh = new Set(head.map((item) => item.id));
      const tail = shown > size ? items.value.slice(size).filter((item) => !fresh.has(item.id)) : [];
      items.value = [...head, ...tail];
      if (!tail.length) nextCursor.value = response.next_cursor || null;
      total.value = response.total ?? total.value;
      facets.value = response.facets || facets.value;
      status.value = 'ready';
      error.value = '';
      return true;
    } catch (failure) {
      if (mine !== sequence) return false;
      status.value = 'error';
      error.value = failure.message || '任务列表刷新失败';
      return false;
    }
  }

  // ---- selection (PLAN-078e) ---------------------------------------------------------------------------
  // Either a set of ticked rows, or "everything the filters match" frozen on the server (a token plus
  // the rows the person then unticked). A filter, sort or view change always starts a new selection.
  const selectedIds = ref(new Set());
  const allMatching = ref(null); // { token, count, scope, excluded: Set }
  const selectionNotice = ref('');
  const selectionBusy = ref(false);

  const selectionCount = computed(() => (
    allMatching.value
      ? Math.max(0, allMatching.value.count - allMatching.value.excluded.size)
      : selectedIds.value.size
  ));
  const pageSelected = computed(() => items.value.length > 0 && items.value.every((item) => isSelected(item.id)));
  const selectedRows = computed(() => items.value.filter((item) => isSelected(item.id)));

  function isSelected(id) {
    return allMatching.value ? !allMatching.value.excluded.has(id) : selectedIds.value.has(id);
  }

  function toggle(id) {
    selectionNotice.value = '';
    if (allMatching.value) {
      const excluded = new Set(allMatching.value.excluded);
      if (excluded.has(id)) excluded.delete(id); else excluded.add(id);
      allMatching.value = { ...allMatching.value, excluded };
      return;
    }
    const next = new Set(selectedIds.value);
    if (next.has(id)) next.delete(id); else next.add(id);
    selectedIds.value = next;
  }

  function selectPage() {
    selectionNotice.value = '';
    allMatching.value = null;
    selectedIds.value = new Set([...selectedIds.value, ...items.value.map((item) => item.id)]);
  }

  function selectOnly(id) {
    selectionNotice.value = '';
    allMatching.value = null;
    selectedIds.value = new Set([id]);
  }

  function clearSelection(notice = '') {
    allMatching.value = null;
    selectedIds.value = new Set();
    selectionNotice.value = notice;
  }

  async function selectAllMatching() {
    selectionBusy.value = true;
    try {
      const response = await api.createRunSelection(filtersToSelectionBody(filters));
      allMatching.value = {
        token: response.selection_token,
        count: response.count,
        scope: response.scope,
        excluded: new Set(),
      };
      selectedIds.value = new Set();
      selectionNotice.value = '';
    } finally {
      selectionBusy.value = false;
    }
  }

  function newAttemptId() {
    return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  // Run one action over the selection (or over `onlyIds`, for "retry the failed ones") and return one
  // combined result. Explicit ids go out in chunks the server accepts; each chunk has its own key.
  async function runBatch(action, { onlyIds = null } = {}) {
    const attempt = newAttemptId();
    const combined = { action, requested: 0, succeeded: 0, failed: 0, skipped: 0, items: [] };
    const merge = (part) => {
      combined.requested += part.requested;
      combined.succeeded += part.succeeded;
      combined.failed += part.failed;
      combined.skipped += part.skipped;
      combined.items.push(...part.items);
    };
    if (!onlyIds && allMatching.value) {
      merge(await api.batchRuns({
        action,
        selection_token: allMatching.value.token,
        exclude_ids: [...allMatching.value.excluded],
      }, `${attempt}:all`));
      return combined;
    }
    const ids = onlyIds || [...selectedIds.value];
    for (let start = 0; start < ids.length; start += BATCH_CHUNK) {
      merge(await api.batchRuns({ action, ids: ids.slice(start, start + BATCH_CHUNK) }, `${attempt}:${start}`));
    }
    return combined;
  }

  function reset() {
    clearSelection();
    sequence += 1;
    epoch += 1;
    applyFilters({});
    items.value = [];
    nextCursor.value = null;
    total.value = 0;
    facets.value = { lifecycle: {}, total: 0 };
    status.value = 'loading';
    error.value = '';
    loadingMore.value = false;
    loaded.value = false;
  }

  function patchItem(runId, patch) {
    items.value = items.value.map((item) => (item.id === runId ? { ...item, ...patch } : item));
  }

  return {
    filters,
    items,
    nextCursor,
    total,
    facets,
    status,
    error,
    loadingMore,
    loaded,
    filtered,
    applyFilters,
    load,
    loadMore,
    refresh,
    reset,
    patchItem,
    selectedIds,
    allMatching,
    selectionNotice,
    selectionBusy,
    selectionCount,
    pageSelected,
    selectedRows,
    isSelected,
    toggle,
    selectPage,
    selectOnly,
    clearSelection,
    selectAllMatching,
    runBatch,
  };
}

// One list for the whole app session: leaving for a task and coming back shows the same rows at the
// same place, then refreshes them in the background.
export const runList = createRunListStore();
export const listView = { scrollY: 0, openedId: '' };
