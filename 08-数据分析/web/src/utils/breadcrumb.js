// 面包屑推导：从 menus.js(唯一数据源) + 当前路由路径生成 [顶级组, 页面]
// 有仪表盘后不再加"首页"前缀；未知路径返回空数组（不显示面包屑）
import menus from '../menus.js'

export function getBreadcrumb(path) {
  // 顶级直接菜单（如仪表盘 /home）：单一项
  for (const item of menus) {
    if (!item.children && path.startsWith(item.path)) {
      return [{ title: item.title, path: item.path }]
    }
  }

  // 子页面：顶级组 → 当前页
  for (const item of menus) {
    if (!item.children) continue
    const child = item.children.find(c => path.startsWith(c.path))
    if (child) {
      return [
        { title: item.title, path: item.children[0].path },
        { title: child.title, path: child.path },
      ]
    }
  }

  // 未知路径（如 404）：不显示面包屑
  return []
}
