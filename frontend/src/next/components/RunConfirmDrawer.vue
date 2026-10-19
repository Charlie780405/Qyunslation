<template>
  <div class="qy-drawer-backdrop" @click.self="$emit('close')">
    <aside
      ref="rootEl"
      class="qy-confirm-drawer"
      data-run-confirm
      role="dialog"
      aria-modal="true"
      :aria-labelledby="titleId"
      tabindex="-1"
      @keydown="onKeydown"
    >
      <header class="qy-confirm-head">
        <div>
          <h2 :id="titleId">{{ title }}</h2>
          <p class="qy-muted">{{ subtitle }}</p>
        </div>
        <button type="button" class="qy-icon-button" aria-label="关闭" @click="$emit('close')">×</button>
      </header>

      <section class="qy-confirm-file" aria-label="文件">
        <strong>{{ fileName }}</strong>
        <span v-if="fileMeta">{{ fileMeta }}</span>
      </section>

      <!-- new task: every setting is editable -->
      <form v-if="mode === 'new'" class="qy-confirm-form" @submit.prevent="submit">
        <p v-if="last && lastDiffers" class="qy-confirm-last">
          <button type="button" class="qy-link-button" data-use-last @click="useLast">沿用{{ last.label || '上次任务' }}的配置</button>
        </p>

        <div class="qy-confirm-row" data-field-row="name">
          <label class="qy-field"><span>任务名称</span>
            <input v-model="form.name" data-field="name" type="text" maxlength="120" :placeholder="defaultName" />
          </label>
          <small class="qy-field-source">默认取原文件名，可修改</small>
        </div>

        <div class="qy-confirm-row" data-field-row="sourceLanguage">
          <label class="qy-field"><span>源语言</span>
            <select v-model="form.sourceLanguage" data-field="sourceLanguage"><option v-for="l in LANGUAGES" :key="l" :value="l">{{ l }}</option></select>
          </label>
          <small class="qy-field-source">{{ sourceLabel('sourceLanguage') }}<template v-if="differs('sourceLanguage')"> · <span class="qy-field-diff">{{ diffNote('sourceLanguage') }}</span></template></small>
        </div>
        <div class="qy-confirm-row" data-field-row="targetLanguage">
          <label class="qy-field"><span>目标语言</span>
            <select v-model="form.targetLanguage" data-field="targetLanguage"><option v-for="l in LANGUAGES" :key="l" :value="l">{{ l }}</option></select>
          </label>
          <small class="qy-field-source">{{ sourceLabel('targetLanguage') }}<template v-if="differs('targetLanguage')"> · <span class="qy-field-diff">{{ diffNote('targetLanguage') }}</span></template></small>
        </div>

        <div class="qy-confirm-row" data-field-row="profile">
          <label class="qy-field"><span>文档类型</span>
            <select v-model="form.profile" data-field="profile"><option v-for="p in documentProfiles" :key="p" :value="p">{{ p }}</option></select>
          </label>
          <small class="qy-field-source">{{ sourceLabel('profile') }}<template v-if="differs('profile')"> · <span class="qy-field-diff">{{ diffNote('profile') }}</span></template></small>
        </div>

        <div class="qy-confirm-row" data-field-row="domainProfile">
          <label class="qy-field"><span>专业领域</span>
            <select v-model="form.domainProfile" data-field="domainProfile">
              <option value="general">通用医药翻译</option>
              <option v-if="adEnabled" value="ad">AD 特应性皮炎（内部测试版）</option>
            </select>
          </label>
          <small class="qy-field-source">{{ sourceLabel('domainProfile') }}<template v-if="differs('domainProfile')"> · <span class="qy-field-diff">{{ diffNote('domainProfile') }}</span></template></small>
        </div>

        <div class="qy-confirm-row" data-field-row="classification">
          <label class="qy-field"><span>资料等级</span>
            <select v-model="form.classification" data-field="classification">
              <option v-for="(label, value) in CLASSIFICATIONS" :key="value" :value="value">{{ label }}</option>
            </select>
          </label>
          <small class="qy-field-source">{{ sourceLabel('classification') }}<template v-if="differs('classification')"> · <span class="qy-field-diff">{{ diffNote('classification') }}</span></template></small>
        </div>

        <div class="qy-confirm-row" data-field-row="modelProfileId">
          <label class="qy-field"><span>翻译模型</span>
            <select v-model="form.modelProfileId" data-field="modelProfileId">
              <option v-for="p in translators" :key="p.profile_id" :value="p.profile_id" :disabled="!p.configured">{{ p.label }}{{ p.configured ? '' : '（未配置）' }}</option>
            </select>
          </label>
          <small class="qy-field-source">
            {{ sourceLabel('modelProfileId') }}<template v-if="differs('modelProfileId')"> · <span class="qy-field-diff">{{ diffNote('modelProfileId') }}</span></template>
            <template v-if="egressText"> · {{ egressText }}</template>
          </small>
          <p v-if="modelNotice" class="qy-confirm-notice" role="status">{{ modelNotice }}</p>
        </div>

        <div class="qy-confirm-row" data-field-row="bilingual">
          <label class="qy-check-field">
            <input v-model="form.bilingual" data-field="bilingual" type="checkbox" :disabled="!pdf" />
            <span>生成源译对照稿</span>
          </label>
          <small class="qy-field-source">
            <template v-if="!pdf">仅 PDF 支持源译对照；当前格式只输出译文。</template>
            <template v-else>{{ sourceLabel('bilingual') }}<template v-if="differs('bilingual')"> · <span class="qy-field-diff">{{ diffNote('bilingual') }}</span></template></template>
          </small>
        </div>

        <section class="qy-confirm-qa" data-qa-policy aria-label="质量检查策略">
          <h3>质量检查</h3>
          <p>确定性 QA + 术语抽取<template v-if="termModelLabel">（{{ termModelLabel }}）</template>。</p>
          <p v-if="!termModelLabel" class="qy-muted">校验完成后显示实际使用的术语模型。</p>
        </section>

        <section class="qy-confirm-validation" data-validation aria-live="polite" aria-label="参数校验">
          <p v-if="validating" class="qy-muted">正在校验参数…</p>
          <p v-if="validationError" class="qy-confirm-error" role="alert">
            校验失败：{{ validationError }} <button type="button" class="qy-link-button" @click="runValidation">重试</button>
          </p>
          <ul v-if="errors.length" class="qy-confirm-errors">
            <li v-for="(issue, index) in errors" :key="`e${index}`" role="alert">
              {{ issue.message }}
              <button v-if="issue.can_copy" type="button" class="qy-link-button" data-copy-preflight @click="$emit('copy-preflight')">复制预检后用新参数继续</button>
            </li>
          </ul>
          <ul v-if="warnings.length" class="qy-confirm-warnings">
            <li v-for="(issue, index) in warnings" :key="`w${index}`" data-warning>{{ issue.message }}</li>
          </ul>
          <p v-if="isFresh && !errors.length && !validationError" class="qy-confirm-ok">✓ 参数校验通过</p>
        </section>

        <fieldset class="qy-confirm-save">
          <legend>保存方式</legend>
          <label><input v-model="saveMode" type="radio" name="save-mode" value="once" /> 仅本次生效（默认）</label>
          <label><input v-model="saveMode" type="radio" name="save-mode" value="default" /> 同时保存为以后的默认参数</label>
        </fieldset>

        <p v-if="submitError" class="qy-confirm-error" role="alert" data-submit-error>{{ submitError }}</p>
        <footer class="qy-confirm-actions">
          <button type="button" class="qy-secondary-button" @click="$emit('close')">返回修改</button>
          <button type="submit" class="qy-primary-button" data-confirm :disabled="Boolean(disabledReason)">{{ submitting ? '正在创建任务…' : '确认并开始翻译' }}</button>
          <span v-if="disabledReason" class="qy-muted" data-disabled-reason>{{ disabledReason }}</span>
        </footer>
      </form>

      <!-- a new version of an existing task: configuration is frozen, safe parameters may change -->
      <form v-else class="qy-confirm-form" @submit.prevent="submit">
        <section class="qy-confirm-frozen" aria-label="已冻结的配置">
          <h3>原任务的冻结配置</h3>
          <dl>
            <dt>语言方向</dt><dd>{{ frozen.direction }}</dd>
            <dt>文档类型</dt><dd>{{ frozen.profile }}</dd>
            <dt>专业领域</dt><dd>{{ frozen.domain }}</dd>
            <template v-if="mode === 'resume'">
              <dt>资料等级</dt><dd>{{ CLASSIFICATIONS[form.classification] || form.classification }}</dd>
              <dt>翻译模型</dt><dd>{{ modelLabelOf(form.modelProfileId) }}</dd>
              <dt>源译对照稿</dt><dd>{{ form.bilingual ? '生成' : '不生成' }}</dd>
            </template>
          </dl>
          <p class="qy-muted">{{ mode === 'resume' ? '续跑沿用以上冻结配置，不会改变任何参数。需要改参数请使用“生成修订版”。' : '以下参数冻结，修改它们需要从原文件新建任务。' }}</p>
        </section>

        <template v-if="mode === 'revision'">
          <p v-if="isAd" class="qy-confirm-notice">AD 任务的模型和资料等级与已冻结的提示词绑定，如需修改请从原文件新建任务。</p>
          <div class="qy-confirm-row" data-field-row="name">
            <label class="qy-field"><span>任务名称</span><input v-model="form.name" data-field="name" type="text" maxlength="120" /></label>
          </div>
          <div class="qy-confirm-row" data-field-row="classification">
            <label class="qy-field"><span>资料等级</span>
              <select v-model="form.classification" data-field="classification" :disabled="isAd">
                <option v-for="(label, value) in CLASSIFICATIONS" :key="value" :value="value">{{ label }}</option>
              </select>
            </label>
            <small class="qy-field-source">{{ changed('classification') ? '本次修改' : '沿用原配置' }}</small>
          </div>
          <div class="qy-confirm-row" data-field-row="modelProfileId">
            <label class="qy-field"><span>翻译模型</span>
              <select v-model="form.modelProfileId" data-field="modelProfileId" :disabled="isAd">
                <option v-for="p in translators" :key="p.profile_id" :value="p.profile_id" :disabled="!p.configured">{{ p.label }}{{ p.configured ? '' : '（未配置）' }}</option>
              </select>
            </label>
            <small class="qy-field-source">{{ changed('modelProfileId') ? '本次修改' : '沿用原配置' }}<template v-if="egressText"> · {{ egressText }}</template></small>
            <p v-if="modelNotice" class="qy-confirm-notice" role="status">{{ modelNotice }}</p>
          </div>
          <div class="qy-confirm-row" data-field-row="bilingual">
            <label class="qy-check-field"><input v-model="form.bilingual" data-field="bilingual" type="checkbox" :disabled="!pdf" /><span>生成源译对照稿</span></label>
            <small class="qy-field-source"><template v-if="!pdf">仅 PDF 支持源译对照；当前格式只输出译文。</template><template v-else>{{ changed('bilingual') ? '本次修改' : '沿用原配置' }}</template></small>
          </div>
          <p class="qy-muted">将重新翻译全文并重新做质量检查；原版本保持冻结，其中的问题和处置记录不受影响。</p>
        </template>

        <p v-if="submitError" class="qy-confirm-error" role="alert" data-submit-error>{{ submitError }}</p>
        <footer class="qy-confirm-actions">
          <button type="button" class="qy-secondary-button" @click="$emit('close')">返回</button>
          <button type="submit" class="qy-primary-button" data-confirm :disabled="Boolean(disabledReason)">{{ submitting ? '正在提交…' : confirmLabel }}</button>
          <span v-if="disabledReason" class="qy-muted" data-disabled-reason>{{ disabledReason }}</span>
        </footer>
      </form>
    </aside>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { api } from '../api.js';

const props = defineProps({
  mode: { type: String, default: 'new' }, // new | revision | resume
  preflight: { type: Object, default: null },
  run: { type: Object, default: null },
  initial: { type: Object, default: () => ({}) },
  defaults: { type: Object, default: () => ({}) },
  last: { type: Object, default: null },
  initialSource: { type: String, default: '上次使用' },
  adEnabled: { type: Boolean, default: false },
  onSubmit: { type: Function, default: null },
});
const emit = defineEmits(['close', 'copy-preflight']);

const LANGUAGES = ['English', '简体中文'];
const CLASSIFICATIONS = { internal: '内部', confidential: '机密', public: '公开' };
const AD_PROFILES = ['医学研究文献', '临床研究文档'];
const GENERAL_PROFILES = ['临床研究文档', '监管申报材料', '通用医药文档'];

let counter = 0;
const titleId = `qy-confirm-title-${Date.now()}-${(counter += 1)}`;
const rootEl = ref(null);
let opener = null;

// ---- the configuration being confirmed -----------------------------------------------------
function stem(name) {
  return String(name || '').replace(/\.[^.]+$/, '');
}
const fileName = computed(() => props.mode === 'new' ? (props.preflight?.filename || '') : (props.run?.filename || '未命名文档'));
const fileFormat = computed(() => String(props.mode === 'new' ? props.preflight?.format : props.run?.format || '').toLowerCase());
const pdf = computed(() => !fileFormat.value || fileFormat.value === 'pdf');
const defaultName = computed(() => stem(fileName.value));
const fileMeta = computed(() => {
  if (props.mode !== 'new') return '';
  const size = props.preflight?.size_bytes;
  const kb = size ? (size >= 1048576 ? `${(size / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(size / 1024))} KB`) : '';
  return [String(props.preflight?.format || '').toUpperCase(), kb, '预检通过'].filter(Boolean).join(' · ');
});

function startOf() {
  if (props.mode === 'new') {
    return {
      name: props.initial.displayName || '',
      sourceLanguage: props.initial.sourceLanguage || 'English',
      targetLanguage: props.initial.targetLanguage || '简体中文',
      profile: props.initial.profile || '临床研究文档',
      domainProfile: props.initial.domainProfile || 'general',
      classification: props.initial.classification || 'internal',
      modelProfileId: props.initial.modelProfileId || '',
      bilingual: props.initial.bilingual ?? true,
    };
  }
  const run = props.run || {};
  const settings = run.settings || {};
  return {
    name: run.display_name || '',
    sourceLanguage: settings.source_language || 'English',
    targetLanguage: settings.target_language || '简体中文',
    profile: settings.profile || run.profile || '',
    domainProfile: settings.domain_profile || 'general',
    classification: run.document_classification || settings.document_classification || 'internal',
    modelProfileId: run.model_profile_id || settings.model_profile_id || '',
    bilingual: settings.bilingual ?? true,
  };
}

const start = ref(startOf());
const startSource = ref(props.initialSource);
const form = reactive({ ...start.value });
const saveMode = ref('once');

const defaultValues = computed(() => ({
  sourceLanguage: props.defaults.sourceLanguage, targetLanguage: props.defaults.targetLanguage,
  profile: props.defaults.profile, domainProfile: props.defaults.domainProfile,
  classification: props.defaults.classification, modelProfileId: props.defaults.modelProfileId,
  bilingual: props.defaults.bilingual,
}));
const documentProfiles = computed(() => (form.domainProfile === 'ad' ? AD_PROFILES : GENERAL_PROFILES));
const isAd = computed(() => form.domainProfile === 'ad');

function valueLabel(name, value) {
  if (name === 'classification') return CLASSIFICATIONS[value] || value;
  if (name === 'domainProfile') return value === 'ad' ? 'AD 特应性皮炎' : '通用医药翻译';
  if (name === 'bilingual') return value ? '生成' : '不生成';
  if (name === 'modelProfileId') return modelLabelOf(value);
  return value;
}
function differs(name) {
  return defaultValues.value[name] !== undefined && form[name] !== defaultValues.value[name];
}
function diffNote(name) {
  return `与默认值不同（默认：${valueLabel(name, defaultValues.value[name])}）`;
}
function sourceLabel(name) {
  if (form[name] !== start.value[name]) return '本次修改';
  if (defaultValues.value[name] !== undefined && form[name] === defaultValues.value[name]) return '默认';
  return startSource.value;
}
function changed(name) {
  return form[name] !== start.value[name];
}

const lastDiffers = computed(() => Boolean(props.last) && Object.keys(defaultValues.value).some(
  (key) => props.last[key] !== undefined && props.last[key] !== form[key],
));
function useLast() {
  const last = props.last || {};
  const next = {};
  for (const key of Object.keys(defaultValues.value)) if (last[key] !== undefined) next[key] = last[key];
  Object.assign(form, next);
  start.value = { ...start.value, ...next };
  startSource.value = last.label && last.label !== '上次任务' ? `上次使用（${last.label}）` : '上次使用';
}

// ---- models: only those usable for the chosen data class ---------------------------------------
const profiles = ref([]);
const modelNotice = ref('');
const translators = computed(() => profiles.value.filter((p) => !p.role || p.role === 'translator'));
function modelLabelOf(id) {
  return profiles.value.find((p) => p.profile_id === id)?.label || id || '—';
}
const egressText = computed(() => {
  if (props.mode !== 'new') {
    const model = profiles.value.find((p) => p.profile_id === form.modelProfileId);
    return model?.provider === 'deepseek' ? '外发范围：全文发送到外部模型' : model ? '外发范围：无' : '';
  }
  const scope = result.value?.config?.egress_scope;
  if (!scope) return '';
  return { none: '外发范围：无', redacted_term_snippets: '外发范围：脱敏术语片段', full_document: '外发范围：全文发送到外部模型' }[scope] || '';
});

let profileSeq = 0;
async function loadProfiles() {
  const seq = ++profileSeq;
  try {
    const payload = await api.listModelProfiles(form.classification);
    if (seq !== profileSeq) return;
    profiles.value = payload.items || payload.profiles || [];
  } catch {
    if (seq === profileSeq) profiles.value = [];
    return;
  }
  const usable = translators.value.find((p) => p.profile_id === form.modelProfileId && p.configured);
  if (!usable) {
    const fallback = translators.value.find((p) => p.configured);
    if (fallback) {
      const previous = form.modelProfileId;
      form.modelProfileId = fallback.profile_id;
      if (previous) {
        modelNotice.value = `原选择的模型不可用于该资料等级，已改为「${fallback.label}」，请确认。`;
      } else {
        // Nothing was chosen before (no frozen model recorded): filling it in is not a change.
        start.value = { ...start.value, modelProfileId: fallback.profile_id };
      }
    }
  } else {
    modelNotice.value = '';
  }
}

watch(() => form.classification, () => { modelNotice.value = ''; loadProfiles(); });
watch(() => form.domainProfile, (domain) => {
  const allowed = domain === 'ad' ? AD_PROFILES : GENERAL_PROFILES;
  if (!allowed.includes(form.profile)) form.profile = '临床研究文档';
});

// ---- validation (new task only): what the server says will actually run ----------------------------
const result = ref(null);
const validating = ref(false);
const validationError = ref('');
const validatedKey = ref('');
let validationSeq = 0;
let debounce;

function buildBody() {
  return {
    preflight_id: props.preflight?.id,
    display_name: form.name.trim() || undefined,
    source_language: form.sourceLanguage,
    target_language: form.targetLanguage,
    profile: form.profile,
    domain_profile: form.domainProfile,
    bilingual: form.bilingual && pdf.value,
    document_classification: form.classification,
    model_profile_id: form.modelProfileId || undefined,
  };
}
const bodyKey = computed(() => JSON.stringify(buildBody()));

async function runValidation() {
  if (props.mode !== 'new') return;
  const seq = ++validationSeq;
  const key = bodyKey.value;
  validating.value = true;
  validationError.value = '';
  try {
    const response = await api.validateRun(buildBody());
    if (seq !== validationSeq) return;
    result.value = response;
    validatedKey.value = key;
  } catch (error) {
    if (seq !== validationSeq) return;
    result.value = null;
    validationError.value = error?.message || '请求失败';
  } finally {
    if (seq === validationSeq) validating.value = false;
  }
}

const errors = computed(() => result.value?.errors || []);
const warnings = computed(() => result.value?.warnings || []);
const isFresh = computed(() => !validating.value && result.value !== null && validatedKey.value === bodyKey.value);
const termModelLabel = computed(() => result.value?.config?.term_model?.label || '');

watch(bodyKey, () => {
  if (props.mode !== 'new') return;
  window.clearTimeout(debounce);
  debounce = window.setTimeout(runValidation, 150);
});

// One request key per confirmed configuration: a retry of the same decision reuses it, a changed
// configuration gets a new one so it can never be answered with an earlier task.
function newKey() {
  return globalThis.crypto?.randomUUID ? globalThis.crypto.randomUUID() : `k-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
const requestKey = ref(newKey());
watch(() => result.value?.config_digest, (digest, previous) => {
  if (digest && digest !== previous) requestKey.value = newKey();
});

// ---- submit -----------------------------------------------------------------------------------------
const submitting = ref(false);
const submitError = ref('');

const disabledReason = computed(() => {
  if (submitting.value) return '正在创建任务…';
  if (props.mode !== 'new') return '';
  if (validationError.value) return '参数校验失败，请重试';
  if (validating.value || result.value === null) return '正在校验参数…';
  if (errors.value.length) return `请先解决上方 ${errors.value.length} 个问题`;
  if (!isFresh.value) return '参数已修改，正在重新校验…';
  return '';
});
const confirmLabel = computed(() => (props.mode === 'resume' ? '按原配置续跑' : '确认并生成修订版'));
const title = computed(() => ({ new: '确认本次翻译参数', revision: '确认新版本的参数', resume: '确认续跑' })[props.mode]);
const subtitle = computed(() => ({
  new: '开始后这些参数会冻结为任务快照。请检查，必要时修改。',
  revision: '新版本使用原任务的冻结配置，只有下面列出的参数可以修改。',
  resume: '从断点继续，使用原任务的冻结配置。',
})[props.mode]);

const frozen = computed(() => ({
  direction: `${form.sourceLanguage} → ${form.targetLanguage}`,
  profile: form.profile || '—',
  domain: form.domainProfile === 'ad' ? 'AD 特应性皮炎' : '通用医药翻译',
}));

function overrides() {
  const out = {};
  if (changed('classification')) out.document_classification = form.classification;
  if (changed('modelProfileId')) out.model_profile_id = form.modelProfileId;
  if (changed('bilingual')) out.bilingual = form.bilingual;
  if (changed('name')) out.display_name = form.name.trim();
  return out;
}

async function submit() {
  if (disabledReason.value || submitting.value || !props.onSubmit) return;
  submitting.value = true;
  submitError.value = '';
  try {
    if (props.mode === 'new') {
      await props.onSubmit({
        payload: { ...buildBody(), config_digest: result.value?.config_digest || undefined },
        key: requestKey.value,
        saveAsDefault: saveMode.value === 'default',
        config: result.value?.config || null,
        form: { ...form },
      });
    } else if (props.mode === 'revision') {
      await props.onSubmit({ overrides: overrides() });
    } else {
      await props.onSubmit({});
    }
  } catch (error) {
    submitError.value = error?.message || '提交失败，请重试';
    if (error?.payload?.detail?.code === 'CONFIG_STALE' || error?.status === 409) runValidation();
  } finally {
    submitting.value = false;
  }
}

// ---- keyboard and focus ---------------------------------------------------------------------------------
function onKeydown(event) {
  if (event.key === 'Escape') {
    event.stopPropagation();
    emit('close');
    return;
  }
  if (event.key !== 'Tab') return;
  const focusable = [...rootEl.value.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')]
    .filter((el) => !el.disabled && el.offsetParent !== null || el === document.activeElement);
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && (document.activeElement === first || document.activeElement === rootEl.value)) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

onMounted(async () => {
  opener = document.activeElement;
  await nextTick();
  rootEl.value?.focus();
  await loadProfiles();
  if (props.mode === 'new') runValidation();
});

onBeforeUnmount(() => {
  window.clearTimeout(debounce);
  validationSeq += 1; // late answers are ignored
  if (opener && typeof opener.focus === 'function') opener.focus();
});

// A different pre-check (after "copy the pre-check") is a different request.
watch(() => props.preflight?.id, (id, previous) => {
  if (id && id !== previous && props.mode === 'new') {
    result.value = null;
    runValidation();
  }
});
</script>

<style scoped>
.qy-drawer-backdrop { position: fixed; inset: 0; background: rgba(15, 23, 42, .45); z-index: 60; display: flex; justify-content: flex-end; }
.qy-confirm-drawer { width: min(520px, 100%); height: 100%; overflow-y: auto; background: #fff; padding: 1rem 1.25rem 1.5rem; display: grid; gap: .9rem; align-content: start; box-shadow: -8px 0 24px rgba(15, 23, 42, .2); outline: none; }
.qy-confirm-head { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; }
.qy-confirm-head h2 { margin: 0; font-size: 1.15rem; }
.qy-confirm-head p { margin: .25rem 0 0; }
.qy-confirm-file { display: flex; flex-wrap: wrap; gap: .25rem .75rem; padding: .5rem .7rem; background: #f6f8fa; border: 1px solid var(--qy-border, #d6dce3); }
.qy-confirm-form { display: grid; gap: .8rem; }
.qy-confirm-row { display: grid; gap: .2rem; }
.qy-field-source { color: #5b6573; }
.qy-field-diff { color: #8a4b00; font-weight: 600; }
.qy-confirm-notice { margin: 0; padding: .4rem .6rem; background: #fffbeb; border-left: 4px solid #b45309; }
.qy-confirm-qa { padding: .5rem .7rem; border: 1px solid var(--qy-border, #d6dce3); }
.qy-confirm-qa h3, .qy-confirm-frozen h3 { margin: 0 0 .25rem; font-size: .95rem; }
.qy-confirm-qa p { margin: 0; }
.qy-confirm-frozen { padding: .6rem .8rem; background: #f6f8fa; border: 1px solid var(--qy-border, #d6dce3); }
.qy-confirm-frozen dl { display: grid; grid-template-columns: max-content 1fr; gap: .2rem .8rem; margin: 0 0 .4rem; }
.qy-confirm-frozen dd { margin: 0; }
.qy-confirm-errors, .qy-confirm-warnings { margin: 0; padding-left: 1.1rem; }
.qy-confirm-errors li { color: #8b1e1e; }
.qy-confirm-warnings li { color: #7a5200; }
.qy-confirm-error { margin: 0; color: #8b1e1e; }
.qy-confirm-ok { margin: 0; color: #1c6b3a; }
.qy-confirm-save { border: 1px solid var(--qy-border, #d6dce3); padding: .5rem .7rem; display: grid; gap: .25rem; }
.qy-confirm-actions { display: flex; flex-wrap: wrap; gap: .6rem; align-items: center; position: sticky; bottom: 0; background: #fff; padding-top: .6rem; border-top: 1px solid var(--qy-border, #d6dce3); }
.qy-confirm-last { margin: 0; }
@media (max-width: 700px) { .qy-confirm-drawer { width: 100%; } }
</style>
