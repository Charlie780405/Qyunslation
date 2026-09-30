<template>
  <main class="qy-login-page">
    <section class="qy-login-panel" aria-labelledby="login-title">
      <div class="qy-login-brand">
        <img src="/static/quanxin-logo.svg" alt="荃信" class="qy-login-logo" />
        <span class="qy-eyebrow">QYUNSLATION WORKSPACE</span>
      </div>
      <h1 id="login-title">进入临床翻译工作台</h1>
      <p class="qy-login-lead">面向医药文档的翻译、术语审核与受控交付。</p>

      <div v-if="message" class="qy-callout qy-callout-warning" role="alert">
        <ExclamationTriangleIcon aria-hidden="true" />
        <span>{{ message }}</span>
      </div>

      <button class="qy-primary-button qy-login-button" type="button" @click="login">
        <ShieldCheckIcon aria-hidden="true" /> 使用公司账号登录
        <ArrowRightIcon aria-hidden="true" />
      </button>
      <p class="qy-login-note"><LockClosedIcon aria-hidden="true" /> 通过公司身份服务安全登录，应用不会保存你的密码。</p>

      <div v-if="session.isPreview" class="qy-preview-entry">
        <span>本地开发预览</span>
        <RouterLink to="/workbench">查看工作台界面</RouterLink>
      </div>
    </section>
    <aside class="qy-login-aside" aria-label="工作台能力">
      <div class="qy-login-aside-content">
        <span class="qy-aside-kicker">CLINICAL TRANSLATION CONTROL</span>
        <h2>每个术语、每个版本，都能回到证据。</h2>
        <p>从预检到导出，以文档对象、专业词库和 QA 门禁串起一次可复核的翻译任务。</p>
        <div class="qy-login-feature-list">
          <span><CheckCircleIcon aria-hidden="true" /> 源文只读，译文可追溯</span>
          <span><CheckCircleIcon aria-hidden="true" /> 高风险术语自动标记</span>
          <span><CheckCircleIcon aria-hidden="true" /> 正式导出前检查 blocker</span>
        </div>
      </div>
      <span class="qy-login-vertical-label">QYUNSLATION / 066</span>
    </aside>
  </main>
</template>

<script setup>
import { ref } from 'vue';
import { RouterLink } from 'vue-router';
import { useSessionStore } from '../stores/session.js';
import {
  ArrowRightIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  LockClosedIcon,
  ShieldCheckIcon,
} from '@heroicons/vue/24/outline';

const session = useSessionStore();
const message = ref('');

async function login() {
  message.value = '';
  try {
    await session.beginLogin();
  } catch (error) {
    message.value = error?.message || '公司身份服务暂不可用，请稍后重试。';
  }
}
</script>
