<script setup>
import { ref, onMounted } from 'vue'

const stocks = ref([])
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const r = await fetch('/api/stocks')
    stocks.value = await r.json()
  } catch (e) {
    error.value = `加载失败: ${e.message}`
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div style="display:flex; align-items:center; gap:12px; margin-bottom:16px;">
      <h2 style="font-size:16px; margin:0;">关注标的</h2>
      <a-button type="primary" size="small">添加标的</a-button>
      <a-spin v-if="loading" size="small" />
      <span style="color:#f53f3f; font-size:13px;" v-if="error">{{ error }}</span>
    </div>
    <a-card :bordered="true" style="border-radius:8px;">
      <a-table
        :data="stocks.map((s, i) => ({ key: i, ...s }))"
        :pagination="false"
        :bordered="true"
        size="small"
      >
        <template #columns>
          <a-table-column title="代码" data-index="code" :width="100" />
          <a-table-column title="名称" data-index="name" />
          <a-table-column title="现价" :width="100">
            <template #cell>—</template>
          </a-table-column>
          <a-table-column title="涨跌" :width="100">
            <template #cell>—</template>
          </a-table-column>
          <a-table-column title="操作" :width="260">
            <template #cell="{ record }">
              <a-space>
                <a-link href="#/market/kline">K线</a-link>
                <a-link href="#/market/fenjia">分价</a-link>
                <a-link href="#/market/fundflow">资金流</a-link>
                <a-link href="#/market/finance">财务</a-link>
              </a-space>
            </template>
          </a-table-column>
        </template>
      </a-table>
    </a-card>
  </div>
</template>
