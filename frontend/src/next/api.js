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
  listRuns: () => apiRequest(`${API_PREFIX}/translation-runs`),
  getRun: (runId) => apiRequest(`${API_PREFIX}/translation-runs/${encodeURIComponent(runId)}`),
  cancelRun: (runId) => apiRequest(`${API_PREFIX}/translation-runs/${encodeURIComponent(runId)}/cancel`, { method: 'POST' }),
  retryRun: (runId) => apiRequest(`${API_PREFIX}/translation-runs/${encodeURIComponent(runId)}/retry`, { method: 'POST' }),
  listTerms: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return apiRequest(`${API_PREFIX}/concepts${query ? `?${query}` : ''}`);
  },
  uploadPreflight: (file, fields = {}) => {
    const body = new FormData();
    body.append('file', file);
    Object.entries(fields).forEach(([key, value]) => body.append(key, String(value)));
    return apiRequest(`${API_PREFIX}/preflights`, { method: 'POST', body });
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
