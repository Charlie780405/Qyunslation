<template>
  <Modal :modelValue="modelValue" @update:modelValue="$emit('update:modelValue', $event)" title="扩展工具" size="max-w-4xl">
    <!-- Tab 切换 -->
    <div class="flex gap-2 mb-4 border-b border-gray-200 dark:border-gray-700">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        class="px-4 py-2 text-sm font-medium border-b-2 transition-colors"
        :class="activeTab === tab.id ? 'border-primary text-primary' : 'border-transparent text-gray-500 hover:text-gray-700'"
        @click="activeTab = tab.id"
      >{{ tab.label }}</button>
    </div>

    <!-- Tab 1: 图片嵌字 -->
    <div v-if="activeTab === 'image'">
      <div class="flex gap-4 items-center mb-4">
        <input type="file" accept="image/*" class="text-sm" @change="onImageSelect" />
        <span v-if="imgLoading" class="text-sm text-gray-500">嵌字中…</span>
        <span v-if="imgError" class="text-sm text-red-500">{{ imgError }}</span>
      </div>
      <div v-if="imgOriginal || imgTranslated" class="grid grid-cols-2 gap-4">
        <div>
          <div class="text-sm font-medium mb-1 text-gray-600">原文</div>
          <img v-if="imgOriginal" :src="imgOriginal" class="border rounded max-h-[420px] mx-auto" />
        </div>
        <div>
          <div class="text-sm font-medium mb-1 text-gray-600">译文（嵌字后）</div>
          <img v-if="imgTranslated" :src="imgTranslated" class="border rounded max-h-[420px] mx-auto" />
        </div>
      </div>
    </div>

    <!-- Tab 2: 术语表库 -->
    <div v-else-if="activeTab === 'glossary'">
      <div class="flex gap-2 mb-3">
        <input v-model="newSrc" placeholder="源术语（如 atopic dermatitis）" class="flex-1 px-3 py-1.5 border rounded text-sm" />
        <input v-model="newDst" placeholder="译文（如 特应性皮炎）" class="flex-1 px-3 py-1.5 border rounded text-sm" />
        <button class="px-3 py-1.5 text-sm bg-primary text-white rounded hover:opacity-90" @click="addGlossary">添加</button>
      </div>
      <div class="max-h-[400px] overflow-auto border rounded">
        <table class="w-full text-sm">
          <thead class="sticky top-0 bg-gray-50 dark:bg-gray-700">
            <tr class="text-left">
              <th class="px-3 py-2 font-medium">源术语</th>
              <th class="px-3 py-2 font-medium">译文</th>
              <th class="px-3 py-2 w-16"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(dst, src) in glossaryData" :key="src" class="border-t">
              <td class="px-3 py-1.5">{{ src }}</td>
              <td class="px-3 py-1.5">{{ dst }}</td>
              <td class="px-3 py-1.5">
                <button class="text-red-500 hover:text-red-700 text-xs" @click="removeGlossary(src)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="text-xs text-gray-500 mt-2">共 {{ glossaryCount }} 条术语（预置 + 自定义）</div>
    </div>
  </Modal>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import Modal from '../ui/Modal.vue';

defineProps({ modelValue: Boolean });
defineEmits(['update:modelValue']);

const tabs = [
  { id: 'image', label: '图片嵌字' },
  { id: 'glossary', label: '术语表库' },
];
const activeTab = ref('image');

// 图片嵌字
const imgOriginal = ref('');
const imgTranslated = ref('');
const imgLoading = ref(false);
const imgError = ref('');

async function onImageSelect(e) {
  const file = e.target.files[0];
  if (!file) return;
  imgError.value = '';
  imgOriginal.value = URL.createObjectURL(file);
  imgTranslated.value = '';
  imgLoading.value = true;
  try {
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch('/service/image-translate', { method: 'POST', body: fd });
    if (!res.ok) throw new Error((await res.text()).slice(0, 200));
    const blob = await res.blob();
    imgTranslated.value = URL.createObjectURL(blob);
  } catch (e) {
    imgError.value = '嵌字失败: ' + e.message;
  } finally {
    imgLoading.value = false;
  }
}

// 术语表库
const glossaryData = ref({});
const glossaryCount = ref(0);
const newSrc = ref('');
const newDst = ref('');

async function loadGlossary() {
  try {
    const res = await fetch('/service/glossary');
    const d = await res.json();
    glossaryData.value = d.glossary || {};
    glossaryCount.value = d.count || 0;
  } catch (e) {}
}

async function addGlossary() {
  if (!newSrc.value.trim() || !newDst.value.trim()) return;
  try {
    await fetch('/service/glossary', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ src: newSrc.value.trim(), dst: newDst.value.trim() }),
    });
    newSrc.value = '';
    newDst.value = '';
    await loadGlossary();
  } catch (e) {}
}

async function removeGlossary(src) {
  try {
    await fetch('/service/glossary/' + encodeURIComponent(src), { method: 'DELETE' });
    await loadGlossary();
  } catch (e) {}
}

onMounted(loadGlossary);
</script>
