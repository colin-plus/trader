<script setup>
import { ref, onMounted, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({ data: { type: Array, required: true } })
const el = ref(null)
let chart = null

function render() {
  if (!chart) return
  // 按日期聚合：每日一个价格区间柱（横条），宽度=手数
  const byDate = {}
  for (const r of props.data) {
    if (!byDate[r.date]) byDate[r.date] = []
    byDate[r.date].push(r)
  }
  const dates = Object.keys(byDate).sort()
  // 转成横向条形：每行一天，x=价格，长度=手数占比
  const series = []
  dates.forEach((d, i) => {
    const rows = byDate[d]
    const max = Math.max(...rows.map(r => r.vol))
    series.push({
      type: 'bar',
      data: rows.map(r => ({
        value: r.price,
        itemStyle: {
          color: r.buy + r.sell > 0
            ? (r.buy >= r.sell ? '#ef4444aa' : '#22c55eaa')
            : '#4f8cff66',
        },
        name: `${d} ${r.price.toFixed(2)}  ${(r.vol / 10000).toFixed(1)}万手${r.buy + r.sell > 0 ? `  买${r.buy} 卖${r.sell}` : ''}`,
      })),
      barWidth: 6,
      barGap: '20%',
      xAxisIndex: 0,
      yAxisIndex: i,
    })
  })

  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item', formatter: (p) => p.name },
    grid: { left: 10, right: 70, top: 10, bottom: 10, containLabel: true },
    xAxis: {
      type: 'value',
      scale: true,
      axisLabel: { color: '#8b98a9' },
      splitLine: { lineStyle: { color: '#20262e' } },
    },
    yAxis: dates.map(d => ({
      type: 'category',
      data: [d.slice(5)],
      axisLabel: { color: '#8b98a9', fontSize: 10 },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: false },
    })),
    series,
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
  <div ref="el" style="width: 100%; height: 380px;"></div>
</template>
