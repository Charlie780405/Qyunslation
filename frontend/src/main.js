import { createApp } from 'vue';
import { createPinia } from 'pinia';
import NextApp from './next/AppNext.vue';
import nextRouter from './next/router.js';
import './style.css';
import './next/next.css';

const isNextSurface = window.location.pathname === '/next'
    || window.location.pathname.startsWith('/next/');

if (isNextSurface) {
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
