<template>
  <ol class="qy-flow-list" aria-label="任务阶段">
    <li
      v-for="(item, index) in displayStages"
      :key="item.stage + '-' + index"
      :class="item.className"
      :data-stage="item.stage"
      :data-state="item.state"
    >
      <span>{{ String(index + 1).padStart(2, '0') }}</span>
      <div>
        <strong>{{ item.label }}</strong>
        <small>{{ item.message || item.state }}</small>
      </div>
    </li>
  </ol>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  events: { type: Array, default: () => [] },
  currentStage: { type: String, default: '' },
  qualityState: { type: String, default: 'draft' },
});

const MESSAGE_LABELS = {
  'format=pdf': 'PDF 格式',
  'text pdf': '文本型 PDF，无需 OCR',
  disabled: '本模板未启用',
  pending: '等待中',
  'launched:pdf_cli': '已启动 PDF 引擎',
  'launched:office_sidecar': '已启动 Office 引擎',
  'launched:image_sidecar': '已启动图片引擎',
};

function displayMessage(event, state) {
  const raw = event?.message || state;
  if (!raw) return state;
  return MESSAGE_LABELS[raw] || raw;
}

const STAGE_LABELS = {
  validation: '文件预检',
  structure: '结构解析',
  ocr: 'OCR',
  text: '正文翻译',
  table_figure: '表格与图片',
  layout: '版式',
  qa: 'QA 与术语',
  review: '人工复核',
  export: '受控导出',
};

const ORDER = [
  'validation',
  'structure',
  'ocr',
  'text',
  'table_figure',
  'layout',
  'qa',
  'review',
  'export',
];

const displayStages = computed(() => {
  const byStage = new Map();
  for (const event of props.events || []) {
    byStage.set(event.stage, event);
  }
  return ORDER.map((stage) => {
    const event = byStage.get(stage);
    let state = event?.state || 'pending';
    // Only promote current stage when events exist or stage matches — never invent completed.
    if (!event && props.currentStage === stage) state = 'running';
    if (stage === 'export' && props.qualityState === 'approved' && event?.state === 'completed') {
      state = 'completed';
    } else if (stage === 'export' && props.qualityState === 'approved' && !event) {
      state = 'running';
    }
    if (stage === 'review' && props.qualityState === 'review_ready' && (!event || event.state === 'pending')) {
      state = 'running';
    }
    if (stage === 'qa' && props.qualityState === 'qa_blocked') state = 'blocked';
    const className = {
      'is-complete': state === 'completed',
      'is-current': state === 'running',
      'is-skipped': state === 'skipped',
      'is-blocked': state === 'blocked' || state === 'failed',
    };
    return {
      stage,
      state,
      label: STAGE_LABELS[stage] || stage,
      message: displayMessage(event, state),
      className,
    };
  });
});
</script>
