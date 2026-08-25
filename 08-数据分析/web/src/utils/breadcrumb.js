// 面包屑推导：从 menus.js(唯一数据源) + 当前路由路径生成 [首页, 顶级组, 页面]
// 后续加三级导航只需扩展本函数
import menus from '../menus.js'

export function getBreadcrumb(path) {
  // 首页本身：只有一项
  if (path === '/home') return [{ title: '首页', path: '/home' }]

  const crumbs = [{ title: '首页', path: '/home' }]

  for (const item of menus) {
    if (item.children) {
      const child = item.children.find(c => path.startsWith(c.path))
      if (child) {
        // 顶级组 → 组首页（第一个子页面）；页面 → 当前页
        crumbs.push({ title: item.title, path: item.children[0].path })
        crumbs.push({ title: child.title, path: child.path })
        return crumbs
      }
    } else if (path.startsWith(item.path)) {
      crumbs.push({ title: item.title, path: item.path })
      return crumbs
    }
  }

  // 未知路径（如 404）：仅首页
  return crumbs
}
