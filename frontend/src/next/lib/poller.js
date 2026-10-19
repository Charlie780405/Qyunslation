// PLAN-078f f3: poll only while something is changing and the page is in front of the person.
//
// - nothing to watch (`shouldPoll()` false)  -> no timer at all
// - tab hidden                               -> no timer; coming back refreshes once, immediately
// - something running, nothing new           -> back off 2s -> 5s -> 10s, and snap back to 2s on a change
//
// `run()` does the fetch and returns a signature string of what the person can see; the poller compares it
// with the last one to decide whether to back off.

export const POLL_DELAYS = Object.freeze([2000, 5000, 10000]);

export function createPoller({ run, shouldPoll, delays = POLL_DELAYS, doc = typeof document !== 'undefined' ? document : null, win = typeof window !== 'undefined' ? window : null }) {
  let timer = null;
  let step = 0;
  let last = null;
  let started = false;
  let inFlight = false;

  const hidden = () => Boolean(doc && doc.visibilityState === 'hidden');

  function clear() {
    if (timer !== null) {
      globalThis.clearTimeout(timer);
      timer = null;
    }
  }

  function schedule() {
    clear();
    if (!started || hidden() || !shouldPoll()) return;
    timer = globalThis.setTimeout(tick, delays[Math.min(step, delays.length - 1)]);
  }

  async function tick() {
    timer = null;
    if (!started || inFlight) return;
    inFlight = true;
    try {
      const signature = await run();
      if (signature !== undefined && signature === last) step = Math.min(step + 1, delays.length - 1);
      else step = 0;
      last = signature;
    } catch {
      // The caller shows its own error; keep trying, slowly.
      step = Math.min(step + 1, delays.length - 1);
    } finally {
      inFlight = false;
      schedule();
    }
  }

  // Refresh now (a person did something, or the tab came back) and carry on from there.
  function kick() {
    clear();
    step = 0;
    return tick();
  }

  function onVisibility() {
    if (!hidden()) kick();
    else clear();
  }

  function onOnline() {
    kick();
  }

  function start() {
    if (started) return;
    started = true;
    doc?.addEventListener?.('visibilitychange', onVisibility);
    win?.addEventListener?.('online', onOnline);
  }

  function stop() {
    started = false;
    clear();
    doc?.removeEventListener?.('visibilitychange', onVisibility);
    win?.removeEventListener?.('online', onOnline);
  }

  // Call after any fetch that may have started or finished work, so the timer follows the new state.
  function reschedule() {
    schedule();
  }

  return { start, stop, kick, reschedule };
}
