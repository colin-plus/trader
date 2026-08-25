// 菜单/路由单一数据源：新增功能 = 在此加一项 + 建对应页面组件
// title: 菜单名 | path: 路由路径 | icon: Lucide 图标组件 | children: 子菜单（可选）
import { TrendingUp, PieChart, Wallet, Database, Settings } from 'lucide-vue-next'

export default [
  {
    title: '行情中心',
    icon: TrendingUp,
    path: '/market',
    children: [
      { title: 'K线', path: '/market/kline' },
      { title: '分价分布', path: '/market/fenjia' },
      { title: '资金流向', path: '/market/fundflow' },
    ],
  },
  {
    title: '财务分析',
    icon: PieChart,
    path: '/finance',
    children: [
      { title: '财务速览', path: '/finance/overview' },
      { title: '估值对比', path: '/finance/valuation' },
    ],
  },
  { title: '持仓管理', icon: Wallet, path: '/position' },
  { title: '数据管理', icon: Database, path: '/data' },
  { title: '设置', icon: Settings, path: '/settings' },
]
