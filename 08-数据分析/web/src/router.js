// 路由表：与 menus.js 对应。真实页面直接 import，占位页面用懒加载占位组件。
import { createRouter, createWebHistory } from 'vue-router'
import { h } from 'vue'
import menus from './menus.js'

// 占位页面组件（未开发的功能统一用此占位，显示功能名）
// 用 h() 渲染函数而非 template 字符串（Vite 默认运行时构建不含模板编译器）
const Placeholder = {
  props: { title: String },
  render() {
    return h('div', {
      style: 'display:flex;flex-direction:column;align-items:center;justify-content:center;height:60vh;color:var(--muted);',
    }, [
      h('div', { style: 'font-size:48px;margin-bottom:16px;' }, '🚧'),
      h('div', { style: 'font-size:18px;margin-bottom:8px;' }, this.title),
      h('div', { style: 'font-size:13px;' }, '功能开发中，敬请期待'),
    ])
  },
}

// 展平菜单生成 (path → {title, component})，保证 menus.js 是唯一数据源
function buildRoutes(menuItems) {
  const routes = []
  for (const item of menuItems) {
    if (item.children) {
      // 父级：重定向到第一个子菜单
      routes.push({
        path: item.path,
        redirect: item.children[0].path,
      })
      for (const child of item.children) {
        routes.push(makeRoute(child.path, child.title))
      }
    } else {
      routes.push(makeRoute(item.path, item.title))
    }
  }
  return routes
}

// 显式页面映射：Vite 能静态分析的懒加载（比动态模板字符串可靠）
const pageModules = import.meta.glob('./pages/**/*.vue')

function makeRoute(path, title) {
  // 约定：真实页面在 src/pages/ 下，路径 → 文件名（如 /market/kline → pages/market/kline.vue）
  const rel = `./pages/${path.slice(1)}.vue`
  const loader = pageModules[rel]
  return {
    path,
    meta: { title },
    component: loader
      ? loader  // 页面存在 → 懒加载
      : () => Promise.resolve({  // 页面不存在 → 占位组件（props 注入功能名）
          components: { default: Placeholder },
          render() {
            return h(Placeholder, { title })
          },
        }),
  }
}

const routes = buildRoutes(menus)

// 首页：不在侧边菜单（面包屑第一项入口），单独注册
routes.push({
  path: '/home',
  meta: { title: '首页' },
  component: () => import('./pages/home.vue'),
})
routes.push({ path: '/', redirect: '/home' })
routes.push({ path: '/:pathMatch(.*)*', redirect: '/home' })

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
