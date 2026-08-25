<script setup>
import { ref, onMounted, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({ data: { type: Array, required: true } })
const el = ref(null)
let chart = null

function render() {
  if (!chart) return
  const dates = props.data.map(d => d.date)
  const kdata = props.data.map(d => [d.open, d.close, d.low, d.high])
  const vols = props.data.map(d => d.volume)

  // 均线
  function ma(n) {
    return props.data.map((_, i) => {
      if (i < n - 1) return '-'
      const s = props.data.slice(i - n + 1, i + 1).reduce((a, b) => a + b.close, 0)
      return +(s / n).toFixed(2)
    })
  }

  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { data: ['MA5', 'MA10', 'MA20'], textStyle: { color: '#8b98a9' }, top: 0 },
    grid: [
      { left: 60, right: 20, top: 30, height: '55%' },
      { left: 60, right: 20, top: '72%', height: '18%' },
    ],
    xAxis: [
      { type: 'category', data: dates, boundaryGap: true, axisLine: { lineStyle: { color: '#2a3441' } }, axisLabel: { color: '#8b98a9' } },
      { type: 'category', data: dates, gridIndex: 1, axisLabel: { show: false }, axisLine: { lineStyle: { color: '#2a3441' } } },
    ],
    yAxis: [
      { scale: true, splitLine: { lineStyle: { color: '#20262e' } }, axisLabel: { color: '#8b98a9' } },
      { gridIndex: 1, splitLine: { show: false }, axisLabel: { show: false } },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: 60, end: 100 },
      { type: 'slider', xAxisIndex: [0, 1], bottom: 0, height: 18, borderColor: '#2a3441', textStyle: { color: '#8b98a9' } },
    ],
    series: [
      {
        name: 'K线', type: 'candlestick', data: kdata,
        itemStyle: {
          color: '#ef4444', color0: '#22c55e',
          borderColor: '#ef4444', borderColor0: '#22c55e',
        },
      },
      { name: 'MA5', type: 'line', data: ma(5), smooth: true, showSymbol: false, lineStyle: { width: 1, color: '#f59e0b' } },
      { name: 'MA10', type: 'line', data: ma(10), smooth: true, showSymbol: false, lineStyle: { width: 1, color: '#4f8cff' } },
      { name: 'MA20', type: 'line', data: ma(20), smooth: true, showSymbol: false, lineStyle: { width: 1, color: '#a855f7' } },
      {
        name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: vols,
        itemStyle: { color: (p) => props.data[p.dataIndex].close >= props.data[p.dataIndex].open ? '#ef444488' : '#22c55e88' },
      },
    ],
  }, true)
}

onMounted(() => {
  chart = echarts.init(el.value)
  render()
  window.addEventListener('resize', () => chart && chart.resize())
})

watch(() => props.data, render, { deep: true })
</script>

<template>
  <div ref="el" style="width: 100%; height: 420px;"></div>
</template>
