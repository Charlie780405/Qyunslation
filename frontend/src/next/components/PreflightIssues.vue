<template>
  <section v-if="show" class="qy-preflight-issues" data-preflight-issues aria-label="预检发现的限制">
    <p v-if="summaryText" class="qy-preflight-summary" data-preflight-summary>{{ summaryText }}</p>
    <p v-if="blockers.length" class="qy-preflight-blocked" role="alert" data-preflight-blocked>
      <strong>不能开始翻译</strong>：下面{{ blockers.length > 1 ? ' ' + blockers.length + ' 项' : '这一项' }}问题需要先处理。
    </p>
    <ul class="qy-issue-list">
      <li v-for="(issue, index) in ordered" :key="`${issue.code}-${index}`" class="qy-issue" :data-severity="issue.severity" :data-issue-code="issue.code">
        <span class="qy-issue-badge" :class="`is-${issue.severity}`">{{ SEVERITY[issue.severity] || '提示' }}</span>
        <div>
          <strong>{{ issue.message }}</strong>
          <p v-if="issue.impact"><span>影响：</span>{{ issue.impact }}</p>
          <p v-if="issue.action"><span>建议：</span>{{ issue.action }}</p>
        </div>
      </li>
    </ul>
  </section>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({ preflight: { type: Object, default: null } });

const SEVERITY = { blocker: '阻断', warning: '注意', info: '提示' };
const RANK = { blocker: 0, warning: 1, info: 2 };

const issues = computed(() => (props.preflight?.issues || []).filter((issue) => issue && issue.message));
const blockers = computed(() => issues.value.filter((issue) => issue.severity === 'blocker'));
const ordered = computed(() => [...issues.value].sort((a, b) => (RANK[a.severity] ?? 3) - (RANK[b.severity] ?? 3)));

// "12 页 · 扫描页 3 · 表格 2 · 图片 5": only what the probe actually found.
const summaryText = computed(() => {
  const summary = props.preflight?.manifest_summary || {};
  const parts = [];
  if (summary.pages) parts.push(`${summary.pages} 页`);
  if (summary.paragraphs) parts.push(`${summary.paragraphs} 个段落`);
  if (summary.characters) parts.push(`${summary.characters} 个字符`);
  if (summary.scanned_pages) parts.push(`扫描页约 ${summary.scanned_pages}`);
  if (summary.tables) parts.push(`表格 ${summary.tables}`);
  if (summary.images) parts.push(`图片 ${summary.images}`);
  if (summary.width && summary.height) parts.push(`${summary.width}×${summary.height} 像素`);
  return parts.join(' · ');
});

const show = computed(() => Boolean(props.preflight) && (issues.value.length > 0 || summaryText.value !== ''));
</script>
