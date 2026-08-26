<script setup>
import { ref, computed, onMounted } from 'vue'
import { Message } from '@arco-design/web-vue'
import StockSearch from '../../components/StockSearch.vue'

const rows = ref([])
const macro = ref(null)
const loading = ref(false)
const error = ref('')
const filterCode = ref('all')
const filterLevel = ref([])  // 多选，空数组 = 全部结论

// 新增评估弹窗
const modalVisible = ref(false)
const modalLoading = ref(false)
const modalError = ref('')
const evalCode = ref('all')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [d, m] = await Promise.all([
      fetch('/api/margin/dashboard').then(r => r.json()),
      fetch('/api/margin/macro').then(r => r.json()),
    ])
    rows.value = d.map((r, i) => ({ key: i, ...r }))
    macro.value = m[0] || null
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
    const levelOk = filterLevel.value.length === 0 || filterLevel.value.includes(r.margin_level)
    return codeOk && levelOk
  })
})

// 新增评估提交（后台自动算结论落库）
async function submitEval() {
  if (evalCode.value === 'all') {
    modalError.value = '请选择标的'
    return
  }
  modalLoading.value = true
  modalError.value = ''
  try {
    const r = await fetch('/api/margin/evaluations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: evalCode.value }),
    })
    if (!r.ok) {
      const err = await r.json().catch(() => ({}))
      throw new Error(err.detail || `HTTP ${r.status}`)
    }
    const result = await r.json()
    modalVisible.value = false
    evalCode.value = 'all'
    await load()
    Message.success(`评估成功：${result.code} 结论「${result.margin_level}」`)
  } catch (e) {
    modalError.value = `评估失败: ${e.message}`
  } finally {
    modalLoading.value = false
  }
}

function fmt(v) {
  return v === null || v === undefined ? '—' : Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtPct(v) {
  return v === null || v === undefined ? '—' : `${Number(v).toFixed(1)}%`
}
function levelColor(level) {
  return { '充足': 'green', '一般': 'orange', '不足': 'red', '无边际': 'gray' }[level] || 'gray'
}

// 结论定义说明（页面展示用）
const levelDefs = [
  { level: '充足', color: 'green', desc: '股息率 ≥3% 且 PB ≤1.5，两把尺子都亮——有充分价值垫' },
  { level: '一般', color: 'orange', desc: '股息率 ≥3% 或 PB ≤1.5，亮一把——价值垫有限' },
  { level: '不足', color: 'red', desc: '两把尺子都不亮，但估值不算夸张——不便宜但可评估' },
  { level: '无边际', color: 'gray', desc: '两把尺子都不亮且高 PE（>30）——无价值垫，不属于安全边际投资（≠不能买）' },
]
</script>

<template>
  <div>
    <div style="display:flex; align-items:center; gap:12px; margin-bottom:16px;">
      <h2 style="font-size:16px; margin:0;">安全边际评估看板</h2>
      <StockSearch v-model="filterCode" />
      <a-select
        v-model="filterLevel"
        :style="{ width: '320px' }"
        multiple
        allow-clear
        :options="[
          { label: '充足', value: '充足' },
          { label: '一般', value: '一般' },
          { label: '不足', value: '不足' },
          { label: '无边际', value: '无边际' },
        ]"
        placeholder="结论筛选（多选）"
      />
      <a-spin v-if="loading" size="small" />
      <span style="color:#f53f3f; font-size:13px;" v-if="error">{{ error }}</span>
      <div style="flex:1;"></div>
      <a-button type="primary" size="small" @click="modalVisible = true">新增评估</a-button>
    </div>

    <!-- 宏观基准 + 结论定义问号 -->
    <div v-if="macro" style="display:flex; align-items:center; gap:8px; margin-bottom:16px; font-size:13px; color:var(--color-text-3);">
      <span>10 年期国债收益率：<b style="color:var(--color-text-1);">{{ macro.cn10y }}%</b>
      （{{ macro.date }}）· 股息率安全线 ≥ {{ (macro.cn10y * 1.5).toFixed(2) }}%。</span>
      <a-popover trigger="click" position="bottom">
        <span style="cursor:pointer; color:var(--color-link, #165dff);">查看结论定义</span>
        <template #content>
          <div style="font-size:12px; line-height:2; color:var(--color-text-2);">
            <div style="font-weight:600; color:var(--color-text-1); margin-bottom:4px;">结论定义</div>
            <ul style="margin:0; padding-left:16px;">
              <li v-for="d in levelDefs" :key="d.level">
                <a-tag :color="d.color" size="small" style="margin-right:6px;">{{ d.level }}</a-tag>{{ d.desc }}
              </li>
            </ul>
          </div>
        </template>
      </a-popover>
    </div>

    <a-card :bordered="true" style="border-radius:8px;">
      <a-table :data="filtered" :pagination="false" :bordered="true" size="small" :scroll="{ x: 'max-content' }">
        <template #columns>
          <a-table-column title="代码" data-index="code" :width="100" />
          <a-table-column title="名称" data-index="name" />
          <a-table-column title="评估日期" data-index="eval_date" :width="120" />
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
          <a-table-column title="决策" :width="90">
            <template #cell="{ record }">{{ record.decision || '—' }}</template>
          </a-table-column>
          <a-table-column title="备注" data-index="note" />
          <a-table-column title="操作" :width="100">
            <template #cell="{ record }">
              <router-link class="table-link" :to="`/margin/history?code=${record.code}`">历史</router-link>
            </template>
          </a-table-column>
        </template>
      </a-table>
    </a-card>

    <!-- 新增评估弹窗 -->
    <a-modal
      v-model:visible="modalVisible"
      title="新增评估"
      :width="420"
      @cancel="modalError = ''"
    >
      <div style="display:flex; flex-direction:column; gap:12px;">
        <div>
          <div style="font-size:12px; color:var(--color-text-3); margin-bottom:4px;">标的</div>
          <StockSearch v-model="evalCode" />
        </div>
        <div style="font-size:12px; color:var(--color-text-3);">
          选择标的后点击保存，系统将基于当前估值数据自动计算安全边际结论并写入记录。
        </div>
        <span style="color:#f53f3f; font-size:12px;" v-if="modalError">{{ modalError }}</span>
      </div>
      <template #footer>
        <a-button @click="modalVisible = false">取消</a-button>
        <a-button type="primary" :loading="modalLoading" @click="submitEval">保存评估</a-button>
      </template>
    </a-modal>
  </div>
</template>
