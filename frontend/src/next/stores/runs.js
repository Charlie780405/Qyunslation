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

function requestParams(filters, extra = {}) {
  const params = {};
  for (const key of FILTER_KEYS) {
    const value = filters[key];
    if (key === 'lifecycle') {
      if (value.length) params.lifecycle = value.join(',');
    } else if (value) {
      params[key] = value;
    }
  }
  return { ...params, ...extra };
}

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

  function reset() {
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
  };
}

// One list for the whole app session: leaving for a task and coming back shows the same rows at the
// same place, then refreshes them in the background.
export const runList = createRunListStore();
export const listView = { scrollY: 0, openedId: '' };
