<script setup>
import { useRouter } from 'vue-router'
import { ChartCandlestick, Star, BarChart3, Coins, Wallet, Clock, Database, Settings, ArrowRight } from 'lucide-vue-next'
import menus from '../menus.js'

const router = useRouter()

// 快捷入口：从 menus.js 展平叶子菜单（单一数据源，新增页面自动出现）
// 图标显式映射：menus 里只有叶子项有 icon，这里直接用
const entries = []
for (const group of menus) {
  if (group.children) {
    for (const child of group.children) {
      entries.push({ title: child.title, path: child.path, icon: child.icon })
    }
  } else {
    entries.push({ title: group.title, path: group.path, icon: group.icon })
  }
}

function go(path) {
  router.push(path)
}
</script>

<template>
  <div>
    <!-- 欢迎卡片 -->
    <div
      style="
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 28px 32px;
        border-radius: 12px;
        background: linear-gradient(120deg, rgba(34, 211, 238, 0.08), rgba(167, 139, 250, 0.08));
        border: 1px solid var(--color-border-2);
        margin-bottom: 20px;
      "
    >
      <div>
        <div style="font-size: 22px; font-weight: 700; margin-bottom: 8px;">👋 欢迎回来</div>
        <div style="font-size: 14px; color: var(--color-text-3);">
          观澜 TideScope · 交易数据分析工作台。数据每日盘后自动更新，行情与研究一目了然。
        </div>
      </div>
      <span style="font-size: 40px; opacity: 0.6;">🌊</span>
    </div>

    <!-- 快捷入口 -->
    <div style="font-size: 14px; font-weight: 600; margin: 4px 2px 12px;">快捷入口</div>
    <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px;">
      <div
        v-for="e in entries"
        :key="e.path"
        @click="go(e.path)"
        style="
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 16px 18px;
          border-radius: 10px;
          border: 1px solid var(--color-border-2);
          background: var(--color-bg-2);
          cursor: pointer;
          transition: border-color .15s ease, transform .15s ease;
        "
        @mouseenter="$event.currentTarget.style.borderColor = 'var(--color-primary-4)'"
        @mouseleave="$event.currentTarget.style.borderColor = 'var(--color-border-2)'"
      >
        <span
          style="
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 36px;
            height: 36px;
            border-radius: 8px;
            background: var(--color-primary-light-4);
            color: var(--color-primary-6);
            flex-shrink: 0;
          "
        >
          <component :is="e.icon" :size="18" />
        </span>
        <span style="flex: 1; font-size: 14px; font-weight: 500;">{{ e.title }}</span>
        <arrow-right :size="14" style="color: var(--color-text-4);" />
      </div>
    </div>
  </div>
</template>
