<script setup>
// 突破确认（唐奇安通道 + 三道防火墙）
// 扫描接口：GET /api/breakout/scan  个股详情：GET /api/breakout/{code}  元信息：GET /api/breakout/meta
// 参数默认值与会话约定：n=60, vbase=20, m=1, mode=atr, k=1.0, theta=0.03, rmin=1.5, rmax=3.0, max_elapsed=10, min_pass=3
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { RotateCcw, Search } from 'lucide-vue-next'
import BreakoutChart from '../../components/BreakoutChart.vue'

const route = useRoute()
const router = useRouter()

// 视频默认参数（一键重置）。min_pass = 至少满足几道防火墙（3=视频口径）
const DEFAULTS = { n: 60, vbase: 20, m: 1, mode: 'atr', k: 1.0, theta: 0.03, rmin: 1.5, rmax: 3.0, max_elapsed: 10, min_pass: 3, run_preset: 'any', ago_min: 0, ago_max: 3 }

// 突破距今（run_pos = 自突破日起的交易日数，含突破当日）
//   run_pos=1 → 当日突破；run_pos<=N → "N 日内突破"；run_pos=N+1 → N 天前
// 主用法是"N 日内"（累计），"仅某一天"用于精确定位。
const RUN_PRESETS = [
  { label: '不限（全部追踪窗口）', value: 'any' },
  { label: '当日突破', value: 'w1', min: 1, max: 1 },
  { label: '2 日内（今天或昨天）', value: 'w2', min: 1, max: 2 },
  { label: '3 日内', value: 'w3', min: 1, max: 3 },
  { label: '4 日内', value: 'w4', min: 1, max: 4 },
  { label: '5 日内', value: 'w5', min: 1, max: 5 },
  { label: '7 日内', value: 'w7', min: 1, max: 7 },
  { label: '10 日内', value: 'w10', min: 1, max: 10 },
  { label: '仅 昨天（第 2 个交易日）', value: 'e2', min: 2, max: 2 },
  { label: '仅 2 天前', value: 'e3', min: 3, max: 3 },
  { label: '仅 3 天前', value: 'e4', min: 4, max: 4 },
  { label: '自定义区间', value: 'custom' },
]

const p = reactive({ ...DEFAULTS })
const scanDate = ref('')          // '' = 交给后端取最新交易日
const effectiveDate = ref('')     // 后端返回的实际扫描日
const meta = ref(null)
const count = ref(0)
const rows = ref([])
const loading = ref(false)
const error = ref('')

const detail = ref(null)
const detailLoading = ref(false)
const detailError = ref('')
const selectedCode = ref('')
const detailVisible = ref(false)   // 证据面板改为近全屏弹窗

// 弹窗内上/下一只（便于逐个翻看命中列表，不必滚回表格再点）
const curIndex = computed(() => rows.value.findIndex((r) => r.code === selectedCode.value))

const modeOptions = [
  { label: 'ATR倍数', value: 'atr' },
  { label: '百分比', value: 'abs' },
  { label: '两者同时', value: 'both' },
]

const runOptions = RUN_PRESETS.map((x) => ({ label: x.label, value: x.value }))

const advancedVisible = ref(false)
let timer = null

function runBounds() {
  // 把「突破距今」预设换算成后端要的 run_min / run_max（run_pos 口径）
  if (p.run_preset === 'any') return [1, p.max_elapsed]
  if (p.run_preset === 'custom') {
    const a = Math.max(0, Number(p.ago_min) || 0)
    const b = Math.max(a, Number(p.ago_max) || 0)
    return [Math.min(a + 1, p.max_elapsed), Math.min(b + 1, p.max_elapsed)]
  }
  const pz = RUN_PRESETS.find((x) => x.value === p.run_preset)
  return pz && pz.min ? [pz.min, Math.min(pz.max, p.max_elapsed)] : [1, p.max_elapsed]
}

function qs() {
  const q = new URLSearchParams()
  if (scanDate.value) q.set('date', scanDate.value)
  q.set('n', p.n)
  q.set('vbase', p.vbase)
  q.set('m', p.m)
  q.set('mode', p.mode)
  q.set('k', p.k)
  q.set('theta', p.theta)
  q.set('rmin', p.rmin)
  q.set('rmax', p.rmax)
  q.set('max_elapsed', p.max_elapsed)
  q.set('min_pass', p.min_pass)
  const [rmin, rmax] = runBounds()
  q.set('run_min', rmin)
  q.set('run_max', rmax)
  q.set('limit', 200)
  return q.toString()
}

async function loadMeta() {
  try {
    const r = await fetch('/api/breakout/meta')
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    meta.value = await r.json()
  } catch (e) {
    meta.value = null   // 元信息不可用不阻塞扫描
  }
}

async function loadScan() {
  loading.value = true
  error.value = ''
  try {
    const r = await fetch(`/api/breakout/scan?${qs()}`)
    if (!r.ok) {
      const err = await r.json().catch(() => ({}))
      throw new Error(err.detail || `HTTP ${r.status}`)
    }
    const d = await r.json()
    rows.value = (d.rows || []).map((x, i) => ({ key: `${x.code}-${i}`, ...x }))
    count.value = d.count === undefined || d.count === null ? rows.value.length : d.count
    effectiveDate.value = d.date || ''
    // 首次进入 / 后端回填交易日 → 同步到日期选择器
    if (!scanDate.value && d.date) scanDate.value = d.date
  } catch (e) {
    rows.value = []
    count.value = 0
    error.value = `扫描失败: ${e.message}`
    Message.error(`突破扫描失败: ${e.message}`)
  } finally {
    loading.value = false
  }
}

// 任一参数变化 → 防抖后自动查询（日期选择器变化即时触发）
watch(
  () => [scanDate.value, p.n, p.vbase, p.m, p.mode, p.k, p.theta, p.rmin, p.rmax, p.max_elapsed, p.min_pass,
         p.run_preset, p.ago_min, p.ago_max],
  () => {
    clearTimeout(timer)
    timer = setTimeout(loadScan, 300)
  }
)

function resetParams() {
  Object.assign(p, DEFAULTS)
  Message.info('已重置为默认参数')
}

async function loadDetail(code) {
  detailLoading.value = true
  detailError.value = ''
  try {
    const q = new URLSearchParams({ days: 120, n: p.n, vbase: p.vbase, m: p.m })
    const r = await fetch(`/api/breakout/${code}?${q.toString()}`)
    if (!r.ok) {
      const err = await r.json().catch(() => ({}))
      throw new Error(err.detail || `HTTP ${r.status}`)
    }
    detail.value = await r.json()
  } catch (e) {
    detail.value = null
    detailError.value = `详情加载失败: ${e.message}`
    Message.error(`个股详情加载失败: ${e.message}`)
  } finally {
    detailLoading.value = false
  }
}

function onRowClick(record) {
  selectedCode.value = record.code
  detailVisible.value = true
  router.replace({ path: route.path, query: { code: record.code } })
  loadDetail(record.code)
}

function step(delta) {
  const i = curIndex.value
  const j = i + delta
  if (i < 0 || j < 0 || j >= rows.value.length) return
  onRowClick(rows.value[j])
}

function closeDetail() {
  detailVisible.value = false
  // 保留 detail 数据，让关闭动画期间内容不闪空；下次点击会覆盖
  router.replace({ path: route.path })
}

// 弹窗打开时用 ←/→ 翻看上一只/下一只（输入框内不拦截）
function onKeydown(e) {
  if (!detailVisible.value) return
  const t = e.target
  if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT')) return
  if (e.key === 'ArrowLeft') { e.preventDefault(); step(-1) }
  else if (e.key === 'ArrowRight') { e.preventDefault(); step(1) }
}

onMounted(async () => {
  window.addEventListener('keydown', onKeydown)
  await loadMeta()
  // URL 直达（如 /market/breakout?code=600105）
  const codeParam = route.query.code
  if (codeParam) {
    selectedCode.value = String(codeParam)
    detailVisible.value = true
    loadDetail(selectedCode.value)
  }
  await loadScan()
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  clearTimeout(timer)
})

// ---- 展示格式化（null 一律安全显示为 —）----
function fmt(v, digits = 2) {
  return v === null || v === undefined ? '—' : Number(v).toFixed(digits)
}
function fmtPct(v, digits = 2) {
  return v === null || v === undefined ? '—' : `${(Number(v) * 100).toFixed(digits)}%`
}
// run_pos(自突破日交易日数，含当日) → 人话：今天 / 昨天 / N 天前
function agoText(runPos) {
  if (runPos === null || runPos === undefined || runPos < 1) return '—'
  const d = runPos - 1
  if (d === 0) return '今天'
  if (d === 1) return '昨天'
  return `${d} 天前`
}
function agoColor(runPos) {
  if (!runPos) return 'var(--color-text-3)'
  return runPos <= 3 ? '#f53f3f' : 'inherit'
}
function passTag(ok) {
  return ok
    ? { text: '✓', color: 'green' }
    : { text: '✗', color: 'red' }
}
function mainColor(record) {
  return record.passed ? 'green' : 'orange'
}

const summary = computed(() => {
  const modeText = { atr: 'ATR倍数', abs: '百分比', both: '两者同时' }[p.mode] || p.mode
  const pz = RUN_PRESETS.find((x) => x.value === p.run_preset)
  const [rmin, rmax] = runBounds()
  const runText = p.run_preset === 'custom'
    ? `距今${rmin - 1}~${rmax - 1}个交易日`
    : (pz ? pz.label : `距今${rmin - 1}~${rmax - 1}个交易日`)
  return `扫描日 ${effectiveDate.value || scanDate.value || '最新交易日'} · 突破${runText} · 至少满足 ${p.min_pass} 道门槛 · N=${p.n} · 量能基准=${p.vbase} · m=${p.m} · 模式=${modeText} · k=${p.k} · theta=${p.theta} · R∈[${p.rmin}, ${p.rmax}] · 最长追踪=${p.max_elapsed} 日`
})
</script>

<template>
  <div>
    <!-- 标题 + 参数条 -->
    <div style="display:flex; align-items:center; gap:12px; margin-bottom:16px; flex-wrap:wrap;">
      <h2 style="font-size:16px; margin:0;">突破确认</h2>
      <a-date-picker
        v-model="scanDate"
        value-format="YYYY-MM-DD"
        :style="{ width: '160px' }"
        placeholder="最新交易日"
        allow-clear
      />
      <span class="muted" style="font-size:13px; margin-left:4px;">突破距今</span>
      <a-select v-model="p.run_preset" :options="runOptions" size="small" :style="{ width: '190px' }" />
      <template v-if="p.run_preset === 'custom'">
        <a-input-number v-model="p.ago_min" :min="0" :max="60" size="small" :style="{ width: '78px' }" />
        <span class="muted" style="font-size:13px;">~</span>
        <a-input-number v-model="p.ago_max" :min="0" :max="60" size="small" :style="{ width: '78px' }" />
        <span class="muted" style="font-size:13px;">个交易日前（0=今天）</span>
      </template>
      <span class="muted" style="font-size:13px; margin-left:4px;">至少满足</span>
      <a-radio-group v-model="p.min_pass" type="button" size="small">
        <a-radio :value="3">3 道</a-radio>
        <a-radio :value="2">2 道</a-radio>
        <a-radio :value="1">1 道</a-radio>
      </a-radio-group>
      <a-button size="small" @click="advancedVisible = !advancedVisible">
        {{ advancedVisible ? '收起高级参数' : '高级参数' }}
      </a-button>
      <a-button size="small" @click="resetParams">
        <template #icon><rotate-ccw :size="14" /></template>
        重置参数
      </a-button>
      <a-button type="primary" size="small" :loading="loading" @click="loadScan">
        <template #icon><search :size="14" /></template>
        查询
      </a-button>
      <a-spin v-if="loading" size="small" />
      <span style="color:#f53f3f; font-size:13px;" v-if="error">{{ error }}</span>
      <div style="flex:1;"></div>
      <span class="muted" v-if="meta && meta.updated_at">
        数据更新至 {{ meta.updated_at }}<template v-if="meta.date_max">（最新交易日 {{ meta.date_max }}）</template>
      </span>
    </div>

    <!-- 高级参数 -->
    <a-card v-if="advancedVisible" :bordered="true" style="border-radius:8px; margin-bottom:16px;">
      <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(180px, 1fr)); gap:14px 18px;">
        <div>
          <div class="muted" style="margin-bottom:4px;">唐奇安回看天数 N</div>
          <a-input-number v-model="p.n" :min="5" :max="250" :step="5" style="width:100%;" />
        </div>
        <div>
          <div class="muted" style="margin-bottom:4px;">量能基准天数 vbase</div>
          <a-input-number v-model="p.vbase" :min="3" :max="120" :step="1" style="width:100%;" />
        </div>
        <div>
          <div class="muted" style="margin-bottom:4px;">额外确认天数 m</div>
          <a-input-number v-model="p.m" :min="0" :max="10" :step="1" style="width:100%;" />
        </div>
        <div>
          <div class="muted" style="margin-bottom:4px;">判定模式</div>
          <a-select v-model="p.mode" :options="modeOptions" style="width:100%;" />
        </div>
        <div>
          <div class="muted" style="margin-bottom:4px;">ATR 倍数阈值 k</div>
          <a-input-number v-model="p.k" :min="0" :max="10" :step="0.1" style="width:100%;" />
        </div>
        <div>
          <div class="muted" style="margin-bottom:4px;">百分比阈值 theta</div>
          <a-input-number v-model="p.theta" :min="0" :max="1" :step="0.005" style="width:100%;" />
        </div>
        <div>
          <div class="muted" style="margin-bottom:4px;">量能倍数下限 R min</div>
          <a-input-number v-model="p.rmin" :min="0" :max="20" :step="0.1" style="width:100%;" />
        </div>
        <div>
          <div class="muted" style="margin-bottom:4px;">量能倍数上限 R max</div>
          <a-input-number v-model="p.rmax" :min="0" :max="50" :step="0.1" style="width:100%;" />
        </div>
        <div>
          <div class="muted" style="margin-bottom:4px;">最长追踪天数 max_elapsed</div>
          <a-input-number v-model="p.max_elapsed" :min="1" :max="60" :step="1" style="width:100%;" />
        </div>
      </div>
    </a-card>

    <!-- 参数摘要 -->
    <div class="muted" style="margin-bottom:10px;">
      命中 <b style="color:var(--color-text-1);">{{ count }}</b> 只 · {{ summary }}
    </div>

    <!-- 扫描结果表 -->
    <a-card :bordered="true" style="border-radius:8px;">
      <a-table
        :data="rows"
        :loading="loading"
        :pagination="false"
        :bordered="true"
        size="small"
        :scroll="{ x: 'max-content' }"
        :row-class="(record) => (record.passed ? '' : 'breakout-row-muted')"
        @row-click="onRowClick"
      >
        <template #columns>
          <a-table-column title="代码" data-index="code" :width="90" />
          <a-table-column title="名称" data-index="name" :width="110" />
          <a-table-column title="最新收盘" :width="100" align="right">
            <template #cell="{ record }">{{ fmt(record.close) }}</template>
          </a-table-column>
          <a-table-column title="突破距今" :width="120" align="center">
            <template #cell="{ record }">
              <a-tooltip mini :content="`突破日 ${record.run_start_date || '—'} · 自突破已站稳 ${record.run_pos ?? '—'} 个交易日`">
                <span :style="{ color: agoColor(record.run_pos), fontWeight: record.run_pos <= 3 ? 600 : 400 }">
                  {{ agoText(record.run_pos) }}
                </span>
              </a-tooltip>
            </template>
          </a-table-column>
          <a-table-column title="突破日幅度/波动" :width="160" align="right">
            <template #cell="{ record }">
              <span :style="{ color: record.a_pct >= 0 ? '#f53f3f' : '#00b42a' }">{{ fmtPct(record.a_pct) }}</span>
              <span class="muted"> / {{ record.z_atr === null || record.z_atr === undefined ? '—' : `${fmt(record.z_atr)}×ATR` }}</span>
            </template>
          </a-table-column>
          <a-table-column title="突破日量能倍数" :width="140" align="right">
            <template #cell="{ record }">
              <span :style="{ color: record.r_vol !== null && record.r_vol >= 1.5 ? '#f53f3f' : 'inherit' }">{{ fmt(record.r_vol) }}</span>
            </template>
          </a-table-column>
          <a-table-column title="满足门槛" :width="90" align="center">
            <template #cell="{ record }">
              <a-tag :color="record.pass_count === 3 ? 'green' : record.pass_count === 2 ? 'orange' : 'gray'" size="small">
                {{ record.pass_count }}/3
              </a-tag>
            </template>
          </a-table-column>
          <a-table-column title="防火墙" :width="110" align="center">
            <template #cell="{ record }">
              <a-space :size="2">
                <a-tooltip content="幅度：穿透关键位是否达标" mini>
                  <a-tag :color="passTag(record.pass_amp).color" size="small" style="padding:0 5px;">{{ passTag(record.pass_amp).text }}</a-tag>
                </a-tooltip>
                <a-tooltip content="时间：突破后是否守住关键位" mini>
                  <a-tag :color="passTag(record.pass_time).color" size="small" style="padding:0 5px;">{{ passTag(record.pass_time).text }}</a-tag>
                </a-tooltip>
                <a-tooltip :content="record.is_limit_up
                  ? '量能：突破日涨停封板，成交天然偏小 → 已豁免放量要求'
                  : '量能：突破日是否放量（≥1.5 倍均量）'" mini>
                  <a-tag :color="passTag(record.pass_vol).color" size="small" style="padding:0 5px;">{{ passTag(record.pass_vol).text }}</a-tag>
                </a-tooltip>
              </a-space>
            </template>
          </a-table-column>
          <a-table-column title="结论" :width="80" align="center">
            <template #cell="{ record }">
              <a-tag :color="mainColor(record)" size="small">{{ record.passed ? '通过' : '观察' }}</a-tag>
            </template>
          </a-table-column>
        </template>
        <template #empty>
          <a-empty description="当前参数下没有符合条件的突破标的。可把「至少满足」调到 2 道看近似信号，或放宽 k / theta、缩短确认天数 m 后再试" />
        </template>
      </a-table>
      <div class="muted" style="margin-top:10px;">
        三道防火墙（<b>并列独立判定，与列出顺序无关</b>）：幅度 / 时间 / 量能（✓ 通过 / ✗ 未通过，悬停可看判定口径；<b>突破日涨停封板会豁免量能要求</b>）。「满足门槛」列为通过的道数（<b>3/3</b> = 三原则全满足，即视频口径；<b>2/3</b> = 近似信号，用它对比"差在哪一道"）。<b>点任一整行 → 近全屏弹窗查看该股证据</b>（弹窗内可用「↑ 上一只 / ↓ 下一只」按钮或键盘 ←/→ 逐个翻看，不必滚回表格；Esc 或点遮罩关闭）。
      </div>
    </a-card>

    <!-- 个股证据面板：近全屏弹窗（列表很长时不必滚到底部再滚回来） -->
    <a-modal
      v-model:visible="detailVisible"
      :width="'94%'"
      :top="'3vh'"
      :footer="false"
      :mask-closable="true"
      :esc-to-close="true"
      :body-style="{ padding: '8px 20px 16px' }"
      @cancel="closeDetail"
    >
      <template #title>
        <div style="display:flex; align-items:center; gap:10px; width:100%; padding-right:28px;">
          <span style="font-size:15px;">
            {{ detail ? `${detail.name || ''}（${detail.code || selectedCode}）` : selectedCode }} · 突破证据
          </span>
          <span v-if="curIndex >= 0" style="font-size:12px; color:var(--color-text-3);">
            第 {{ curIndex + 1 }} / {{ rows.length }} 只
          </span>
          <div style="flex:1;"></div>
          <a-button size="mini" :disabled="curIndex <= 0" @click="step(-1)">↑ 上一只</a-button>
          <a-button size="mini" :disabled="curIndex < 0 || curIndex >= rows.length - 1" @click="step(1)">↓ 下一只</a-button>
        </div>
      </template>

      <a-spin v-if="detailLoading" style="display:block; width:100%; min-height:240px; padding-top:80px;" />
      <div v-else-if="detailError" style="color:#f53f3f; font-size:13px; padding:24px 0;">{{ detailError }}</div>
      <BreakoutChart
        v-else-if="detail && detail.rows && detail.rows.length"
        :data="detail.rows"
        height="calc(100vh - 250px)"
      />
      <a-empty v-else description="该标的暂无可用行情数据" />
    </a-modal>
  </div>
</template>

<style scoped>
/* 未通过三道防火墙的行弱化，方便一眼扫过 */
:deep(.breakout-row-muted) td {
  opacity: 0.72;
}
:deep(.arco-table-tr) {
  cursor: pointer;
}
</style>
