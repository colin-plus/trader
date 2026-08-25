<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import menus from '../menus.js'

const route = useRoute()
const collapsed = ref(false)

// 当前激活的顶级菜单（用于父级高亮）
const activeTop = computed(() => {
  const path = route.path
  for (const item of menus) {
    if (item.children) {
      if (item.children.some(c => path.startsWith(c.path))) return item.path
    } else if (path.startsWith(item.path)) {
      return item.path
    }
  }
  return ''
})

// 展开的顶级菜单组
const openGroups = ref(new Set())

// 路由变化时：自动展开当前路由所属的组（不关闭其他组）
watch(
  () => route.path,
  (path) => {
    for (const item of menus) {
      if (item.children) {
        const hit = item.children.some(c => path.startsWith(c.path))
        if (hit) {
          const s = new Set(openGroups.value)
          s.add(item.path)
          openGroups.value = s
        }
      }
    }
  },
  { immediate: true }
)

function toggleGroup(path) {
  const s = new Set(openGroups.value)
  s.has(path) ? s.delete(path) : s.add(path)
  openGroups.value = s
}

function isActive(path) {
  return route.path === path || route.path.startsWith(path + '/')
}
</script>

<template>
  <div style="display:flex; height:100vh; overflow:hidden;">
    <!-- 侧边栏 -->
    <aside
      :style="{
        width: collapsed ? '52px' : '200px',
        background: '#151b23',
        borderRight: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        transition: 'width .18s ease',
        flexShrink: 0,
      }"
    >
      <!-- 顶部：标题 + 折叠按钮 -->
      <div style="display:flex; align-items:center; gap:8px; padding:14px 12px; border-bottom:1px solid var(--border);">
        <span style="font-size:20px; cursor:pointer; user-select:none;" @click="collapsed = !collapsed" title="折叠/展开">
          {{ collapsed ? '📈' : '📈 Trader' }}
        </span>
        <span v-if="!collapsed" style="font-size:14px; font-weight:600; color:var(--text); flex:1;">Trader Data</span>
        <span v-if="!collapsed" style="cursor:pointer; color:var(--muted); font-size:12px;" @click="collapsed = !collapsed">◀</span>
      </div>

      <!-- 菜单 -->
      <nav style="flex:1; overflow-y:auto; padding:8px 0;">
        <template v-for="item in menus" :key="item.path">
          <!-- 有子菜单 -->
          <template v-if="item.children">
            <div
              @click="toggleGroup(item.path)"
              :style="{
                display:'flex', alignItems:'center', gap:'8px', padding:'10px 14px',
                cursor:'pointer', fontSize:'14px', color: activeTop === item.path ? 'var(--accent)' : 'var(--text)',
                background: activeTop === item.path ? '#1c2431' : 'transparent',
              }"
            >
              <span>{{ item.icon }}</span>
              <span v-if="!collapsed" style="flex:1;">{{ item.title }}</span>
              <span v-if="!collapsed" style="font-size:10px; color:var(--muted);">
                {{ openGroups.has(item.path) ? '▾' : '▸' }}
              </span>
            </div>
            <div v-if="openGroups.has(item.path) && !collapsed">
              <router-link
                v-for="child in item.children"
                :key="child.path"
                :to="child.path"
                :style="{
                  display:'block', padding:'8px 14px 8px 44px', fontSize:13,
                  color: isActive(child.path) ? 'var(--accent)' : 'var(--muted)',
                  textDecoration:'none', borderLeft: isActive(child.path) ? '2px solid var(--accent)' : '2px solid transparent',
                }"
              >{{ child.title }}</router-link>
            </div>
          </template>

          <!-- 无子菜单 -->
          <router-link
            v-else
            :to="item.path"
            :style="{
              display:'flex', alignItems:'center', gap:'8px', padding:'10px 14px',
              fontSize:'14px', color: isActive(item.path) ? 'var(--accent)' : 'var(--text)',
              textDecoration:'none', background: isActive(item.path) ? '#1c2431' : 'transparent',
            }"
          >{{ item.icon }} <span v-if="!collapsed">{{ item.title }}</span></router-link>
        </template>
      </nav>

      <!-- 底部：数据库更新时间 -->
      <div v-if="!collapsed" style="padding:10px 14px; border-top:1px solid var(--border); font-size:11px; color:var(--muted);">
        数据仓库 · duckdb
      </div>
    </aside>

    <!-- 内容区 -->
    <main style="flex:1; overflow-y:auto; padding:20px 24px;">
      <router-view />
    </main>
  </div>
</template>
