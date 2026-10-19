<template>
  <div v-if="confirmState.open" class="qy-drawer-backdrop" data-confirm-backdrop @click.self="answer(false)">
    <div
      ref="dialogEl"
      class="qy-batch-confirm"
      data-confirm-dialog
      role="alertdialog"
      aria-modal="true"
      :aria-labelledby="titleId"
      :aria-describedby="confirmState.body ? bodyId : undefined"
      tabindex="-1"
      @keydown="onKeydown"
    >
      <h2 :id="titleId">{{ confirmState.title }}</h2>
      <p v-if="confirmState.body" :id="bodyId">{{ confirmState.body }}</p>
      <div class="qy-batch-confirm-actions">
        <button type="button" class="qy-secondary-button" data-confirm-cancel @click="answer(false)">{{ confirmState.cancelLabel }}</button>
        <button
          type="button"
          class="qy-primary-button"
          :class="{ 'qy-danger-button': confirmState.danger }"
          data-confirm-ok
          @click="answer(true)"
        >{{ confirmState.confirmLabel }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { answerConfirm, confirmState } from '../lib/confirm.js';

const uid = Math.random().toString(36).slice(2, 8);
const titleId = `confirm-title-${uid}`;
const bodyId = `confirm-body-${uid}`;
const dialogEl = ref(null);
let opener = null;

// Focus goes into the dialog when it opens (on the safe choice for a destructive question) and back to
// whatever had it when it closes.
watch(() => confirmState.open, async (open) => {
  if (open) {
    opener = document.activeElement;
    await nextTick();
    const safe = confirmState.danger ? dialogEl.value?.querySelector('[data-confirm-cancel]') : dialogEl.value?.querySelector('[data-confirm-ok]');
    (safe || dialogEl.value)?.focus?.();
  } else {
    const target = opener;
    opener = null;
    await nextTick();
    if (target?.isConnected) target.focus?.();
  }
});

function answer(value) {
  answerConfirm(value);
}

function onKeydown(event) {
  if (event.key === 'Escape') {
    event.stopPropagation();
    answer(false);
    return;
  }
  if (event.key !== 'Tab' || !dialogEl.value) return;
  const focusable = [...dialogEl.value.querySelectorAll('button')].filter((el) => !el.disabled);
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && (document.activeElement === first || document.activeElement === dialogEl.value)) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

onBeforeUnmount(() => { if (confirmState.open) answerConfirm(false); });
</script>
