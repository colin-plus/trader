<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import FundFlowChart from '../../components/FundFlowChart.vue'
import StockSearch from '../../components/StockSearch.vue'

const route = useRoute()
const tab = ref('stock')
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
    const r = await fetch(`/api/capital-flow/${selected.value}?days=60`)
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
      <h2 style="font-size:16px; margin:0;">资金流向</h2>
      <a-tabs v-model:active-key="tab" size="small" type="line" style="flex:1;">
        <a-tab-pane key="stock" title="个股" />
        <a-tab-pane key="sector" title="行业板块" />
      </a-tabs>
    </div>

    <!-- 个股资金流 -->
    <template v-if="tab === 'stock'">
      <div style="display:flex; align-items:center; gap:12px; margin-bottom:16px;">
        <StockSearch v-model="selected" />
        <a-spin v-if="loading" size="small" />
        <span style="color:#f53f3f; font-size:13px;" v-if="error">{{ error }}</span>
      </div>
      <a-card v-if="data" :bordered="true" style="border-radius:8px;">
        <FundFlowChart :data="data.rows" />
      </a-card>
      <a-empty v-else-if="!loading" description="请搜索并选择标的" style="margin-top:40px;" />
    </template>

    <!-- 行业板块资金流（待开发） -->
    <template v-else>
      <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; height:50vh; color:var(--color-text-4);">
        <div style="font-size:36px; margin-bottom:12px;">🚧</div>
        <div>行业板块资金流开发中</div>
      </div>
    </template>
  </div>
</template>
