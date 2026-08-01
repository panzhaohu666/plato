import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import HomePage from './pages/HomePage.vue'
import TableManager from './pages/TableManager.vue'
import DataGrid from './pages/DataGrid.vue'
import CanvasEditor from './pages/CanvasEditor.vue'
import Schedules from './pages/Schedules.vue'

const routes = [
  { path: '/', component: HomePage },
  { path: '/tables', component: TableManager },
  { path: '/tables/:name', component: DataGrid, props: true },
  { path: '/canvas', component: CanvasEditor },
  { path: '/schedules', component: Schedules },
]

const router = createRouter({ history: createWebHistory(), routes })
const app = createApp(App)
app.use(router)
app.mount('#app')
