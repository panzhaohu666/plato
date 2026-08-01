<template>
  <div>
    <div class="flex mb">
      <h1>📋 {{ name }}</h1>
      <router-link to="/tables"><button class="secondary">← 返回</button></router-link>
    </div>

    <!-- Add Column -->
    <div class="card">
      <h2>➕ 添加列</h2>
      <div class="flex">
        <input v-model="newCol.name" placeholder="列名" style="flex:1" />
        <select v-model="newCol.type" style="flex:1"><option v-for="t in types" :key="t" :value="t">{{ t }}</option></select>
        <button @click="addColumn">添加</button>
      </div>
      <p v-if="colMsg" :class="colMsgOk?'green':'red'" class="mt">{{ colMsg }}</p>
    </div>

    <!-- Insert Row -->
    <div class="card">
      <h2>➕ 插入行</h2>
      <div v-for="col in columns" :key="col.name" class="flex mb" style="max-width:400px">
        <label style="width:120px;font-size:13px">{{ col.name }}</label>
        <input v-model="newRow[col.name]" :placeholder="col.type" style="flex:1" />
      </div>
      <button @click="insertRow" :disabled="loading">{{ loading ? '...' : '插入' }}</button>
      <p v-if="rowMsg" :class="rowMsgOk?'green':'red'" class="mt">{{ rowMsg }}</p>
    </div>

    <!-- Data Table -->
    <div class="card">
      <h2>数据 ({{ total }} 行) <button class="secondary" @click="loadRows" style="margin-left:8px;font-size:12px;padding:4px 10px">刷新</button></h2>
      <div v-if="rows.length" style="overflow-x:auto">
        <table>
          <thead><tr><th v-for="col in columns" :key="col.name">{{ col.name }}</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="row in rows" :key="row.id">
              <td v-for="col in columns" :key="col.name">{{ formatVal(row[col.name]) }}</td>
              <td><button class="danger" @click="deleteRow(row.id)" style="padding:3px 8px;font-size:11px">删除</button></td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty">暂无数据</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api.js'

const props = defineProps({ name: String })

const columns = ref([])
const rows = ref([])
const total = ref(0)
const newRow = ref({})
const newCol = ref({ name: '', type: 'string' })
const types = ['string','text','integer','decimal','boolean','date','datetime','json']
const loading = ref(false)
const rowMsg = ref(''); const rowMsgOk = ref(true)
const colMsg = ref(''); const colMsgOk = ref(true)

onMounted(loadAll)

async function loadAll() {
  const [t, r] = await Promise.all([api.getTable(props.name), api.listRows(props.name, '?limit=100')])
  columns.value = t.table?.columns || []
  rows.value = r.rows || []
  total.value = r.total || 0
}

async function loadRows() { const r = await api.listRows(props.name, '?limit=100'); rows.value = r.rows || []; total.value = r.total || 0 }

async function insertRow() {
  loading.value = true
  const r = await api.createRow(props.name, newRow.value)
  loading.value = false
  rowMsgOk.value = r.success; rowMsg.value = r.success ? '插入成功' : r.error
  if (r.success) { newRow.value = {}; loadRows() }
}

async function deleteRow(id) {
  if (!confirm('删除此行？')) return
  await api.deleteRow(props.name, id)
  loadRows()
}

async function addColumn() {
  if (!newCol.value.name) return
  const r = await api.addColumn(props.name, newCol.value)
  colMsgOk.value = r.success; colMsg.value = r.success ? '列添加成功' : r.error
  if (r.success) { newCol.value = { name: '', type: 'string' }; loadAll() }
}

function formatVal(v) {
  if (v === null || v === undefined) return ''
  if (typeof v === 'boolean') return v ? '✅' : '❌'
  if (typeof v === 'object') return JSON.stringify(v)
  return v
}
</script>
