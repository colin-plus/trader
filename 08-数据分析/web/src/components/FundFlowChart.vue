<script setup>
import { ref, onMounted, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({ data: { type: Array, required: true } })
const el = ref(null)
let chart = null

function render() {
  if (!chart) return
  const dates = props.data.map(d => d.date.slice(5))
  const zhuli = props.data.map(d => d.zhuli)
  const xd = props.data.map(d => d.xd) // 小单（散户）

  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { data: ['主力净流入', '散户(小单)净流入'], textStyle: { color: '#8b98a9' }, top: 0 },
    grid: { left: 55, right: 20, top: 30, bottom: 30 },
    xAxis: {
      type: 'category', data: dates,
      axisLabel: { color: '#8b98a9' },
      axisLine: { lineStyle: { color: '#2a3441' } },
    },
    yAxis: {
      type: 'value',
      name: '亿元',
      nameTextStyle: { color: '#8b98a9' },
      splitLine: { lineStyle: { color: '#20262e' } },
      axisLabel: { color: '#8b98a9' },
    },
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },
      { type: 'slider', bottom: 0, height: 16, borderColor: '#2a3441', textStyle: { color: '#8b98a9' } },
    ],
    series: [
      {
        name: '主力净流入', type: 'bar', data: zhuli,
        itemStyle: { color: (p) => p.value >= 0 ? '#ef4444' : '#22c55e' },
      },
      {
        name: '散户(小单)净流入', type: 'bar', data: xd,
        itemStyle: { color: (p) => p.value >= 0 ? '#ef444466' : '#22c55e66' },
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
  <div ref="el" style="width: 100%; height: 380px;"></div>
</template>
