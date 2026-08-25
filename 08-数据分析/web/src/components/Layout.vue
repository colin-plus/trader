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
    <!-- 侧边栏（Arco Menu） -->
    <aside style="display:flex; flex-direction:column; flex-shrink:0; background:var(--color-bg-2); border-right:1px solid var(--color-border-2);">
      <!-- 顶部标题 + 折叠按钮 -->
      <div style="display:flex; align-items:center; gap:8px; padding:14px 16px; border-bottom:1px solid var(--color-border-2);">
        <span style="font-size:20px;">📈</span>
        <span v-if="!collapsed" style="font-size:15px; font-weight:600; flex:1; white-space:nowrap;">Trader Data</span>
        <a-button
          size="mini"
          shape="circle"
          :style="{ border: 'none', background: 'transparent', color: 'var(--color-text-3)' }"
          @click="collapsed = !collapsed"
        >
          <icon-menu-unfold v-if="collapsed" />
          <icon-menu-fold v-else />
        </a-button>
      </div>

      <!-- 菜单 -->
      <a-menu
        :style="{ width: collapsed ? '48px' : '200px', height: 'calc(100vh - 53px)', overflow: 'auto', transition: 'width .18s ease' }"
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

      <!-- 底部 -->
      <div v-if="!collapsed" style="padding:10px 16px; border-top:1px solid var(--color-border-2); font-size:11px; color:var(--color-text-4); white-space:nowrap;">
        数据仓库 · duckdb
      </div>
    </aside>

    <!-- 内容区 -->
    <main style="flex:1; overflow-y:auto; padding:20px 24px;">
      <router-view />
    </main>
  </div>
</template>
