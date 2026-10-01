const API_PREFIX = '/api/v1';

function csrfToken() {
  if (window.__QY_CSRF_TOKEN__) return window.__QY_CSRF_TOKEN__;
  const meta = document.querySelector('meta[name="csrf-token"]')?.content;
  if (meta) return meta;
  const cookie = document.cookie
    .split('; ')
    .find((entry) => entry.startsWith('qyunslation_csrf='));
  return cookie ? decodeURIComponent(cookie.slice('qyunslation_csrf='.length)) : '';
}

export async function apiRequest(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }
  const method = (options.method || 'GET').toUpperCase();
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const token = csrfToken();
    if (token) headers.set('X-CSRF-Token', token);
  }

  const response = await fetch(path, { ...options, headers, credentials: 'same-origin' });
  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json')
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const detail = typeof payload === 'object' && payload
      ? payload.message || payload.detail || payload.code
      : payload;
    const error = new Error(detail || `请求失败（${response.status}）`);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

export const api = {
  me: () => apiRequest(`${API_PREFIX}/me`),
  listRuns: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return apiRequest(`${API_PREFIX}/translation-runs${query ? `?${query}` : ''}`);
  },
  getRun: (runId) => apiRequest(`${API_PREFIX}/translation-runs/${encodeURIComponent(runId)}`),
  patchRun: (runId, payload) => apiRequest(`${API_PREFIX}/translation-runs/${encodeURIComponent(runId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  }),
  restoreRun: (runId) => apiRequest(`${API_PREFIX}/translation-runs/${encodeURIComponent(runId)}/restore`, { method: 'POST' }),
  deleteRun: (runId) => apiRequest(`${API_PREFIX}/translation-runs/${encodeURIComponent(runId)}`, { method: 'DELETE' }),
  cancelRun: (runId) => apiRequest(`${API_PREFIX}/translation-runs/${encodeURIComponent(runId)}/cancel`, { method: 'POST' }),
  retryRun: (runId, payload = {}) => apiRequest(`${API_PREFIX}/translation-runs/${encodeURIComponent(runId)}/retry`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  getRunEvents: (runId, params = {}) => {
    const query = new URLSearchParams(params).toString();
    return apiRequest(`${API_PREFIX}/translation-runs/${encodeURIComponent(runId)}/events${query ? `?${query}` : ''}`);
  },
  getQaItems: (runId) => apiRequest(`${API_PREFIX}/translation-runs/${encodeURIComponent(runId)}/qa-items`),
  postReviewDecision: (runId, payload) => apiRequest(`${API_PREFIX}/translation-runs/${encodeURIComponent(runId)}/review-decision`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  patchPreflight: (preflightId, payload) => apiRequest(`${API_PREFIX}/preflights/${encodeURIComponent(preflightId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  }),
  listModelProfiles: (classification = 'internal') => apiRequest(`${API_PREFIX}/model-profiles?classification=${encodeURIComponent(classification)}`),
  getSettingsSchema: () => apiRequest(`${API_PREFIX}/settings/schema`),
  getSettingsEffective: () => apiRequest(`${API_PREFIX}/settings/effective`),
  getAdminPolicies: () => apiRequest(`${API_PREFIX}/admin/policies`),
  putAdminPolicies: (payload) => apiRequest(`${API_PREFIX}/admin/policies`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  }),
  previewUrl: (runId, side) => `${API_PREFIX}/translation-runs/${encodeURIComponent(runId)}/preview/${encodeURIComponent(side)}`,
  listTerms: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return apiRequest(`${API_PREFIX}/concepts${query ? `?${query}` : ''}`);
  },
  uploadPreflight: (file, fields = {}, onProgress = null) => {
    const body = new FormData();
    body.append('file', file);
    Object.entries(fields).forEach(([key, value]) => body.append(key, String(value)));
    return new Promise((resolve, reject) => {
      const request = new XMLHttpRequest();
      request.open('POST', `${API_PREFIX}/preflights`);
      request.withCredentials = true;
      const token = csrfToken();
      if (token) request.setRequestHeader('X-CSRF-Token', token);
      request.upload.onprogress = (event) => {
        if (event.lengthComputable && typeof onProgress === 'function') {
          onProgress(Math.round((event.loaded / event.total) * 100));
        }
      };
      request.onload = () => {
        const contentType = request.getResponseHeader('content-type') || '';
        let payload = request.responseText;
        if (contentType.includes('application/json')) {
          try { payload = JSON.parse(request.responseText); } catch { /* fall through */ }
        }
        if (request.status >= 200 && request.status < 300) {
          resolve(payload);
          return;
        }
        const detail = typeof payload === 'object' && payload
          ? payload.message || payload.detail || payload.code
          : payload;
        const error = new Error(detail || `请求失败（${request.status}）`);
        error.status = request.status;
        error.payload = payload;
        reject(error);
      };
      request.onerror = () => reject(new Error('网络连接失败，请重试'));
      request.onabort = () => reject(new Error('上传已取消'));
      request.send(body);
    });
  },
  createTranslationRun: (payload, idempotencyKey) => apiRequest(`${API_PREFIX}/translation-runs`, {
    method: 'POST',
    headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {},
    body: JSON.stringify(payload),
  }),
  savePreferences: (preferences) => apiRequest(`${API_PREFIX}/preferences`, {
    method: 'PUT',
    body: JSON.stringify(preferences),
  }),
  getPreferences: () => apiRequest(`${API_PREFIX}/preferences`),
  logout: () => apiRequest('/auth/logout', { method: 'POST' }),
};
