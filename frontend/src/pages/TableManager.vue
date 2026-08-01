<template>
  <div>
    <h1>📊 表管理</h1>
    <p class="gray mb">运行时创建动态表，无需数据库迁移。</p>

    <div class="card mb">
      <h2>创建新表</h2>
      <div class="flex mb">
        <input v-model="newTable.name" placeholder="表名（英文）" style="flex:1" />
        <input v-model="newTable.display" placeholder="显示名" style="flex:1" />
      </div>
      <p class="gray mb">列定义（每行列名:类型，一行一个）：</p>
      <textarea v-model="newTable.colsText" rows="4" placeholder="company:string&#10;revenue:decimal&#10;stage:string" style="width:100%;margin-bottom:8px"></textarea>
      <p class="gray mb">类型: string, text, integer, decimal, boolean, date, datetime, json</p>
      <button @click="createTable" :disabled="loading">{{ loading ? '创建中...' : '创建表' }}</button>
      <p v-if="msg" :class="msgOk ? 'green' : 'red'" class="mt">{{ msg }}</p>
    </div>

    <div class="card">
      <h2>已有表 ({{ tables.length }})</h2>
      <div v-if="loading" class="gray">加载中...</div>
      <table v-else-if="tables.length">
        <thead><tr><th>表名</th><th>显示名</th><th>列数</th><th>创建时间</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="t in tables" :key="t.name">
            <td><code>{{ t.name }}</code></td>
            <td>{{ t.display_name }}</td>
            <td>{{ t.columns.length }}</td>
            <td class="gray">{{ t.created_at?.slice(0,10) }}</td>
            <td>
              <router-link :to="'/tables/' + t.name"><button class="secondary" style="padding:4px 10px;font-size:12px">查看数据</button></router-link>
              <button class="danger" @click="archiveTable(t.name)" style="padding:4px 10px;font-size:12px;margin-left:4px">归档</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty">还没有动态表，创建一个吧</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api.js'

const tables = ref([])
const newTable = ref({ name: '', display: '', colsText: '' })
const loading = ref(false)
const msg = ref('')
const msgOk = ref(true)

onMounted(loadTables)

async function loadTables() {
  loading.value = true
  const r = await api.listTables()
  tables.value = r.tables || []
  loading.value = false
}

async function createTable() {
  msg.value = ''
  const cols = newTable.value.colsText.split('\n').filter(Boolean).map(line => {
    const [name, type = 'string'] = line.split(':')
    return { name: name.trim(), col_type: type.trim(), nullable: true }
  })
  if (!newTable.value.name || cols.length === 0) return

  loading.value = true
  const r = await api.createTable({
    name: newTable.value.name,
    display_name: newTable.value.display || newTable.value.name,
    columns: cols
  })
  loading.value = false
  msgOk.value = r.success
  msg.value = r.success ? `表 "${newTable.value.name}" 创建成功！` : r.error
  if (r.success) { newTable.value = { name: '', display: '', colsText: '' }; loadTables() }
}

async function archiveTable(name) {
  if (!confirm(`归档表 "${name}"？`)) return
  await api.archiveTable(name)
  loadTables()
}
</script>
