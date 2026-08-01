<template>
  <div class="app">
    <div v-if="!user" class="login-page">
      <div class="login-card">
        <h1 style="color:#58a6ff;text-align:center;margin-bottom:24px">🏛️ Plato</h1>
        <p class="gray" style="text-align:center;margin-bottom:20px">动态数据协同系统</p>
        <input v-model="loginForm.username" placeholder="用户名" style="margin-bottom:8px" @keyup.enter="doLogin" />
        <input v-model="loginForm.password" type="password" placeholder="密码" style="margin-bottom:12px" @keyup.enter="doLogin" />
        <button @click="doLogin" :disabled="loading" style="width:100%;margin-bottom:8px">{{ loading ? '登录中...' : '登录' }}</button>
        <p class="gray" style="text-align:center;font-size:11px">Demo: admin / admin123</p>
        <p v-if="loginMsg" :class="loginOk ? 'green' : 'red'" style="text-align:center;margin-top:8px;font-size:13px">{{ loginMsg }}</p>
      </div>
    </div>

    <div v-else>
      <nav>
        <router-link to="/">🏛️ Plato</router-link>
        <router-link to="/tables">📊 表管理</router-link>
        <router-link to="/canvas">🔗 画布</router-link>
        <router-link to="/schedules">⏰ 定时</router-link>
        <span style="margin-left:auto;color:#8b949e;font-size:13px;padding:14px 0">{{ user.username }}</span>
        <a @click="logout" style="cursor:pointer;color:#8b949e;padding:14px 20px;font-size:13px">退出</a>
      </nav>
      <main><router-view /></main>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api, getToken } from './api.js'

const user = ref(null)
const loading = ref(false)
const loginForm = ref({ username: 'admin', password: 'admin123' })
const loginMsg = ref('')
const loginOk = ref(true)

onMounted(() => {
  const saved = localStorage.getItem('plato_user')
  const token = getToken()
  if (saved && token) user.value = JSON.parse(saved)
})

async function doLogin() {
  loading.value = true; loginMsg.value = ''
  const r = await api.login(loginForm.value.username, loginForm.value.password)
  loading.value = false
  if (r.access) {
    localStorage.setItem('plato_token', r.access)
    localStorage.setItem('plato_user', JSON.stringify(r.user))
    user.value = r.user
  } else {
    loginOk.value = false; loginMsg.value = r.error || '登录失败'
  }
}

function logout() {
  localStorage.removeItem('plato_token')
  localStorage.removeItem('plato_user')
  user.value = null
}
</script>

<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0d1117;color:#c9d1d9}
.app{min-height:100vh}
nav{display:flex;gap:0;background:#161b22;border-bottom:1px solid #30363d;padding:0 20px}
nav a{color:#8b949e;text-decoration:none;padding:14px 20px;font-size:14px;border-bottom:2px solid transparent;transition:all .2s}
nav a:hover,nav a.router-link-active{color:#f0f6fc;border-bottom-color:#58a6ff}
main{padding:24px;max-width:1400px;margin:0 auto}
button,input,select,textarea{font-family:inherit;font-size:13px;padding:8px 14px;border:1px solid #30363d;border-radius:6px;background:#0d1117;color:#c9d1d9;outline:none;width:100%}
button{background:#238636;color:#fff;border:none;cursor:pointer;white-space:nowrap}
button:hover{opacity:.9}
button.danger{background:#da3633}
button.secondary{background:#21262d;border:1px solid #30363d;color:#c9d1d9}
input:focus,select:focus,textarea:focus{border-color:#58a6ff}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;margin-bottom:16px}
.card h2{font-size:16px;color:#58a6ff;margin-bottom:16px}
table{width:100%;border-collapse:collapse;font-size:13px}
td,th{border:1px solid #30363d;padding:6px 10px;text-align:left}
th{background:#0d1117;color:#8b949e;font-weight:600}
tr:hover{background:#1c2129}
.grid{display:grid;gap:16px}
.col2{grid-template-columns:1fr 1fr}
.flex{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.mb{margin-bottom:12px}
.mt{margin-top:12px}
.gray{color:#8b949e;font-size:12px}
.green{color:#3fb950}
.red{color:#f85149}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px}
.badge-ok{background:#033a16;color:#3fb950}
.badge-err{background:#490202;color:#f85149}
pre{background:#0d1117;padding:12px;border-radius:6px;font-size:12px;overflow:auto;max-height:400px}
.empty{text-align:center;color:#484f58;padding:40px}
.login-page{display:flex;justify-content:center;align-items:center;min-height:100vh}
.login-card{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:32px;width:360px}
.login-card input{width:100%}
.login-card button{width:100% !important}
</style>
