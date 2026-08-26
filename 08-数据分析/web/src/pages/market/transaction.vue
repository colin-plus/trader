<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const stocks = ref([])
const selected = ref('all')  // 'all' = 全部
const rows = ref([])
const loading = ref(false)
const error = ref('')

async function fetchStocks() {
  const r = await fetch('/api/stocks')
  stocks.value = await r.json()
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const q = selected.value === 'all' ? '' : `?code=${selected.value}`
    rows.value = await fetch(`/api/transactions${q}`).then(r => r.json())
  } catch (e) {
    error.value = `加载失败: ${e.message}`
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await fetchStocks()
  // 支持 URL 参数直达（如 /market/transaction?code=003043）
  const codeParam = route.query.code
  if (codeParam) selected.value = codeParam
  await load()
})

watch(selected, load)

function fmt(v) {
  return v === null || v === undefined ? '—' : Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<template>
  <div>
    <div style="display:flex; align-items:center; gap:12px; margin-bottom:16px;">
      <h2 style="font-size:16px; margin:0;">交易记录</h2>
      <a-select
        v-model="selected"
        :style="{ width: '200px' }"
        :options="[{ label: '全部标的', value: 'all' }, ...stocks.map(s => ({ label: `${s.name}（${s.code}）`, value: s.code }))]"
      />
      <a-spin v-if="loading" size="small" />
      <span style="color:#f53f3f; font-size:13px;" v-if="error">{{ error }}</span>
    </div>

    <a-card :bordered="true" style="border-radius:8px;">
      <a-table :data="rows.map((r, i) => ({ key: i, ...r }))" :pagination="false" :bordered="true" size="small" :scroll="{ x: 'max-content' }">
        <template #columns>
          <a-table-column title="日期" data-index="trade_date" :width="120" />
          <a-table-column title="代码" data-index="code" :width="100" />
          <a-table-column title="名称" data-index="name" />
          <a-table-column title="方向" :width="70">
            <template #cell="{ record }">
              <a-tag :color="record.direction === 'buy' ? 'red' : 'green'" size="small">
                {{ record.direction === 'buy' ? '买入' : '卖出' }}
              </a-tag>
            </template>
          </a-table-column>
          <a-table-column title="价格" :width="90" align="right">
            <template #cell="{ record }">{{ fmt(record.price) }}</template>
          </a-table-column>
          <a-table-column title="数量" :width="90" align="right">
            <template #cell="{ record }">{{ record.shares }}</template>
          </a-table-column>
          <a-table-column title="金额" :width="110" align="right">
            <template #cell="{ record }">{{ fmt(record.amount) }}</template>
          </a-table-column>
          <a-table-column title="费用" :width="90" align="right">
            <template #cell="{ record }">{{ fmt(record.fee) }}</template>
          </a-table-column>
          <a-table-column title="备注" data-index="note" />
        </template>
      </a-table>
    </a-card>
  </div>
</template>
