import { createApp } from 'vue'
import App from './App.vue'
import router from './router.js'
import ArcoVue from '@arco-design/web-vue'
import '@arco-design/web-vue/dist/arco.css'
import './style.css'

const app = createApp(App)
app.use(router)
app.use(ArcoVue)
app.mount('#app')

// Arco 深色主题（暗色仪表盘）
document.body.setAttribute('arco-theme', 'dark')
