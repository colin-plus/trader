<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import menus from '../menus.js'
import AppHeader from './AppHeader.vue'

const route = useRoute()
const router = useRouter()

// 折叠状态：localStorage 持久化（刷新保持用户偏好）
const COLLAPSED_KEY = 'tidescope.sidebar.collapsed'
const collapsed = ref(localStorage.getItem(COLLAPSED_KEY) === '1')
watch(collapsed, (v) => localStorage.setItem(COLLAPSED_KEY, v ? '1' : '0'))

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
      <!-- 顶部标题：展开=[观澜 TideScope 文字]，收起=[仅居中澜徽标] -->
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
        <span
          v-if="collapsed"
          style="
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 24px;
            height: 24px;
            border-radius: 6px;
            background: var(--color-primary-light-4);
            color: var(--color-white);
            font-size: 14px;
            font-weight: 600;
            flex-shrink: 0;
          "
        >澜</span>
        <span v-if="!collapsed" style="font-size:15px; font-weight:600; white-space:nowrap;">观澜 TideScope</span>
      </div>

      <!-- 菜单：宽度跟随 aside -->
      <a-menu
        :style="{ flex: 1, overflow: 'auto', overflowX: 'hidden' }"
        :collapsed="collapsed"
        :selected-keys="selectedKeys"
        v-model:open-keys="openKeys"
        @menu-item-click="handleMenuClick"
        :tooltip-props="{ disabled: true }"
      >
        <template v-for="item in menus" :key="item.path">
          <!-- 有子菜单 -->
          <a-sub-menu v-if="item.children" :key="item.path" :key-property="item.path">
            <template #title>
              <component :is="item.icon" :size="16" style="vertical-align: middle;" />
              <span v-if="!collapsed" style="margin-left:8px;">{{ item.title }}</span>
            </template>
            <a-menu-item v-for="child in item.children" :key="child.path">
              <span style="margin-left:8px;">{{ child.title }}</span>
            </a-menu-item>
          </a-sub-menu>

          <!-- 无子菜单 -->
          <a-menu-item v-else :key="item.path">
            <component :is="item.icon" :size="16" style="vertical-align: middle;" />
            <span v-if="!collapsed" style="margin-left:8px;">{{ item.title }}</span>
          </a-menu-item>
        </template>
      </a-menu>

      <!-- 侧边栏底部折叠按钮已移至 Header（见 AppHeader.vue） -->
    </aside>

    <!-- 右侧：Header + 内容区（纵向堆叠） -->
    <main style="flex:1; display:flex; flexDirection:column; overflow:hidden;">
      <AppHeader :collapsed="collapsed" @toggle="collapsed = !collapsed" />
      <div style="flex:1; overflow-y:auto; padding:20px 24px;">
        <router-view />
      </div>
    </main>
  </div>
</template>
