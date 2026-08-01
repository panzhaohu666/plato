<template>
  <div>
    <h1>🔗 公式依赖画布</h1>
    <p class="gray mb">可视化定义列之间的公式依赖关系。Rust 引擎实时检测循环依赖。</p>

    <div class="grid col2">
      <div class="card">
        <h2>列节点</h2>
        <p class="gray mb">点击添加列，拖拽连线建立依赖。</p>
        <div class="flex mb">
          <input v-model="colName" placeholder="列名" style="flex:1" />
          <select v-model="dependsOn" style="flex:1">
            <option value="">无依赖（源列）</option>
            <option v-for="n in nodes" :key="n" :value="n">{{ n }}</option>
          </select>
          <button @click="addNode">添加</button>
        </div>
        <div v-if="msg" :class="msgOk?'green':'red'" class="mt">{{ msg }}</div>
      </div>

      <div class="card">
        <h2>依赖分析</h2>
        <button @click="analyze" :disabled="!nodes.length">🔍 分析依赖</button>
        <div class="mt" v-if="result">
          <div v-if="result.has_cycle" class="red">
            ⚠️ 检测到循环依赖！<br/>
            <span v-for="c in result.cycles" :key="c">{{ c.join(' → ') }}</span>
          </div>
          <div v-else class="green">
            ✅ 无循环依赖<br/>
            计算顺序（同层可并行）：
            <div v-for="(group,i) in result.order" :key="i" class="mt" style="font-size:12px">
              <span class="badge badge-ok">第{{ i }}层</span>
              <span v-for="col in group" :key="col" class="badge" style="background:#1c2129;margin:2px">{{ col }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="card mt">
      <h2>依赖图 ({{ nodes.length }} 个节点)</h2>
      <div class="flex" style="flex-wrap:wrap;gap:12px;min-height:120px">
        <div v-for="n in nodes" :key="n" style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px;text-align:center">
          <div style="font-weight:600">{{ n }}</div>
          <div class="gray" style="font-size:11px">{{ edges[n]?.length ? '← ' + edges[n].join(', ') : '源列' }}</div>
          <button class="danger" @click="removeNode(n)" style="padding:2px 6px;font-size:10px;margin-top:4px">×</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { api } from '../api.js'

const nodes = ref([])
const edges = ref({})
const colName = ref('')
const dependsOn = ref('')
const result = ref(null)
const msg = ref(''); const msgOk = ref(true)

function addNode() {
  const name = colName.value.trim()
  if (!name || nodes.value.includes(name)) return
  nodes.value.push(name)
  edges.value[name] = []
  if (dependsOn.value && nodes.value.includes(dependsOn.value)) {
    edges.value[name].push(dependsOn.value)
  }
  colName.value = ''; dependsOn.value = ''
  result.value = null
}

function removeNode(name) {
  nodes.value = nodes.value.filter(n => n !== name)
  delete edges.value[name]
  for (const k in edges.value) edges.value[k] = edges.value[k].filter(d => d !== name)
  result.value = null
}

async function analyze() {
  const cols = nodes.value.map(n => ({ name: n, dependencies: edges.value[n] || [] }))
  try {
    result.value = await api.analyzeDeps(cols)
  } catch {
    result.value = { has_cycle: detectCycle(cols), cycles: [], order: [nodes.value] }
  }
}

function detectCycle(cols) {
  const g = {}; cols.forEach(c => g[c.name] = c.dependencies || [])
  const visited = new Set(), stack = new Set()
  function dfs(n) {
    if (stack.has(n)) return true
    if (visited.has(n)) return false
    visited.add(n); stack.add(n)
    for (const d of (g[n] || [])) if (dfs(d)) return true
    stack.delete(n); return false
  }
  return cols.some(c => dfs(c.name))
}
</script>
