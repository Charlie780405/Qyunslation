import { computed, ref } from 'vue';
import { defineStore } from 'pinia';
import { api } from '../api.js';

export const useSessionStore = defineStore('next-session', () => {
  const user = ref(null);
  const state = ref('unknown');
  const error = ref('');

  const isAuthenticated = computed(() => state.value === 'authenticated');
  const isPreview = computed(() => !isAuthenticated.value && import.meta.env.DEV);
  const hasCapability = (name) => Boolean(user.value?.capabilities?.[name]);

  async function load() {
    if (state.value !== 'unknown') return user.value;
    try {
      user.value = await api.me();
      state.value = 'authenticated';
    } catch (cause) {
      state.value = cause?.status === 401 ? 'anonymous' : 'unavailable';
      error.value = cause?.message || '无法读取当前会话';
    }
    return user.value;
  }

  async function beginLogin() {
    const returnTo = `${window.location.pathname}${window.location.search}`;
    const response = await fetch(`/auth/login?format=json&return_to=${encodeURIComponent(returnTo)}`, {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(payload.message || '公司身份服务暂不可用，请稍后重试。');
      error.status = response.status;
      throw error;
    }
    if (payload.location) window.location.assign(payload.location);
  }

  async function logout() {
    await api.logout();
    user.value = null;
    state.value = 'anonymous';
  }

  return { user, state, error, isAuthenticated, isPreview, hasCapability, load, beginLogin, logout };
});
