<script setup>
import { ref, onMounted } from 'vue'

const summary = ref(null)
const positions = ref([])
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [s, p] = await Promise.all([
      fetch('/api/performance/summary').then(r => r.json()),
      fetch('/api/positions').then(r => r.json()),
    ])
    summary.value = s
    positions.value = p
  } catch (e) {
    error.value = `加载失败: ${e.message}`
  } finally {
    loading.value = false
  }
}

onMounted(load)

function fmt(v) {
  return v === null || v === undefined ? '—' : Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtPct(v) {
  return v === null || v === undefined ? '—' : `${v > 0 ? '+' : ''}${Number(v).toFixed(2)}%`
}
function color(v) {
  if (v === null || v === undefined) return ''
  return v > 0 ? '#f53f3f' : v < 0 ? '#00b42a' : ''
}
</script>

<template>
  <div>
    <div style="display:flex; align-items:center; gap:12px; margin-bottom:16px;">
      <h2 style="font-size:16px; margin:0;">持仓管理</h2>
      <a-spin v-if="loading" size="small" />
      <span style="color:#f53f3f; font-size:13px;" v-if="error">{{ error }}</span>
    </div>

    <!-- 收益汇总卡片 -->
    <div v-if="summary" style="display:grid; grid-template-columns:repeat(4, 1fr); gap:12px; margin-bottom:16px;">
      <a-card :bordered="true" style="border-radius:8px;">
        <div style="font-size:13px; color:var(--color-text-3);">总市值</div>
        <div style="font-size:20px; font-weight:600; margin-top:4px;">{{ fmt(summary.total_market_value) }}</div>
      </a-card>
      <a-card :bordered="true" style="border-radius:8px;">
        <div style="font-size:13px; color:var(--color-text-3);">总成本</div>
        <div style="font-size:20px; font-weight:600; margin-top:4px;">{{ fmt(summary.total_cost) }}</div>
      </a-card>
      <a-card :bordered="true" style="border-radius:8px;">
        <div style="font-size:13px; color:var(--color-text-3);">持仓浮盈</div>
        <div style="font-size:20px; font-weight:600; margin-top:4px;" :style="{ color: color(summary.total_unrealized) }">
          {{ fmt(summary.total_unrealized) }}
          <span style="font-size:13px;">（{{ fmtPct(summary.total_unrealized_pct) }}）</span>
        </div>
      </a-card>
      <a-card :bordered="true" style="border-radius:8px;">
        <div style="font-size:13px; color:var(--color-text-3);">已实现盈亏</div>
        <div style="font-size:20px; font-weight:600; margin-top:4px;" :style="{ color: color(summary.total_realized) }">
          {{ fmt(summary.total_realized) }}
        </div>
      </a-card>
    </div>

    <!-- 持仓表格 -->
    <a-card :bordered="true" style="border-radius:8px;">
      <a-table :data="positions.map((r, i) => ({ key: i, ...r }))" :pagination="false" :bordered="true" size="small" :scroll="{ x: 'max-content' }">
        <template #columns>
          <a-table-column title="代码" data-index="code" :width="100" />
          <a-table-column title="名称" data-index="name" />
          <a-table-column title="股数" data-index="shares" :width="90" align="right">
            <template #cell="{ record }">{{ record.shares }}</template>
          </a-table-column>
          <a-table-column title="成本价" :width="100" align="right">
            <template #cell="{ record }">{{ fmt(record.cost) }}</template>
          </a-table-column>
          <a-table-column title="现价" :width="100" align="right">
            <template #cell="{ record }">{{ fmt(record.latest_close) }}</template>
          </a-table-column>
          <a-table-column title="市值" :width="110" align="right">
            <template #cell="{ record }">{{ fmt(record.market_value) }}</template>
          </a-table-column>
          <a-table-column title="浮盈" :width="110" align="right">
            <template #cell="{ record }">
              <span :style="{ color: color(record.unrealized) }">{{ fmt(record.unrealized) }}</span>
            </template>
          </a-table-column>
          <a-table-column title="浮盈%" :width="90" align="right">
            <template #cell="{ record }">
              <span :style="{ color: color(record.unrealized_pct) }">{{ fmtPct(record.unrealized_pct) }}</span>
            </template>
          </a-table-column>
          <a-table-column title="操作" :width="120">
            <template #cell="{ record }">
              <a-space>
                <router-link class="table-link" to="/market/kline">K线</router-link>
                <router-link class="table-link" :to="`/market/transaction?code=${record.code}`">交易</router-link>
              </a-space>
            </template>
          </a-table-column>
        </template>
      </a-table>
    </a-card>
  </div>
</template>
