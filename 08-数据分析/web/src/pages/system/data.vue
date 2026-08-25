<script setup>
import { ref, onMounted } from 'vue'

const meta = ref(null)
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const r = await fetch('/api/meta')
    meta.value = await r.json()
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
      <h2 style="font-size:16px; margin:0;">数据管理</h2>
      <a-spin v-if="loading" size="small" />
      <span style="color:#f53f3f; font-size:13px;" v-if="error">{{ error }}</span>
    </div>
    <a-card :bordered="true" style="border-radius:8px;">
      <a-descriptions title="数据库概览" :column="2" bordered size="small">
        <a-descriptions-item label="数据表">
          {{ meta?.meta?.length ? '7 张表（investable_asset / daily_kline / volume_profile / daily_capital_flow / finance / watchlist / meta）' : '—' }}
        </a-descriptions-item>
        <a-descriptions-item label="最后更新">
          {{ meta?.meta?.find(m => m.key === 'updated_at')?.value || '—' }}
        </a-descriptions-item>
      </a-descriptions>
      <div style="margin-top:16px; color:var(--color-text-4); font-size:13px;">
        表数据量明细、导入/更新操作（开发中）
      </div>
    </a-card>
  </div>
</template>
