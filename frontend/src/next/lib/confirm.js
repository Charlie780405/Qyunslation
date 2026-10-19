import { reactive } from 'vue';

// PLAN-078f f5: `await confirmDialog({...})` instead of window.confirm. One <ConfirmDialog> in the app shell
// renders whatever is asked; the answer is true (confirmed) or false (cancelled, Esc, or clicked outside).
// Only one question is open at a time; asking again while one is open cancels the earlier one.

export const confirmState = reactive({ open: false, title: '', body: '', confirmLabel: '确定', cancelLabel: '取消', danger: false });

let resolver = null;

export function confirmDialog({ title, body = '', confirmLabel = '确定', cancelLabel = '取消', danger = false } = {}) {
  if (resolver) resolver(false);
  Object.assign(confirmState, { open: true, title, body, confirmLabel, cancelLabel, danger });
  return new Promise((resolve) => { resolver = resolve; });
}

export function answerConfirm(value) {
  confirmState.open = false;
  const done = resolver;
  resolver = null;
  if (done) done(Boolean(value));
}
