import { describe, expect, it } from 'vitest';
import router from '../router.js';
import RunDetailPage from '../pages/RunDetailPage.vue';
import WorkbenchPage from '../pages/WorkbenchPage.vue';

describe('next router', () => {
  it('resolves /workbench/:runId to RunDetailPage with the run id param', () => {
    const resolved = router.resolve('/workbench/abc-123?page=2');
    expect(resolved.name).toBe('workbench-run');
    expect(resolved.params.runId).toBe('abc-123');
    expect(resolved.query.page).toBe('2');
    expect(resolved.matched.at(-1).components.default).toBe(RunDetailPage);
  });

  it('resolves /workbench to WorkbenchPage', () => {
    const resolved = router.resolve('/workbench');
    expect(resolved.name).toBe('workbench');
    expect(resolved.matched.at(-1).components.default).toBe(WorkbenchPage);
  });
});
