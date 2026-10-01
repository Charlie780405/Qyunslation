import { createRouter, createWebHistory } from 'vue-router';
import LoginPage from './pages/LoginPage.vue';
import WorkbenchPage from './pages/WorkbenchPage.vue';
import RunDetailPage from './pages/RunDetailPage.vue';
import TermbasePage from './pages/TermbasePage.vue';
import SettingsPage from './pages/SettingsPage.vue';
import { useSessionStore } from './stores/session.js';

const router = createRouter({
  history: createWebHistory('/next'),
  routes: [
    { path: '/login', name: 'login', component: LoginPage, meta: { public: true } },
    { path: '/', redirect: '/workbench' },
    { path: '/workbench', name: 'workbench', component: WorkbenchPage },
    { path: '/workbench/:runId', name: 'workbench-run', component: RunDetailPage, props: true },
    { path: '/termbase', name: 'termbase', component: TermbasePage },
    { path: '/settings', name: 'settings', component: SettingsPage },
    {
      path: '/settings/admin',
      name: 'settings-admin',
      component: SettingsPage,
      props: { admin: true },
      meta: { requiresPolicy: true },
    },
    { path: '/:pathMatch(.*)*', redirect: '/workbench' },
  ],
});

router.beforeEach(async (to) => {
  if (to.meta.public) return true;
  const session = useSessionStore();
  await session.load();
  if (session.state === 'anonymous' && !session.isPreview) {
    return { name: 'login', query: { return_to: to.fullPath } };
  }
  if (!session.isPreview && !session.hasCapability('workbench_v2')) {
    return { name: 'login', query: { denied: 'workbench_v2' } };
  }
  if (to.meta.requiresPolicy && !session.isPreview && !session.hasCapability('can_manage_policy')) {
    return { name: 'settings', query: { denied: 'can_manage_policy' } };
  }
  return true;
});

export default router;
