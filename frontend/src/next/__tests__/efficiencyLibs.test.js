import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createPoller } from '../lib/poller.js';
import { createEventTail } from '../lib/eventTail.js';
import { describeFailure, useAsyncAction } from '../lib/asyncAction.js';
import { sha256Hex } from '../lib/fileHash.js';
import { answerConfirm, confirmDialog, confirmState } from '../lib/confirm.js';

// PLAN-078f f3/f4/f5/f7: the small pieces the pages are built from.

function fakeDoc(state = 'visible') {
  const listeners = {};
  return {
    visibilityState: state,
    addEventListener: (name, fn) => { listeners[name] = fn; },
    removeEventListener: (name) => { delete listeners[name]; },
    set(next) { this.visibilityState = next; listeners.visibilitychange?.(); },
    listeners,
  };
}

describe('poller (f3)', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('backs off 2s -> 5s -> 10s while nothing changes and snaps back on a change', async () => {
    const run = vi.fn(async () => 'same');
    const poller = createPoller({ run, shouldPoll: () => true, doc: fakeDoc(), win: null });
    poller.start();
    poller.reschedule();
    await vi.advanceTimersByTimeAsync(1999);
    expect(run).toHaveBeenCalledTimes(0);
    await vi.advanceTimersByTimeAsync(1); // t=2s: first poll (a change from "nothing seen yet")
    expect(run).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(2000); // still 2s after a change
    expect(run).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(4999); // same result -> now 5s
    expect(run).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(1);
    expect(run).toHaveBeenCalledTimes(3);
    await vi.advanceTimersByTimeAsync(9999); // same again -> 10s
    expect(run).toHaveBeenCalledTimes(3);
    await vi.advanceTimersByTimeAsync(1);
    expect(run).toHaveBeenCalledTimes(4);
    run.mockResolvedValue('changed');
    await vi.advanceTimersByTimeAsync(10000);
    expect(run).toHaveBeenCalledTimes(5);
    await vi.advanceTimersByTimeAsync(2000); // back to 2s
    expect(run).toHaveBeenCalledTimes(6);
    poller.stop();
  });

  it('sets no timer at all when there is nothing to watch', async () => {
    const run = vi.fn(async () => 'x');
    const poller = createPoller({ run, shouldPoll: () => false, doc: fakeDoc(), win: null });
    poller.start();
    poller.reschedule();
    await vi.advanceTimersByTimeAsync(120000);
    expect(run).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
    poller.stop();
  });

  it('stops while the tab is hidden and refreshes once, at once, when it comes back', async () => {
    const doc = fakeDoc();
    const run = vi.fn(async () => 'x');
    const poller = createPoller({ run, shouldPoll: () => true, doc, win: null });
    poller.start();
    poller.reschedule();
    doc.set('hidden');
    expect(vi.getTimerCount()).toBe(0);
    await vi.advanceTimersByTimeAsync(60000);
    expect(run).not.toHaveBeenCalled();
    doc.set('visible');
    await vi.advanceTimersByTimeAsync(0);
    expect(run).toHaveBeenCalledTimes(1);
    poller.stop();
    expect(doc.listeners.visibilitychange).toBeUndefined();
  });

  it('keeps going, slowly, when a poll fails', async () => {
    const run = vi.fn(async () => { throw new Error('offline'); });
    const poller = createPoller({ run, shouldPoll: () => true, doc: fakeDoc(), win: null });
    poller.start();
    poller.reschedule();
    await vi.advanceTimersByTimeAsync(2000);
    expect(run).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(5000);
    expect(run).toHaveBeenCalledTimes(2);
    poller.stop();
  });

  it('an idle tab makes far fewer requests than a fixed 2-second poll (10 minutes)', async () => {
    const run = vi.fn(async () => 'x');
    let working = true;
    const poller = createPoller({ run, shouldPoll: () => working, doc: fakeDoc(), win: null });
    poller.start();
    poller.reschedule();
    await vi.advanceTimersByTimeAsync(60000); // a minute of "running", nothing new
    working = false; // the task finished
    await vi.advanceTimersByTimeAsync(9 * 60000);
    const requests = run.mock.calls.length;
    expect(requests).toBeLessThan(300 * 0.1); // 10 min at 2s would be 300 requests
    poller.stop();
  });
});

describe('event tail (f3)', () => {
  const event = (sequence, extra = {}) => ({ sequence, stage: 's', state: 'completed', ...extra });

  it('asks only for events after the last one it has', async () => {
    const fetchEvents = vi.fn()
      .mockResolvedValueOnce({ items: [event(1), event(2)], generation: 1 })
      .mockResolvedValueOnce({ items: [event(3)], generation: 1 })
      .mockResolvedValueOnce({ items: [], generation: 1 });
    const tail = createEventTail(fetchEvents);
    expect((await tail.pull('r1')).map((e) => e.sequence)).toEqual([1, 2]);
    expect((await tail.pull('r1')).map((e) => e.sequence)).toEqual([1, 2, 3]);
    await tail.pull('r1');
    expect(fetchEvents.mock.calls.map((call) => call[1].after_sequence)).toEqual([0, 2, 3]);
  });

  it('starts over for another task and when the generation changes', async () => {
    const fetchEvents = vi.fn(async (id, { after_sequence: after }) => {
      if (id === 'r2') return { items: [event(1, { stage: 'other' })], generation: 1 };
      if (after > 0) return { items: [], generation: 2 }; // a new generation numbers from 1 again
      return { items: [event(1, { stage: 'new' })], generation: 2 };
    });
    const tail = createEventTail(fetchEvents);
    fetchEvents.mockResolvedValueOnce({ items: [event(1), event(2)], generation: 1 });
    await tail.pull('r1');
    const regenerated = await tail.pull('r1');
    expect(regenerated).toHaveLength(1);
    expect(regenerated[0].stage).toBe('new');
    const other = await tail.pull('r2');
    expect(other.map((e) => e.stage)).toEqual(['other']);
  });

  it('never repeats an event it already has', async () => {
    const fetchEvents = vi.fn()
      .mockResolvedValueOnce({ items: [event(1), event(2)], generation: 1 })
      .mockResolvedValueOnce({ items: [event(2), event(3)], generation: 1 });
    const tail = createEventTail(fetchEvents);
    await tail.pull('r1');
    expect((await tail.pull('r1')).map((e) => e.sequence)).toEqual([1, 2, 3]);
  });
});

describe('useAsyncAction (f4)', () => {
  it('shows pending, then the success notice', async () => {
    const action = useAsyncAction();
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    const done = action.run('requalify', () => gate, { success: '已重新检查。' });
    expect(action.pending.value).toBe('requalify');
    release();
    expect(await done).toBe(true);
    expect(action.pending.value).toBe('');
    expect(action.notice.value).toBe('已重新检查。');
    expect(action.error.value).toBe('');
  });

  it('turns a failure into a visible message and can be run again', async () => {
    const action = useAsyncAction();
    expect(await action.run('x', async () => { throw new Error('术语服务暂不可用'); }, { failure: '重新检查失败' })).toBe(false);
    expect(action.error.value).toBe('重新检查失败：术语服务暂不可用');
    expect(await action.run('x', async () => {}, { success: 'ok' })).toBe(true);
    expect(action.error.value).toBe('');
  });

  it('ignores a second click while one is running', async () => {
    const action = useAsyncAction();
    const task = vi.fn(() => new Promise(() => {}));
    action.run('a', task);
    expect(await action.run('b', task)).toBe(false);
    expect(task).toHaveBeenCalledTimes(1);
  });

  it('explains permission, missing and server errors, and a lost connection, in plain words', () => {
    expect(describeFailure({ status: 403 }, '删除失败')).toContain('没有');
    expect(describeFailure({ status: 404 }, '删除失败')).toContain('不存在');
    expect(describeFailure({ status: 502, message: 'bad gateway' }, '删除失败')).toContain('稍后重试');
    expect(describeFailure({ network: true, message: '连接中断，请检查网络；页面会自动重试。' }, '删除失败')).toContain('连接中断');
  });
});

describe('sha256Hex (f7)', () => {
  it('matches the known digest of "abc"', async () => {
    const file = new File(['abc'], 'a.txt');
    if (typeof file.arrayBuffer !== 'function') {
      file.arrayBuffer = async () => new TextEncoder().encode('abc').buffer;
    }
    expect(await sha256Hex(file)).toBe('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
  });

  it('skips files above the limit, and returns null instead of throwing', async () => {
    expect(await sha256Hex({ size: 300 * 1024 * 1024, arrayBuffer: async () => { throw new Error('should not read'); } })).toBeNull();
    expect(await sha256Hex({ size: 4, arrayBuffer: async () => { throw new Error('read failed'); } })).toBeNull();
    expect(await sha256Hex(null)).toBeNull();
  });
});

describe('confirmDialog (f5)', () => {
  it('resolves true on confirm and false on cancel, and only one question is open at a time', async () => {
    const first = confirmDialog({ title: '一', danger: true });
    expect(confirmState.open).toBe(true);
    expect(confirmState.danger).toBe(true);
    const second = confirmDialog({ title: '二' });
    expect(await first).toBe(false); // replaced
    expect(confirmState.title).toBe('二');
    answerConfirm(true);
    expect(await second).toBe(true);
    expect(confirmState.open).toBe(false);
  });
});
