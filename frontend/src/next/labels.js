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

// PLAN-079: with term_gate_mode "enforce" undecided vocabulary candidates are glossary work, not a delivery blocker.
export function termsBlockDelivery(run) {
  return run?.formal_gate?.term_gate_mode !== 'enforce';
}

// Count shown on the "处理质量问题（N）" entry: what still stands between the run and delivery.
export function todoCount(run) {
  const pending = run?.pending_counts;
  if (pending) {
    return (pending.qa_blockers || 0) + (pending.qa_unavailable || 0)
      + (termsBlockDelivery(run) ? (pending.unresolved_terms || 0) : 0);
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

// ---- PLAN-078b: QA findings, dispositions and delivery checklist -------------------------

export const RULE_CLASS_LABELS = {
  C1: '关键事实',
  C2: '版式与元数据',
  C3: '检查未完成',
  C4: '术语',
  W: '警告',
  I: '提示',
};

export const ITEM_STATUS_LABELS = {
  open: '待处理',
  false_positive_reported: '已反馈误报，待确认',
  false_positive_confirmed: '误报已确认',
  waived: '已授权例外',
  acknowledged: '已确认已阅',
};

export const ACTION_LABELS = {
  report_false_positive: '反馈误报',
  confirm_false_positive: '确认误报',
  reject_false_positive: '驳回（问题确实存在）',
  grant_waiver: '授权例外',
  revoke_waiver: '撤销例外',
  acknowledge: '确认已阅',
};

export const ACTION_HELP = {
  report_false_positive: '认为这是检查规则的误判时使用。反馈本身不会放行，需由有确认权限的人（术语管理员、管理员、所有者）确认；你有确认权限时可以自己确认。',
  confirm_false_positive: '核对原文后确认这是规则误判，阻断解除。你自己的反馈也可以自己确认，审计里会标注为自我确认。',
  reject_false_positive: '核对后认为问题真实存在，驳回别人的误报反馈；阻断保留，问题仍需修复。想说“这是误报、可以放行”不要点这个。',
  grant_waiver: '用于版式、元数据、乱码和术语类问题：说明为何可以带着它交付（例如页面上读不出乱码）。一个复核人即可，理由会记入审计。',
  revoke_waiver: '撤销之前授权的例外，问题重新计入阻断。',
  acknowledge: '确认已阅读这条警告；警告本身不阻断交付。',
};

export const GATE_REASON_LABELS = {
  qa_blockers: '仍有未处理的阻断问题',
  qa_unavailable: '质量检查未完成',
  qa_checking: '质量检查进行中',
  qa_degraded: '语义检查未完成',
  unresolved_terms: '有待审核的术语',
  superseded_artifact: '已有更新的版本',
  term_extraction_degraded: '术语抽取未完成',
};

export function ruleClassLabel(ruleClass) {
  return RULE_CLASS_LABELS[ruleClass] || '';
}

export function itemStatusLabel(status) {
  return ITEM_STATUS_LABELS[status || 'open'] || '待处理';
}

export function actionLabel(action) {
  return ACTION_LABELS[action] || action;
}

export function anchorText(anchor) {
  if (!anchor) return '';
  const side = anchor.side === 'translated' ? '译文' : '原文';
  if (anchor.page) return `${side}第 ${anchor.page} 页`;
  if (anchor.paragraph) return `${side}第 ${anchor.paragraph} 段`;
  return side;
}

// A finding still stands between the run and delivery unless a valid disposition closed it.
// 提示（info）是检查记录（如「确定性 QA 取证摘要」），不影响交付：不计入待处理，只在「全部」里可查。
export const isInfoItem = (item) => item.severity === 'info';

export function isOpenItem(item) {
  if (item.resolved || isInfoItem(item)) return false;
  return !['false_positive_confirmed', 'waived', 'acknowledged'].includes(item.status || 'open');
}

const SEVERITY_ORDER = { blocker: 0, unavailable: 1, warning: 2, info: 3 };

export function sortItems(items) {
  return [...items].sort((a, b) => (
    (Number(isOpenItem(b)) - Number(isOpenItem(a)))
    || ((SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9))
  ));
}
