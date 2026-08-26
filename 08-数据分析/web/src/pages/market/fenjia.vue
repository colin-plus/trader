<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import FenjiaChart from '../../components/FenjiaChart.vue'
import StockSearch from '../../components/StockSearch.vue'

const route = useRoute()
const selected = ref('all')  // 默认空白，选择后才加载
const data = ref(null)
const loading = ref(false)
const error = ref('')

async function load() {
  if (selected.value === 'all') {
    data.value = null
    return
  }
  loading.value = true
  error.value = ''
  try {
    const r = await fetch(`/api/volume-profile/${selected.value}?days=10`)
    data.value = await r.json()
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
</script>

<template>
  <div>
    <div style="display:flex; align-items:center; gap:12px; margin-bottom:16px;">
      <h2 style="font-size:16px; margin:0;">分价成交量</h2>
      <StockSearch v-model="selected" />
      <a-spin v-if="loading" size="small" />
      <span style="color:#f53f3f; font-size:13px;" v-if="error">{{ error }}</span>
    </div>
    <a-card v-if="data" :bordered="true" style="border-radius:8px;">
      <FenjiaChart :data="data.rows" />
    </a-card>
    <a-empty v-else-if="!loading" description="请搜索并选择标的" style="margin-top:40px;" />
  </div>
</template>
