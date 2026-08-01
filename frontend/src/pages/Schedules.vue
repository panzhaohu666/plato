<template>
  <div>
    <h1>⏰ 定时任务</h1>
    <p class="gray mb">创建 Cron 定时任务，自动执行数据验证和重算。</p>

    <div class="grid col2">
      <div class="card">
        <h2>创建任务</h2>
        <div class="mb"><input v-model="form.name" placeholder="任务名称" /></div>
        <div class="mb"><input v-model="form.table" placeholder="目标表名" /></div>
        <div class="mb">
          <select v-model="form.type" style="width:100%">
            <option value="validate_table">数据验证</option>
            <option value="recalculate_table">重新计算</option>
            <option value="archive_old_rows">归档旧数据</option>
          </select>
        </div>
        <div class="flex mb">
          <input v-model="form.minute" placeholder="分" style="flex:1" />
          <input v-model="form.hour" placeholder="时" style="flex:1" />
        </div>
        <p class="gray mb">Cron: {{ form.minute || '*' }} {{ form.hour || '*' }} * * *</p>
        <button @click="create" :disabled="loading">{{ loading?'...':'创建' }}</button>
        <p v-if="msg" :class="msgOk?'green':'red'" class="mt">{{ msg }}</p>
      </div>

      <div class="card">
        <h2>已有任务 ({{ schedules.length }})</h2>
        <button @click="loadSchedules" class="secondary mb">刷新</button>
        <div v-if="schedules.length">
          <div v-for="s in schedules" :key="s.id" style="padding:8px 0;border-bottom:1px solid #21262d;font-size:13px">
            <div class="flex" style="justify-content:space-between">
              <strong>{{ s.name }}</strong>
              <span :class="s.enabled ? 'badge badge-ok' : 'badge badge-err'">{{ s.enabled ? '启用' : '停用' }}</span>
            </div>
            <div class="gray">{{ s.task_type }} → {{ s.table_name }}</div>
            <div class="gray" style="font-size:11px">{{ s.schedule.type }}: {{ s.schedule.minute }} {{ s.schedule.hour }}</div>
            <button class="danger" @click="remove(s.id)" style="padding:2px 8px;font-size:11px;margin-top:4px">删除</button>
          </div>
        </div>
        <div v-else class="empty">暂无定时任务</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api.js'

const schedules = ref([])
const form = ref({ name: '', table: '', type: 'validate_table', minute: '0', hour: '2' })
const loading = ref(false)
const msg = ref(''); const msgOk = ref(true)

onMounted(loadSchedules)

async function loadSchedules() { const r = await api.listSchedules(); schedules.value = r.schedules || [] }

async function create() {
  if (!form.value.name || !form.value.table) return
  loading.value = true
  const r = await api.createSchedule({
    name: form.value.name, task_type: form.value.type, table_name: form.value.table,
    schedule_type: 'crontab', schedule_config: { minute: form.value.minute, hour: form.value.hour }
  })
  loading.value = false
  msgOk.value = r.success; msg.value = r.success ? '任务创建成功' : r.error
  if (r.success) { form.value.name = ''; loadSchedules() }
}

async function remove(id) { await api.deleteSchedule(id); loadSchedules() }
</script>
