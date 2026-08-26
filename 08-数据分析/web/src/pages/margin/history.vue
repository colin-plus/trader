<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import StockSearch from '../../components/StockSearch.vue'

const route = useRoute()
const selected = ref('all')
const rows = ref([])
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const q = selected.value === 'all' ? '' : `?code=${selected.value}`
    rows.value = await fetch(`/api/margin/evaluations${q}`).then(r => r.json())
  } catch (e) {
    error.value = `加载失败: ${e.message}`
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  const codeParam = route.query.code
  if (codeParam) selected.value = codeParam
  await load()
})

watch(selected, load)

function fmt(v) {
  return v === null || v === undefined ? '—' : Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtPct(v) {
  return v === null || v === undefined ? '—' : `${Number(v).toFixed(2)}%`
}
function levelColor(level) {
  return { '充足': 'green', '一般': 'orange', '不足': 'red', '无边际': 'gray' }[level] || 'gray'
}
</script>

<template>
  <div>
    <div style="display:flex; align-items:center; gap:12px; margin-bottom:16px;">
      <h2 style="font-size:16px; margin:0;">评估历史</h2>
      <StockSearch v-model="selected" />
      <a-spin v-if="loading" size="small" />
      <span style="color:#f53f3f; font-size:13px;" v-if="error">{{ error }}</span>
    </div>

    <a-card :bordered="true" style="border-radius:8px;">
      <a-table :data="rows.map((r, i) => ({ key: i, ...r }))" :pagination="false" :bordered="true" size="small" :scroll="{ x: 'max-content' }">
        <template #columns>
          <a-table-column title="评估日期" data-index="eval_date" :width="120" />
          <a-table-column title="代码" data-index="code" :width="100" />
          <a-table-column title="名称" data-index="name" />
          <a-table-column title="价格" :width="90" align="right">
            <template #cell="{ record }">{{ fmt(record.price) }}</template>
          </a-table-column>
          <a-table-column title="PE" :width="90" align="right">
            <template #cell="{ record }">{{ fmt(record.pe) }}</template>
          </a-table-column>
          <a-table-column title="PE分位" :width="90" align="right">
            <template #cell="{ record }">
              <span :style="{ color: record.pe_percentile !== null && record.pe_percentile <= 30 ? '#00b42a' : 'inherit' }">{{ fmtPct(record.pe_percentile) }}</span>
            </template>
          </a-table-column>
          <a-table-column title="PB" :width="90" align="right">
            <template #cell="{ record }">{{ fmt(record.pb) }}</template>
          </a-table-column>
          <a-table-column title="PB分位" :width="90" align="right">
            <template #cell="{ record }">
              <span :style="{ color: record.pb_percentile !== null && record.pb_percentile <= 30 ? '#00b42a' : 'inherit' }">{{ fmtPct(record.pb_percentile) }}</span>
            </template>
          </a-table-column>
          <a-table-column title="股息率" :width="90" align="right">
            <template #cell="{ record }">
              <span :style="{ color: record.dividend_yield >= 3 ? '#00b42a' : 'inherit' }">{{ fmtPct(record.dividend_yield) }}</span>
            </template>
          </a-table-column>
          <a-table-column title="结论" :width="90" align="center">
            <template #cell="{ record }">
              <a-tag :color="levelColor(record.margin_level)" size="small">{{ record.margin_level }}</a-tag>
            </template>
          </a-table-column>
        </template>
      </a-table>
    </a-card>
  </div>
</template>
