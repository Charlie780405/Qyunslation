<template>
  <div class="qy-app-shell" :class="{ 'is-sidebar-collapsed': sidebarCollapsed }">
    <header class="qy-topbar">
      <RouterLink class="qy-brand" to="/workbench" aria-label="返回翻译工作台">
        <img src="/app-assets/qyunslation-mark.png" alt="" class="qy-brand-mark" />
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
        <button
          class="qy-sidebar-toggle"
          type="button"
          :aria-label="sidebarCollapsed ? '展开主导航' : '收起主导航'"
          :aria-expanded="!sidebarCollapsed"
          aria-controls="qy-primary-navigation"
          :title="sidebarCollapsed ? '展开主导航' : '收起主导航'"
          @click="sidebarCollapsed = !sidebarCollapsed"
        >
          <ChevronDoubleRightIcon v-if="sidebarCollapsed" aria-hidden="true" />
          <ChevronDoubleLeftIcon v-else aria-hidden="true" />
          <span>{{ sidebarCollapsed ? '展开侧栏' : '收起侧栏' }}</span>
        </button>
        <nav id="qy-primary-navigation" class="qy-nav-list">
          <RouterLink
            v-for="item in navItems"
            :key="item.to"
            :to="item.to"
            class="qy-nav-item"
            :aria-label="sidebarCollapsed ? item.label : undefined"
            :title="sidebarCollapsed ? item.label : undefined"
          >
            <component :is="item.icon" aria-hidden="true" /><span v-if="!sidebarCollapsed">{{ item.label }}</span>
          </RouterLink>
        </nav>
      </aside>
      <main class="qy-main-content">
        <div v-if="connection.offline.value" class="qy-offline-banner" role="alert" data-offline-banner>
          <ArrowPathIcon class="qy-spin" aria-hidden="true" />
          <span>连接中断，正在重试。页面上的内容是上次加载的，恢复连接后会自动更新。</span>
        </div>
        <slot />
      </main>
    </div>
    <ConfirmDialog />

    <nav class="qy-mobile-nav" aria-label="移动端导航">
      <RouterLink v-for="item in navItems" :key="item.to" :to="item.to" class="qy-mobile-nav-item">
        <component :is="item.icon" aria-hidden="true" /><span>{{ item.label }}</span>
      </RouterLink>
    </nav>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue';
import { RouterLink, useRouter } from 'vue-router';
import { useSessionStore } from '../stores/session.js';
import { connection } from '../stores/connection.js';
import ConfirmDialog from './ConfirmDialog.vue';
import { DEFAULT_END_SESSION_URL } from '../qyuns/logout.js';
import {
  AdjustmentsHorizontalIcon,
  ArrowPathIcon,
  ArrowRightOnRectangleIcon,
  BookOpenIcon,
  ChevronDoubleLeftIcon,
  ChevronDoubleRightIcon,
  DocumentTextIcon,
  InformationCircleIcon,
} from '@heroicons/vue/24/outline';

const router = useRouter();
const session = useSessionStore();
const sidebarCollapsed = ref(false);
const navItems = [
  { to: '/workbench', label: '翻译工作台', icon: DocumentTextIcon },
  { to: '/termbase', label: '专业词库', icon: BookOpenIcon },
  { to: '/settings', label: '参数设置', icon: AdjustmentsHorizontalIcon },
];
const initials = computed(() => (session.user?.display_name || session.user?.name || 'Q').trim().slice(0, 1).toUpperCase());

async function signOut() {
  // 本应用退出后继续结束 Authentik 会话（否则点回来会被静默登录）；Authentik 的 end-session 页是终点
  try { await session.logout(); } finally {
    if (import.meta.env.DEV) router.push({ name: 'login' });
    else window.location.assign(import.meta.env.VITE_QYUNSAPPS_END_SESSION_URL || DEFAULT_END_SESSION_URL);
  }
}
</script>
