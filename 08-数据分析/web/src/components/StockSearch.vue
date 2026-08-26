<script setup>
// 股票搜索公共组件（用户定规矩：auto-complete 远程搜索补全 + 选中回填"名称（代码）"）
// 用法：<StockSearch v-model="selectedCode" />
//  - v-model: 选中的 code（清空时置 'all'）
//  - 选中后回填"名称（代码）"格式，并 emit 'select'（可选监听）
import { ref, watch, nextTick } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: 'all' },
  placeholder: { type: String, default: '搜索代码/名称…' },
  width: { type: String, default: '220px' },
})
const emit = defineEmits(['update:modelValue', 'select'])

const query = ref('')
const searchOptions = ref([])
const searchLoading = ref(false)

// 远程搜索：输入代码/名称 → 后端返回前 20 条
async function onSearch(q) {
  if (!q || q.trim().length < 1) {
    searchOptions.value = []
    return
  }
  searchLoading.value = true
  try {
    const r = await fetch(`/api/stocks/search?q=${encodeURIComponent(q.trim())}`)
    searchOptions.value = (await r.json()).map(x => ({ label: `${x.name}（${x.code}）`, value: x.code }))
  } catch (e) {
    searchOptions.value = []
  } finally {
    searchLoading.value = false
  }
}

// 选中补全项 → 回填"名称（代码）" + 更新 v-model
// Arco handleSelect 先 emit("select") 再 handleChange 写 code，用 nextTick 覆盖
function onSelect(code) {
  const hit = searchOptions.value.find(o => o.value === code)
  emit('update:modelValue', code)
  emit('select', code)
  if (hit) {
    nextTick(() => { query.value = hit.label })
  }
}

// 外部重置（如清空）时同步清空输入框
watch(() => props.modelValue, v => {
  if (v === 'all' || v === undefined || v === null || v === '') {
    query.value = ''
  }
})

// 清空输入 → 恢复默认
watch(query, v => {
  if (!v || v.trim() === '') {
    emit('update:modelValue', 'all')
  }
})
</script>

<template>
  <a-auto-complete
    v-model="query"
    :data="searchOptions"
    :style="{ width }"
    :placeholder="placeholder"
    allow-clear
    @search="onSearch"
    @select="onSelect"
  />
</template>
