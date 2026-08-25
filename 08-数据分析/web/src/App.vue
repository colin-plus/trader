<script setup>
import { ref, onMounted, watch } from 'vue'
import KlineChart from './components/KlineChart.vue'
import FenjiaChart from './components/FenjiaChart.vue'
import FundFlowChart from './components/FundFlowChart.vue'

const stocks = ref([])
const selected = ref('003043')
const kline = ref(null)
const fenjia = ref(null)
const fundflow = ref(null)
const loading = ref(false)
const error = ref('')

async function fetchStocks() {
  const r = await fetch('/api/stocks')
  stocks.value = await r.json()
}

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const [k, f, ff] = await Promise.all([
      fetch(`/api/kline/${selected.value}?days=120`).then(r => r.json()),
      fetch(`/api/fenjia/${selected.value}?days=10`).then(r => r.json()),
      fetch(`/api/fundflow/${selected.value}?days=60`).then(r => r.json()),
    ])
    kline.value = k
    fenjia.value = f
    fundflow.value = ff
  } catch (e) {
    error.value = `加载失败: ${e.message}`
  } finally {
    loading.value = false
  }
}

watch(selected, loadAll)
onMounted(async () => {
  await fetchStocks()
  await loadAll()
})
</script>

<template>
  <div style="max-width: 1280px; margin: 0 auto; padding: 20px;">
    <header style="display: flex; align-items: center; gap: 16px; margin-bottom: 20px;">
      <h1 style="font-size: 20px;">Trader Data</h1>
      <select v-model="selected" style="padding: 6px 10px; background: var(--panel); color: var(--text); border: 1px solid var(--border); border-radius: 6px;">
        <option v-for="s in stocks" :key="s.code" :value="s.code">{{ s.name }}（{{ s.code }}）</option>
      </select>
      <span class="muted" v-if="loading">加载中…</span>
      <span style="color: #ef4444; font-size: 13px;" v-if="error">{{ error }}</span>
    </header>

    <div class="panel" v-if="kline">
      <h2>日线 K 线（{{ kline.name }}）</h2>
      <KlineChart :data="kline.rows" />
    </div>

    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
      <div class="panel" v-if="fenjia">
        <h2>分价成交量（近 10 日）</h2>
        <FenjiaChart :data="fenjia.rows" />
      </div>
      <div class="panel" v-if="fundflow">
        <h2>资金流向（主力 vs 散户）</h2>
        <FundFlowChart :data="fundflow.rows" />
      </div>
    </div>

    <footer class="muted" style="margin-top: 20px; text-align: center;">
      数据来源：腾讯行情 / 东方财富 · duckdb 本地存储 · 仅供学习研究
    </footer>
  </div>
</template>
