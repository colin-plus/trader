<script setup>
import { ref, onMounted, watch } from 'vue'
import FundFlowChart from '../../components/FundFlowChart.vue'

const stocks = ref([])
const selected = ref('003043')
const data = ref(null)
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
    const r = await fetch(`/api/fundflow/${selected.value}?days=60`)
    data.value = await r.json()
  } catch (e) {
    error.value = `加载失败: ${e.message}`
  } finally {
    loading.value = false
  }
}

watch(selected, load)
onMounted(async () => {
  await fetchStocks()
  await load()
})
</script>

<template>
  <div>
    <div style="display:flex; align-items:center; gap:12px; margin-bottom:16px;">
      <h2 style="font-size:16px;">资金流向</h2>
      <select v-model="selected" style="padding:6px 10px; background:var(--panel); color:var(--text); border:1px solid var(--border); border-radius:6px;">
        <option v-for="s in stocks" :key="s.code" :value="s.code">{{ s.name }}（{{ s.code }}）</option>
      </select>
      <span class="muted" v-if="loading">加载中…</span>
      <span style="color:#ef4444; font-size:13px;" v-if="error">{{ error }}</span>
    </div>
    <div class="panel" v-if="data">
      <FundFlowChart :data="data.rows" />
    </div>
  </div>
</template>
