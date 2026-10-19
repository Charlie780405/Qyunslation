import { ref } from 'vue';

// PLAN-078f f4: one place that knows whether the server can be reached. `apiRequest` flips it on a network
// failure and back on the next answer; the browser's own online/offline events do the same. The shell shows
// a banner while it is `offline`, and the pollers keep trying, so the page recovers without a reload.

export const connection = {
  offline: ref(false),
  since: ref(0),
};

export function markOffline() {
  if (!connection.offline.value) connection.since.value = Date.now();
  connection.offline.value = true;
}

export function markOnline() {
  connection.offline.value = false;
}

if (typeof window !== 'undefined' && window.addEventListener) {
  window.addEventListener('offline', markOffline);
  window.addEventListener('online', markOnline);
}
