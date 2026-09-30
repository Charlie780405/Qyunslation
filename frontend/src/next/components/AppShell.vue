<template>
  <div class="qy-app-shell">
    <header class="qy-topbar">
      <RouterLink class="qy-brand" to="/workbench" aria-label="返回翻译工作台">
        <img src="/static/quanxin-logo.svg" alt="" class="qy-brand-mark" />
        <span><strong>Qyunslation</strong><small>临床翻译工作台</small></span>
      </RouterLink>
      <div class="qy-topbar-actions">
        <span v-if="session.isPreview" class="qy-preview-pill">
          <InformationCircleIcon aria-hidden="true" /> 本地预览
        </span>
        <span v-else-if="session.user" class="qy-user-chip">
          <span class="qy-avatar" aria-hidden="true">{{ initials }}</span>
          <span>{{ session.user.display_name || session.user.name || '当前用户' }}</span>
        </span>
        <button v-if="session.isAuthenticated" class="qy-icon-button" type="button" aria-label="退出登录" @click="signOut">
          <ArrowRightOnRectangleIcon aria-hidden="true" />
        </button>
      </div>
    </header>

    <div class="qy-body">
      <aside class="qy-sidebar" aria-label="主导航">
        <nav class="qy-nav-list">
          <RouterLink v-for="item in navItems" :key="item.to" :to="item.to" class="qy-nav-item">
            <component :is="item.icon" aria-hidden="true" /><span>{{ item.label }}</span>
          </RouterLink>
        </nav>
        <div class="qy-sidebar-footer"><span class="qy-status-dot" aria-hidden="true"></span><span>工作区服务正常</span></div>
      </aside>
      <main class="qy-main-content"><slot /></main>
    </div>

    <nav class="qy-mobile-nav" aria-label="移动端导航">
      <RouterLink v-for="item in navItems" :key="item.to" :to="item.to" class="qy-mobile-nav-item">
        <component :is="item.icon" aria-hidden="true" /><span>{{ item.label }}</span>
      </RouterLink>
    </nav>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { RouterLink, useRouter } from 'vue-router';
import { useSessionStore } from '../stores/session.js';
import {
  AdjustmentsHorizontalIcon,
  ArrowRightOnRectangleIcon,
  BookOpenIcon,
  DocumentTextIcon,
  InformationCircleIcon,
} from '@heroicons/vue/24/outline';

const router = useRouter();
const session = useSessionStore();
const navItems = [
  { to: '/workbench', label: '翻译工作台', icon: DocumentTextIcon },
  { to: '/termbase', label: '专业词库', icon: BookOpenIcon },
  { to: '/settings', label: '参数设置', icon: AdjustmentsHorizontalIcon },
];
const initials = computed(() => (session.user?.display_name || session.user?.name || 'Q').trim().slice(0, 1).toUpperCase());

async function signOut() {
  try { await session.logout(); } finally { router.push({ name: 'login' }); }
}
</script>
