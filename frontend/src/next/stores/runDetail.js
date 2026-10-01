import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';

export const MIN_ZOOM = 0.25;
export const MAX_ZOOM = 4;
export const ZOOM_STEP = 0.25;

export const DEFAULT_VIEW_STATE = Object.freeze({
  page: 1,
  zoom: 'fit',
  objectId: '',
  sync: true,
});

const VIEW_KEYS = ['page', 'zoom', 'obj', 'sync'];

function first(value) {
  return Array.isArray(value) ? value[0] : value;
}

export function clampZoom(value) {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.round(value * 100) / 100));
}

export function parseViewState(query = {}) {
  const state = { ...DEFAULT_VIEW_STATE };

  const rawPage = first(query.page);
  if (typeof rawPage === 'string' && /^\d{1,6}$/.test(rawPage) && Number(rawPage) >= 1) {
    state.page = Number(rawPage);
  }

  const rawZoom = first(query.zoom);
  if (rawZoom === 'fit') {
    state.zoom = 'fit';
  } else if (typeof rawZoom === 'string' && /^\d+(\.\d+)?$/.test(rawZoom)) {
    const value = Number(rawZoom);
    if (value >= MIN_ZOOM && value <= MAX_ZOOM) state.zoom = value;
  }

  const rawObj = first(query.obj);
  if (typeof rawObj === 'string' && rawObj.length > 0 && rawObj.length <= 200) {
    state.objectId = rawObj;
  }

  const rawSync = first(query.sync);
  if (rawSync === '0' || rawSync === 'false') state.sync = false;
  else if (rawSync === '1' || rawSync === 'true') state.sync = true;

  return state;
}

// Defaults are omitted so shared links stay short; parseViewState restores them.
export function serializeViewState(state = {}) {
  const merged = { ...DEFAULT_VIEW_STATE, ...state };
  const parsed = parseViewState({
    page: String(merged.page),
    zoom: String(merged.zoom),
    obj: merged.objectId || '',
    sync: merged.sync ? '1' : '0',
  });
  const query = {};
  if (parsed.page !== DEFAULT_VIEW_STATE.page) query.page = String(parsed.page);
  if (parsed.zoom !== DEFAULT_VIEW_STATE.zoom) query.zoom = String(parsed.zoom);
  if (parsed.objectId) query.obj = parsed.objectId;
  if (parsed.sync !== DEFAULT_VIEW_STATE.sync) query.sync = parsed.sync ? '1' : '0';
  return query;
}

export function mergeViewQuery(currentQuery, state) {
  const next = { ...currentQuery };
  for (const key of VIEW_KEYS) delete next[key];
  return { ...next, ...serializeViewState(state) };
}

export function useRunDetailView() {
  const route = useRoute();
  const router = useRouter();

  const state = computed(() => parseViewState(route.query));

  function update(patch) {
    const next = { ...state.value, ...patch };
    const query = mergeViewQuery(route.query, next);
    return router.replace({ query });
  }

  return {
    state,
    page: computed(() => state.value.page),
    zoom: computed(() => state.value.zoom),
    selectedObjectId: computed(() => state.value.objectId),
    sync: computed(() => state.value.sync),
    setPage: (page) => update({ page: Math.max(1, Math.floor(Number(page) || 1)) }),
    setZoom: (zoom) => update({ zoom: zoom === 'fit' ? 'fit' : clampZoom(Number(zoom) || 1) }),
    setSync: (sync) => update({ sync: Boolean(sync) }),
    selectObject: (objectId) => update({ objectId: objectId || '' }),
  };
}
