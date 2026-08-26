<script setup>
import { ref, computed, onMounted } from 'vue'
import StockSearch from '../../components/StockSearch.vue'

const stocks = ref([])
const rows = ref([])
const macro = ref(null)
const loading = ref(false)
const error = ref('')
const filterCode = ref('all')
const filterLevel = ref([])  // 多选，空数组 = 全部结论

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [s, m] = await Promise.all([
      fetch('/api/stocks').then(r => r.json()),
      fetch('/api/margin/macro').then(r => r.json()),
    ])
    stocks.value = s
    macro.value = m[0] || null
    const statuses = await Promise.all(
      s.map(st => fetch(`/api/margin/status/${st.code}`).then(r => r.json()))
    )
    rows.value = statuses.map((d, i) => ({
      key: i,
      code: d.code,
      name: d.name,
      close: d.price,           // 最新收盘价（status API 的 price 字段）
      ...(d.latest || {}),
      pe_pct: d.percentile_5y?.pe,
      pb_pct: d.percentile_5y?.pb,
      evals: d.evaluation_count,
    }))
  } catch (e) {
    error.value = `加载失败: ${e.message}`
  } finally {
    loading.value = false
  }
}

onMounted(load)

// 筛选：股票 + 结论（多选，空数组 = 全部）
const filtered = computed(() => {
  return rows.value.filter(r => {
    const codeOk = filterCode.value === 'all' || r.code === filterCode.value
    const level = levelTag(r.pe, r.pb, r.dividend_yield).text
    const levelOk = filterLevel.value.length === 0 || filterLevel.value.includes(level)
    return codeOk && levelOk
  })
})

function fmt(v) {
  return v === null || v === undefined ? '—' : Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtPct(v) {
  return v === null || v === undefined ? '—' : `${Number(v).toFixed(1)}%`
}
function levelTag(pe, pb, dy) {
  // 与 eval_margin.py 同规则：股息≥3% + PB≤1.5 或分位≤30%
  if (pe === null || pe === undefined) return { text: '—', color: 'gray' }
  const a = dy >= 3
  const c = pb !== null && pb <= 1.5
  if (a && c) return { text: '充足', color: 'green' }
  if (a || c) return { text: '一般', color: 'orange' }
  return { text: '无', color: 'red' }
}
</script>

<template>
  <div>
    <div style="display:flex; align-items:center; gap:12px; margin-bottom:16px;">
      <h2 style="font-size:16px; margin:0;">安全边际评估看板</h2>
      <StockSearch v-model="filterCode" />
      <a-select
        v-model="filterLevel"
        :style="{ width: '240px' }"
        :popup-container="() => document.body"
        multiple
        allow-clear
        class="level-select"
        :options="[
          { label: '充足', value: '充足' },
          { label: '一般', value: '一般' },
          { label: '不足', value: '不足' },
          { label: '无', value: '无' },
        ]"
        placeholder="结论筛选（多选）"
      />
      <a-spin v-if="loading" size="small" />
      <span style="color:#f53f3f; font-size:13px;" v-if="error">{{ error }}</span>
    </div>

    <!-- 宏观基准 -->
    <div v-if="macro" style="margin-bottom:16px; font-size:13px; color:var(--color-text-3);">
      10 年期国债收益率：<b style="color:var(--color-text-1);">{{ macro.cn10y }}%</b>
      （{{ macro.date }}）· 股息率安全线 ≥ {{ (macro.cn10y * 1.5).toFixed(2) }}%
    </div>

    <a-card :bordered="true" style="border-radius:8px;">
      <a-table :data="filtered" :pagination="false" :bordered="true" size="small" :scroll="{ x: 'max-content' }">
        <template #columns>
          <a-table-column title="代码" data-index="code" :width="100" />
          <a-table-column title="名称" data-index="name" />
          <a-table-column title="现价" :width="90" align="right">
            <template #cell="{ record }">{{ fmt(record.close) }}</template>
          </a-table-column>
          <a-table-column title="PE" :width="90" align="right">
            <template #cell="{ record }">{{ fmt(record.pe) }}</template>
          </a-table-column>
          <a-table-column title="PE分位" :width="90" align="right">
            <template #cell="{ record }">
              <span :style="{ color: record.pe_pct !== null && record.pe_pct <= 30 ? '#00b42a' : 'inherit' }">{{ fmtPct(record.pe_pct) }}</span>
            </template>
          </a-table-column>
          <a-table-column title="PB" :width="90" align="right">
            <template #cell="{ record }">{{ fmt(record.pb) }}</template>
          </a-table-column>
          <a-table-column title="股息率" :width="90" align="right">
            <template #cell="{ record }">
              <span :style="{ color: record.dividend_yield >= 3 ? '#00b42a' : 'inherit' }">{{ fmtPct(record.dividend_yield) }}</span>
            </template>
          </a-table-column>
          <a-table-column title="结论" :width="80" align="center">
            <template #cell="{ record }">
              <a-tag :color="levelTag(record.pe, record.pb, record.dividend_yield).color" size="small">
                {{ levelTag(record.pe, record.pb, record.dividend_yield).text }}
              </a-tag>
            </template>
          </a-table-column>
          <a-table-column title="评估次数" :width="90" align="right">
            <template #cell="{ record }">{{ record.evals }}</template>
          </a-table-column>
          <a-table-column title="操作" :width="100">
            <template #cell="{ record }">
              <router-link class="table-link" :to="`/margin/history?code=${record.code}`">历史</router-link>
            </template>
          </a-table-column>
        </template>
      </a-table>
    </a-card>
  </div>
</template>

<style scoped>
/* 结论多选标签单行显示：不换行，超宽横向滚动（标签全部可达） */
.level-select :deep(.arco-select-view) {
  flex-wrap: nowrap;
  overflow-x: auto;
  overflow-y: hidden;
}
.level-select :deep(.arco-select-view .arco-select-view-value) {
  flex-wrap: nowrap;
  white-space: nowrap;
}
</style>
