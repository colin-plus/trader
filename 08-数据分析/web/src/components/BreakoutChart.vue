<script setup>
// 突破证据面板主图：K线 + 关键位/唐奇安上轨 + ATR 带 + 放量柱 + 突破日标记
// 用法：<BreakoutChart :data="detail.rows" />
// data 为 /api/breakout/{code} 返回的 rows（按日期升序）
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  data: { type: Array, required: true },
  // 图表高度（弹窗里传 'calc(100vh - 260px)' 撑满，内嵌时用默认值）
  height: { type: String, default: '460px' },
})

const el = ref(null)
let chart = null

// 安全取数：null/undefined → '-'（ECharts 断线）
function val(v) {
  return v === null || v === undefined ? '-' : v
}

function render() {
  if (!chart) return
  const rows = props.data || []
  const dates = rows.map(d => d.date)
  const kdata = rows.map(d => [d.open, d.close, d.low, d.high])
  const runLevel = rows.map(d => val(d.run_level))
  const resLevel = rows.map(d => val(d.res_level))
  const atrUp = rows.map(d => (d.close === null || d.close === undefined || d.atr === null || d.atr === undefined)
    ? '-' : +(d.close + d.atr).toFixed(2))
  const atrDown = rows.map(d => (d.close === null || d.close === undefined || d.atr === null || d.atr === undefined)
    ? '-' : +(d.close - d.atr).toFixed(2))

  // 成交量柱：r_vol ≥1.5 放量高亮；<1 缩量弱化
  const vols = rows.map(d => ({
    value: d.volume,
    itemStyle: { color: volColor(d) },
  }))

  // 突破日标记
  const marks = []
  rows.forEach((d, i) => {
    if (d.is_breakout_day) {
      marks.push({
        name: '突破',
        coord: [i, d.high],
        value: '突破',
        symbol: 'pin',
        symbolSize: 34,
        itemStyle: { color: '#f53f3f' },
        label: { color: '#fff', fontSize: 11, formatter: '突破' },
      })
    }
  })

  chart.setOption({
    backgroundColor: 'transparent',
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter: (ps) => {
        const p = ps.find(x => x.seriesName === 'K线')
        const i = (p || ps[0]).dataIndex
        const d = rows[i]
        if (!d) return ''
        const f = (v, n = 2) => (v === null || v === undefined ? '—' : Number(v).toFixed(n))
        const pct = (v) => (v === null || v === undefined ? '—' : `${(v * 100).toFixed(2)}%`)
        return [
          `<b>${d.date}</b>${d.state && d.state !== '无' ? ` · ${d.state}` : ''}`,
          `开 ${f(d.open)}　收 ${f(d.close)}`,
          `高 ${f(d.high)}　低 ${f(d.low)}`,
          `关键位 ${f(d.run_level)}　上轨 ${f(d.res_level)}`,
          `ATR ${f(d.atr)}（${pct(d.atr_pct)}）`,
          `穿透 ${pct(d.a_pct)}　z_atr ${f(d.z_atr)}`,
          `量比 r_vol ${f(d.r_vol)}　run_pos ${d.run_pos === null || d.run_pos === undefined ? '—' : d.run_pos}`,
        ].join('<br/>')
      },
    },
    legend: {
      data: ['K线', '关键位(被突破)', '唐奇安上轨'],
      textStyle: { color: '#8b98a9' },
      top: 0,
    },
    grid: [
      { left: 60, right: 20, top: 30, height: '52%' },
      { left: 60, right: 20, top: '74%', height: '16%' },
    ],
    xAxis: [
      { type: 'category', data: dates, boundaryGap: true, axisLine: { lineStyle: { color: '#2a3441' } }, axisLabel: { color: '#8b98a9' } },
      { type: 'category', data: dates, gridIndex: 1, axisLabel: { show: false }, axisLine: { lineStyle: { color: '#2a3441' } } },
    ],
    yAxis: [
      { scale: true, splitLine: { lineStyle: { color: '#20262e' } }, axisLabel: { color: '#8b98a9' } },
      { gridIndex: 1, splitLine: { show: false }, axisLabel: { color: '#8b98a9', formatter: (v) => fmtVol(v) } },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: 55, end: 100 },
      { type: 'slider', xAxisIndex: [0, 1], bottom: 0, height: 18, borderColor: '#2a3441', textStyle: { color: '#8b98a9' } },
    ],
    series: [
      {
        name: 'K线', type: 'candlestick', data: kdata, z: 3,
        itemStyle: {
          color: '#ef4444', color0: '#22c55e',
          borderColor: '#ef4444', borderColor0: '#22c55e',
        },
        markPoint: { data: marks, silent: true },
      },
      {
        name: 'ATR上沿', type: 'line', data: atrUp, showSymbol: false, silent: true, z: 1,
        lineStyle: { width: 1, color: '#8b98a955', type: 'dotted' },
        itemStyle: { color: '#8b98a955' },
      },
      {
        name: 'ATR下沿', type: 'line', data: atrDown, showSymbol: false, silent: true, z: 1,
        lineStyle: { width: 1, color: '#8b98a955', type: 'dotted' },
        itemStyle: { color: '#8b98a955' },
      },
      {
        name: '关键位(被突破)', type: 'line', data: runLevel, showSymbol: false, connectNulls: false, z: 4,
        lineStyle: { width: 2, color: '#f59e0b', type: 'dashed' },
        itemStyle: { color: '#f59e0b' },
      },
      {
        name: '唐奇安上轨', type: 'line', data: resLevel, showSymbol: false, connectNulls: false, z: 2,
        lineStyle: { width: 1, color: '#4f8cff', opacity: 0.7 },
        itemStyle: { color: '#4f8cff' },
      },
      {
        name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: vols,
        markLine: {
          silent: true,
          symbol: 'none',
          label: { formatter: 'r_vol 1.5', color: '#8b98a9', fontSize: 10, position: 'insideEndTop' },
          lineStyle: { color: '#f59e0b66', type: 'dashed', width: 1 },
          data: [{
            yAxis: baseVol() === null ? '-' : +(baseVol() * 1.5).toFixed(0),
          }],
        },
      },
    ],
  }, true)
}

// 用当日 r_vol 与量能基准推算的柱色：放量红、缩量灰
function volColor(d) {
  const up = d.close >= d.open
  const r = d.r_vol
  if (r === null || r === undefined) return up ? '#ef444466' : '#22c55e66'
  if (r >= 1.5) return up ? '#ef4444' : '#22c55e'
  if (r < 1) return up ? '#ef444433' : '#22c55e33'
  return up ? '#ef444488' : '#22c55e88'
}

// 量能基准（元→股近似不需要，这里仅用于 r_vol=1.5 参考线高度）
function baseVol() {
  const rows = props.data || []
  for (let i = rows.length - 1; i >= 0; i--) {
    const d = rows[i]
    if (d.volume && d.r_vol) return d.volume / d.r_vol
  }
  return null
}

function fmtVol(v) {
  const n = Number(v)
  if (!isFinite(n)) return ''
  if (n >= 1e8) return (n / 1e8).toFixed(1) + '亿'
  if (n >= 1e4) return (n / 1e4).toFixed(0) + '万'
  return String(n)
}

// 证据摘要：以最后一行为当前状态，run_* 取最近一次非空值
const summary = computed(() => {
  const rows = props.data || []
  const last = rows.length ? rows[rows.length - 1] : null
  let runPos = null
  let runLevel = null
  for (let i = rows.length - 1; i >= 0; i--) {
    if (runPos === null && rows[i].run_pos !== null && rows[i].run_pos !== undefined) runPos = rows[i].run_pos
    if (runLevel === null && rows[i].run_level !== null && rows[i].run_level !== undefined) runLevel = rows[i].run_level
    if (runPos !== null && runLevel !== null) break
  }
  return {
    state: last && last.state ? last.state : '无',
    runPos,
    runLevel,
    aPct: last ? last.a_pct : null,
    zAtr: last ? last.z_atr : null,
    rVol: last ? last.r_vol : null,
    limitUp: last ? last.limit_up : null,
    aPctOn: last ? last.is_breakout_day : false,
  }
})

function f2(v) {
  return v === null || v === undefined ? '—' : Number(v).toFixed(2)
}
function fp(v) {
  return v === null || v === undefined ? '—' : `${(v * 100).toFixed(2)}%`
}
function stateColor(s) {
  return { '突破日': 'red', '确认中': 'orange', '已确认': 'green', '失效': 'gray', '无': 'gray' }[s] || 'gray'
}

onMounted(() => {
  chart = echarts.init(el.value)
  render()
  window.addEventListener('resize', onResize)
  // 弹窗有入场动画，容器尺寸在动画结束后才稳定 → 补两次 resize
  setTimeout(onResize, 60)
  setTimeout(onResize, 260)
})

onUnmounted(() => {
  // 弹窗反复开合会不断新建实例，必须清理，否则泄漏 ECharts 实例与 resize 监听
  window.removeEventListener('resize', onResize)
  if (chart) {
    chart.dispose()
    chart = null
  }
})

function onResize() {
  if (chart) chart.resize()
}

watch(() => props.data, render, { deep: true })
</script>

<template>
  <div>
    <div ref="el" :style="{ width: '100%', height: props.height }"></div>

    <!-- 证据摘要 -->
    <div style="display:flex; flex-wrap:wrap; align-items:center; gap:8px 20px; margin-top:12px; padding-top:12px; border-top:1px solid var(--color-border-2); font-size:13px; color:var(--color-text-3);">
      <span>状态
        <a-tag :color="stateColor(summary.state)" size="small" style="margin-left:4px;">{{ summary.state }}</a-tag>
      </span>
      <span>已确认天数 <b style="color:var(--color-text-1);">{{ summary.runPos === null ? '—' : summary.runPos }}</b></span>
      <span>关键位 run_level <b style="color:#f59e0b;">{{ f2(summary.runLevel) }}</b></span>
      <span>幅度 a_pct <b :style="{ color: summary.aPctOn ? '#f53f3f' : 'var(--color-text-1)' }">{{ summary.aPctOn ? fp(summary.aPct) : '—' }}</b></span>
      <span>波动倍数 z_atr <b style="color:var(--color-text-1);">{{ summary.aPctOn ? f2(summary.zAtr) : '—' }}</b></span>
      <span>量能倍数 r_vol
        <b :style="{ color: summary.rVol !== null && summary.rVol >= 1.5 ? '#f53f3f' : 'var(--color-text-1)' }">
          {{ summary.rVol === null || summary.rVol === undefined ? '—' : f2(summary.rVol) }}
        </b>
      </span>
      <span>涨停
        <b :style="{ color: summary.limitUp ? '#f53f3f' : 'var(--color-text-3)' }">{{ summary.limitUp ? '是' : '否' }}</b>
      </span>
    </div>
  </div>
</template>
