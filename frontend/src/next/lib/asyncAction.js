import { computed, ref } from 'vue';

// PLAN-078f f4: every button that talks to the server goes through one of these, so each one has the same
// three states a person can see: working (pending), done (notice), failed (error). A second click while one
// is running is ignored instead of sending the request twice.
//
//   const action = useAsyncAction();
//   action.run('requalify', () => api.requalifyRun(id), { success: '已重新检查。', failure: '重新检查失败' });
//   action.pending.value  // name of the running action, or ''
//   action.error.value    // message to show next to the buttons
//   action.notice.value   // confirmation after success

export function describeFailure(error, fallback = '操作失败') {
  if (error?.network) return error.message;
  if (error?.status === 403) return `${fallback}：当前账号没有这个操作的权限。`;
  if (error?.status === 404) return `${fallback}：任务已不存在，请返回列表确认。`;
  if (error?.status >= 500) return `${fallback}：服务暂时出错，请稍后重试。`;
  return error?.message ? `${fallback}：${error.message}` : fallback;
}

export function useAsyncAction() {
  const pending = ref('');
  const error = ref('');
  const notice = ref('');
  const busy = computed(() => pending.value !== '');

  function clear() {
    error.value = '';
    notice.value = '';
  }

  // Resolves to true when the task succeeded, false when it failed or another action was already running.
  async function run(name, task, { success = '', failure = '操作失败', after = null } = {}) {
    if (pending.value) return false;
    pending.value = name;
    clear();
    try {
      await task();
      notice.value = success;
      return true;
    } catch (cause) {
      error.value = describeFailure(cause, failure);
      return false;
    } finally {
      pending.value = '';
      if (after) await after();
    }
  }

  return { pending, busy, error, notice, run, clear };
}
