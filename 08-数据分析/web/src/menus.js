// 菜单/路由单一数据源：新增功能 = 在此加一项 + 建对应页面组件
// title: 菜单名 | path: 路由路径 | icon: Lucide 图标组件 | children: 子菜单（可选）
// 无 children 的顶级项 = 直接菜单项（如仪表盘 → /home）
import { LayoutDashboard, TrendingUp, SlidersHorizontal, Star, ChartCandlestick, BarChart3, Coins, Wallet, Database, Clock, Settings, ReceiptText, PiggyBank } from 'lucide-vue-next'

export default [
  {
    title: '仪表盘',
    icon: LayoutDashboard,
    path: '/home',
  },
  {
    title: '行情分析',
    icon: TrendingUp,
    path: '/market',
    children: [
      { title: '关注标的', icon: Star, path: '/market/watchlist' },
      { title: '持仓管理', icon: Wallet, path: '/market/position' },
      { title: '交易记录', icon: ReceiptText, path: '/market/transaction' },
      { title: 'K线分析', icon: ChartCandlestick, path: '/market/kline' },
      { title: '分价分布', icon: BarChart3, path: '/market/fenjia' },
      { title: '资金流向', icon: Coins, path: '/market/fundflow' },  // 页面内 Tabs 切个股/行业板块；API /api/capital-flow
      { title: '财务数据', icon: PiggyBank, path: '/market/finance' },
    ],
  },
  {
    title: '系统管理',
    icon: SlidersHorizontal,
    path: '/system',
    children: [
      { title: '定时任务', icon: Clock, path: '/system/tasks' },
      { title: '数据管理', icon: Database, path: '/system/data' },
      { title: '设置', icon: Settings, path: '/system/settings' },
    ],
  },
]
