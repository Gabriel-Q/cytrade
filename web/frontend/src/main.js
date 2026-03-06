import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import Dashboard from './views/Dashboard.vue'
import Strategies from './views/Strategies.vue'
import Positions from './views/Positions.vue'
import Orders from './views/Orders.vue'

const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/dashboard', component: Dashboard },
  { path: '/strategies', component: Strategies },
  { path: '/positions', component: Positions },
  { path: '/orders', component: Orders },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(ElementPlus)
app.mount('#app')
