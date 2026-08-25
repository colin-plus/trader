<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import menus from '../menus.js'

const route = useRoute()
const router = useRouter()
const collapsed = ref(false)

// 当前选中菜单（与路由同步）
const selectedKeys = computed(() => [route.path])

// 展开的顶级菜单组：路由变化时自动展开所属组
const openKeys = ref([])
watch(
  () => route.path,
  (path) => {
    const group = menus.find(item =>
      item.children && item.children.some(c => path.startsWith(c.path))
    )
    if (group && !openKeys.value.includes(group.path)) {
      openKeys.value = [...openKeys.value, group.path]
    }
  },
  { immediate: true }
)

// 菜单点击 → 路由跳转（子菜单由 a-menu 自动处理，这里处理叶子项）
function handleMenuClick(key) {
  if (key && key.startsWith('/')) router.push(key)
}
</script>

<template>
  <div style="display:flex; height:100vh; overflow:hidden;">
    <!-- 侧边栏：宽度由 collapsed 决定，48px/200px 固定 -->
    <aside
      :style="{
        display: 'flex',
        flexDirection: 'column',
        flexShrink: 0,
        width: collapsed ? '48px' : '200px',
        background: 'var(--color-bg-2)',
        borderRight: '1px solid var(--color-border-2)',
        transition: 'width .18s ease',
        overflow: 'hidden',
      }"
    >
      <!-- 顶部标题：展开=[Logo+文字]，收起=[仅居中Logo] -->
      <div
        :style="{
          display: 'flex',
          alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'flex-start',
          gap: '8px',
          padding: collapsed ? '14px 0' : '14px 16px',
          borderBottom: '1px solid var(--color-border-2)',
          flexShrink: 0,
        }"
      >
        <span style="font-size:20px;">📈</span>
        <span v-if="!collapsed" style="font-size:15px; font-weight:600; white-space:nowrap;">Trader Data</span>
      </div>

      <!-- 菜单：宽度跟随 aside -->
      <a-menu
        :style="{ flex: 1, overflow: 'auto', overflowX: 'hidden' }"
        :collapsed="collapsed"
        :selected-keys="selectedKeys"
        v-model:open-keys="openKeys"
        @menu-item-click="handleMenuClick"
      >
        <template v-for="item in menus" :key="item.path">
          <!-- 有子菜单 -->
          <a-sub-menu v-if="item.children" :key="item.path" :key-property="item.path">
            <template #title>
              <span>{{ item.icon }}</span>
              <span v-if="!collapsed" style="margin-left:8px;">{{ item.title }}</span>
            </template>
            <a-menu-item v-for="child in item.children" :key="child.path">
              <span style="margin-left:8px;">{{ child.title }}</span>
            </a-menu-item>
          </a-sub-menu>

          <!-- 无子菜单 -->
          <a-menu-item v-else :key="item.path">
            <span>{{ item.icon }}</span>
            <span v-if="!collapsed" style="margin-left:8px;">{{ item.title }}</span>
          </a-menu-item>
        </template>
      </a-menu>

      <!-- 底部：展开=[信息+收起按钮]，收起=[居中展开按钮] -->
      <div
        :style="{
          borderTop: '1px solid var(--color-border-2)',
          padding: collapsed ? '8px 0' : '8px 10px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '6px',
          flexShrink: 0,
        }"
      >
        <div v-if="!collapsed" style="font-size:11px; color:var(--color-text-4); white-space:nowrap;">
          数据仓库 · duckdb
        </div>
        <a-tooltip :content="collapsed ? '展开菜单' : '收起菜单'" position="right">
          <a-button
            size="mini"
            shape="circle"
            @click="collapsed = !collapsed"
            style="border: 1px solid var(--color-border-3); color: var(--color-text-2);"
          >
            <icon-menu-unfold v-if="collapsed" />
            <icon-menu-fold v-else />
          </a-button>
        </a-tooltip>
      </div>
    </aside>

    <!-- 内容区 -->
    <main style="flex:1; overflow-y:auto; padding:20px 24px;">
      <router-view />
    </main>
  </div>
</template>
