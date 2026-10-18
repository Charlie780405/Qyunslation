// User-facing wording for task state. The server derives `lifecycle`, `allowed_actions`
// and `next_action` (PLAN-078a); the fallbacks below only keep older payloads readable.

const EXECUTING = new Set(['queued', 'scanning', 'translating', 'rendering']);
const GATE_BY_QUALITY = {
  qa_blocked: 'qa_action',
  qa_unavailable: 'qa_unavailable',
  review_ready: 'review',
  qa_degraded: 'review',
  changes_requested: 'changes_requested',
};

export const LIFECYCLE_LABELS = {
  executing: '翻译中',
  qa_checking: '正在质量检查',
  qa_action: '待处理质量问题',
  qa_unavailable: '质量检查未完成',
  review: '待人工复核',
  changes_requested: '已退回修改',
  failed: '失败',
  interrupted: '已中断',
  cancelled: '已取消',
  completed: '已完成',
};

export const STATUS_LABELS = {
  queued: '排队中',
  scanning: '结构分析',
  translating: '翻译中',
  rendering: '渲染中',
  gated: '等待处理',
  review_ready: '待复核',
  succeeded: '已完成',
  failed: '失败',
  cancelled: '已取消',
  blocked: '已阻断',
  degraded: '降级完成',
  interrupted: '已中断',
};

export const QUALITY_LABELS = {
  draft: '检查中',
  qa_blocked: '有阻断问题',
  qa_unavailable: '检查未完成',
  qa_degraded: '语义检查降级',
  review_ready: '检查通过，待复核',
  changes_requested: '已退回修改',
  approved: '已批准',
  legacy_unverified: '旧版未验证',
};

export const STAGE_LABELS = {
  validation: '预检',
  structure: '结构',
  text: '正文',
  table_figure: '表格与图注',
  layout: '版式',
  rendering: '版式',
  qa: '质量检查',
  review: '复核',
  export: '导出',
};

export const SEVERITY_LABELS = {
  blocker: '阻断',
  unavailable: '检查未完成',
  warning: '警告',
  info: '提示',
};

export const NEXT_ACTION_LABELS = {
  fix_quality_issues: '处理质量问题',
  retry_qa: '重新检查',
  review: '去复核',
  resolve_gate_items: '处理待办项',
  create_revision: '生成修订版',
  resume: '从断点续跑',
  retry: '重新翻译',
  download: '下载',
};

export function lifecycleOf(run) {
  if (!run) return 'failed';
  if (run.lifecycle) return run.lifecycle;
  if (EXECUTING.has(run.status)) return 'executing';
  if (run.status === 'gated') {
    return run.quality_state && run.quality_state !== 'draft'
      ? (GATE_BY_QUALITY[run.quality_state] || 'review')
      : 'qa_checking';
  }
  // Legacy payloads: a finished executor still reported as translating/review_ready.
  if (GATE_BY_QUALITY[run.quality_state] && run.status !== 'succeeded') return GATE_BY_QUALITY[run.quality_state];
  if (run.status === 'succeeded') return 'completed';
  if (run.status === 'interrupted' || run.status === 'cancelled') return run.status;
  return 'failed';
}

export function isExecuting(run) {
  return lifecycleOf(run) === 'executing' || lifecycleOf(run) === 'qa_checking';
}

export function lifecycleLabel(run) {
  return LIFECYCLE_LABELS[lifecycleOf(run)] || STATUS_LABELS[run?.status] || '待处理';
}

export function statusLabel(status) {
  return STATUS_LABELS[status] || '待处理';
}

export function qualityLabel(state) {
  return QUALITY_LABELS[state || 'draft'] || '待处理';
}

export function stageLabel(stage) {
  return STAGE_LABELS[stage] || '处理中';
}

export function severityLabel(severity) {
  return SEVERITY_LABELS[severity] || severity || '';
}

// Count shown on the "处理质量问题（N）" entry: what still stands between the run and delivery.
export function todoCount(run) {
  const pending = run?.pending_counts;
  if (pending) {
    return (pending.qa_blockers || 0) + (pending.qa_unavailable || 0)
      + (pending.unresolved_terms || 0) + (pending.unconfirmed_affiliations || 0);
  }
  return run?.qa_summary?.blocker || 0;
}

// Prefer the server's answer; the legacy fallback mirrors the old client-side rules.
export function can(run, action) {
  if (Array.isArray(run?.allowed_actions)) return run.allowed_actions.includes(action);
  const lifecycle = lifecycleOf(run);
  const ended = !['executing', 'qa_checking'].includes(lifecycle);
  switch (action) {
    case 'cancel': return lifecycle === 'executing';
    case 'resume': return run?.status === 'interrupted';
    case 'retry': return ended;
    case 'archive': return ended && !run?.archived;
    case 'restore': return Boolean(run?.archived);
    case 'delete': return ended;
    case 'rename': return true;
    case 'requalify': return ['qa_action', 'qa_unavailable', 'review'].includes(lifecycle);
    default: return false;
  }
}
