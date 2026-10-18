import { createApp } from 'vue';
import { createPinia } from 'pinia';
import NextApp from './next/AppNext.vue';
import nextRouter from './next/router.js';
import './style.css';
import './next/next.css';
import { installQyuns } from './next/qyuns/index.js'; // QyunsApps 统一品牌色与顶栏；必须在 next.css 之后导入

const isNextSurface = window.location.pathname === '/next'
    || window.location.pathname.startsWith('/next/');

if (installQyuns(nextRouter)) {
    // /next/qyuns-logout：已由 installQyuns 处理，不启动应用
} else if (isNextSurface) {
    const app = createApp(NextApp);
    app.use(createPinia());
    app.use(nextRouter);
    app.mount('#app');
} else {
    // Keep the existing Vue page available for the legacy sidecar during migration.
    import('./App.vue').then(({ default: LegacyApp }) => {
        createApp(LegacyApp).mount('#app');
    });
}
