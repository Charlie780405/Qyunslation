const API_PREFIX = '/api/v1';

function formatApiDetail(payload) {
  if (!payload || typeof payload !== 'object') return payload;
  const detail = payload.detail ?? payload.message ?? payload.code;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((entry) => (
      typeof entry === 'string' ? entry : entry?.msg || JSON.stringify(entry)
    )).join('；');
  }
  if (detail && typeof detail === 'object') {
    return detail.message || JSON.stringify(detail);
  }
  return null;
}

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
      ? (formatApiDetail(payload) || payload.message || payload.code)
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
  listPreflights: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return apiRequest(`${API_PREFIX}/preflights${query ? `?${query}` : ''}`);
  },
  patchPreflight: (preflightId, payload) => apiRequest(`${API_PREFIX}/preflights/${encodeURIComponent(preflightId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  }),
  createUploadSession: (payload) => apiRequest(`${API_PREFIX}/upload-sessions`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  getUploadSession: (uploadId) => apiRequest(`${API_PREFIX}/upload-sessions/${encodeURIComponent(uploadId)}`),
  appendUploadSession: (uploadId, chunk, start, end, total) => apiRequest(
    `${API_PREFIX}/upload-sessions/${encodeURIComponent(uploadId)}`,
    {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/octet-stream',
        'Content-Range': `bytes ${start}-${end}/${total}`,
      },
      body: chunk,
    },
  ),
  completeUploadSession: (uploadId, fields = {}) => apiRequest(
    `${API_PREFIX}/upload-sessions/${encodeURIComponent(uploadId)}/complete`,
    {
      method: 'POST',
      body: JSON.stringify(fields),
    },
  ),
  resumeRun: (runId) => apiRequest(`${API_PREFIX}/translation-runs/${encodeURIComponent(runId)}/resume`, {
    method: 'POST',
  }),
  requalifyRun: (runId) => apiRequest(`${API_PREFIX}/translation-runs/${encodeURIComponent(runId)}/requalify`, {
    method: 'POST',
  }),
  listRunTermCandidates: (runId, params = {}) => {
    const query = new URLSearchParams(params).toString();
    return apiRequest(`${API_PREFIX}/translation-runs/${encodeURIComponent(runId)}/term-candidates${query ? `?${query}` : ''}`);
  },
  decideRunTermCandidate: (runId, candidateId, payload) => apiRequest(
    `${API_PREFIX}/translation-runs/${encodeURIComponent(runId)}/term-candidates/${encodeURIComponent(candidateId)}/decision`,
    { method: 'POST', body: JSON.stringify(payload) },
  ),
  batchDecideRunTermCandidates: (runId, decisions) => apiRequest(
    `${API_PREFIX}/translation-runs/${encodeURIComponent(runId)}/term-candidates/batch-decision`,
    { method: 'POST', body: JSON.stringify({ decisions }) },
  ),
  enrichRunTermSuggestions: (runId) => apiRequest(
    `${API_PREFIX}/translation-runs/${encodeURIComponent(runId)}/term-candidates/enrich-suggestions`,
    { method: 'POST' },
  ),
  listRunAffiliationSegments: (runId) => apiRequest(
    `${API_PREFIX}/translation-runs/${encodeURIComponent(runId)}/affiliation-segments`,
  ),
  decideRunAffiliationSegment: (runId, segmentId, payload) => apiRequest(
    `${API_PREFIX}/translation-runs/${encodeURIComponent(runId)}/affiliation-segments/${encodeURIComponent(segmentId)}`,
    { method: 'PATCH', body: JSON.stringify(payload) },
  ),
  applyRunCorrections: (runId) => apiRequest(
    `${API_PREFIX}/translation-runs/${encodeURIComponent(runId)}/apply-corrections`,
    { method: 'POST' },
  ),
  getReviewDraft: (runId) => apiRequest(`${API_PREFIX}/translation-runs/${encodeURIComponent(runId)}/review-draft`),
  saveReviewDraft: (runId, payload) => apiRequest(`${API_PREFIX}/translation-runs/${encodeURIComponent(runId)}/review-draft`, {
    method: 'PUT',
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
  uploadPreflightResumable: async (file, fields = {}, onProgress = null, storageKey = null) => {
    const chunkSize = 1024 * 1024;
    const create = await api.createUploadSession({
      filename: file.name,
      total_size: file.size,
    });
    if (create.reused_preflight) {
      return create.reused_preflight;
    }
    const session = create.upload_session || create;
    const uploadId = session.id;
    if (storageKey) {
      window.localStorage.setItem(storageKey, uploadId);
    }
    let offset = session.received_bytes || 0;
    while (offset < file.size) {
      const end = Math.min(offset + chunkSize, file.size) - 1;
      const chunk = file.slice(offset, end + 1);
      const status = await api.appendUploadSession(uploadId, chunk, offset, end, file.size);
      offset = status.received_bytes;
      if (typeof onProgress === 'function') {
        onProgress(Math.round((offset / file.size) * 100));
      }
    }
    const preflight = await api.completeUploadSession(uploadId, fields);
    if (storageKey) {
      window.localStorage.removeItem(storageKey);
    }
    return preflight;
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
