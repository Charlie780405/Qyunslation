import { reactive, ref } from 'vue';
import { api } from '../api.js';

const DEFAULT_SETTINGS = {
  sourceLanguage: 'English',
  targetLanguage: '简体中文',
  profile: '临床研究文档',
  bilingual: true,
  classification: 'internal',
  modelProfileId: 'internal-qwen-quality',
};

export const workbenchState = reactive({ ...DEFAULT_SETTINGS });
export const restoredPreflight = ref(null);
export const restoring = ref(false);

function applyWorkbenchPreferences(preferences = {}) {
  const wb = preferences.workbench || preferences;
  Object.assign(workbenchState, {
    sourceLanguage: wb.sourceLanguage || DEFAULT_SETTINGS.sourceLanguage,
    targetLanguage: wb.targetLanguage || DEFAULT_SETTINGS.targetLanguage,
    profile: wb.profile || DEFAULT_SETTINGS.profile,
    bilingual: wb.bilingual ?? DEFAULT_SETTINGS.bilingual,
    classification: wb.classification || DEFAULT_SETTINGS.classification,
    modelProfileId: wb.modelProfileId || DEFAULT_SETTINGS.modelProfileId,
  });
}

let saveTimer;
export function scheduleWorkbenchPreferenceSave() {
  window.clearTimeout(saveTimer);
  saveTimer = window.setTimeout(async () => {
    try {
      const current = await api.getPreferences();
      const merged = {
        ...(current.preferences || {}),
        workbench: { ...workbenchState },
      };
      await api.savePreferences(merged);
    } catch {
      /* ignore transient preference errors */
    }
  }, 600);
}

export function uploadStorageKey(tenantSlug, sub) {
  const ns = `${tenantSlug || 'tenant'}:${sub || 'user'}`;
  return `qyunslation:upload:${ns}`;
}

export async function restoreWorkbenchSession(sessionUser) {
  restoring.value = true;
  try {
    const pref = await api.getPreferences();
    applyWorkbenchPreferences(pref.preferences || {});
    const listed = await api.listPreflights();
    if (listed.latest) {
      restoredPreflight.value = listed.latest;
    }
    const uploadKey = uploadStorageKey(sessionUser?.tenant_slug, sessionUser?.sub);
    const pendingUploadId = window.localStorage.getItem(uploadKey);
    if (pendingUploadId) {
      try {
        const status = await api.getUploadSession(pendingUploadId);
        if (status.status === 'uploading' && !status.complete) {
          restoredPreflight.value = restoredPreflight.value || {
            resume_upload: status,
            upload_id: pendingUploadId,
          };
        } else {
          window.localStorage.removeItem(uploadKey);
        }
      } catch {
        window.localStorage.removeItem(uploadKey);
      }
    }
  } finally {
    restoring.value = false;
  }
}
