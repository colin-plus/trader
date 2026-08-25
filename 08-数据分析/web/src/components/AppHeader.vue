<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PanelLeftClose, PanelLeftOpen } from 'lucide-vue-next'
import { getBreadcrumb } from '../utils/breadcrumb.js'

const props = defineProps({
  collapsed: Boolean,
})
const emit = defineEmits(['toggle'])

const route = useRoute()
const router = useRouter()

// 面包屑：首页 / 顶级组 / 当前页（随路由自动推导）
const crumbs = computed(() => getBreadcrumb(route.path))

function go(path) {
  router.push(path)
}
</script>

<template>
  <header
    style="
      display: flex;
      align-items: center;
      height: 48px;
      padding: 0 16px;
      gap: 12px;
      background: var(--color-bg-2);
      border-bottom: 1px solid var(--color-border-2);
      flex-shrink: 0;
    "
  >
    <!-- 左：展开/收起侧边栏 -->
    <a-button
      type="text"
      size="small"
      :aria-label="collapsed ? '展开侧边栏' : '收起侧边栏'"
      @click="emit('toggle')"
    >
      <panel-left-open v-if="collapsed" :size="18" />
      <panel-left-close v-else :size="18" />
    </a-button>

    <!-- 中：面包屑 -->
    <a-breadcrumb>
      <a-breadcrumb-item v-for="(c, i) in crumbs" :key="c.path + '-' + i">
        <a-link v-if="i < crumbs.length - 1" @click="go(c.path)">{{ c.title }}</a-link>
        <template v-else>{{ c.title }}</template>
      </a-breadcrumb-item>
    </a-breadcrumb>

    <div style="flex: 1"></div>

    <!-- 右：预留区（全局信息 / 加载状态 / 通知等，后续扩展） -->
    <span style="font-size: 12px; color: var(--color-text-3); user-select: none;">v0.1</span>
  </header>
</template>
