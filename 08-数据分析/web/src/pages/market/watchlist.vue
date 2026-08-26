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
        :scroll="{ x: 'max-content' }"
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
            <template #cell>
              <a-space>
                <router-link class="table-link" to="/market/kline">K线</router-link>
                <router-link class="table-link" to="/market/fenjia">分价</router-link>
                <router-link class="table-link" to="/market/fundflow">资金流</router-link>
                <router-link class="table-link" to="/market/finance">财务</router-link>
              </a-space>
            </template>
          </a-table-column>
        </template>
      </a-table>
    </a-card>
  </div>
</template>
