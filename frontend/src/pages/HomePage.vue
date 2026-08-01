<template>
  <div>
    <h1 style="font-size:24px;margin-bottom:8px">🏛️ Plato</h1>
    <p class="gray mb">动态数据驱动的实时协同多维表格</p>

    <div class="grid col2">
      <div class="card">
        <h2>📊 动态表管理</h2>
        <p class="gray">在运行时创建和修改数据库表结构，无需迁移。</p>
        <div class="mt"><router-link to="/tables"><button>进入</button></router-link></div>
      </div>
      <div class="card">
        <h2>🔗 可视化画布</h2>
        <p class="gray">拖拽节点定义公式依赖，Rust 引擎实时校验。</p>
        <div class="mt"><router-link to="/canvas"><button>进入</button></router-link></div>
      </div>
      <div class="card">
        <h2>⏰ 定时任务</h2>
        <p class="gray">创建 Cron 定时任务，自动验证和重算数据。</p>
        <div class="mt"><router-link to="/schedules"><button>进入</button></router-link></div>
      </div>
      <div class="card">
        <h2>⚡ 实时协同</h2>
        <p class="gray">Yjs CRDT 驱动的多人实时编辑引擎。</p>
        <p class="gray mt">WebSocket /ws/table/{name}/</p>
      </div>
    </div>

    <div class="card mt">
      <h2>🏆 技术栈</h2>
      <div class="flex">
        <span class="badge badge-ok">Django 6</span>
        <span class="badge badge-ok">PostgreSQL 16</span>
        <span class="badge badge-ok">Redis 7</span>
        <span class="badge badge-ok">ClickHouse</span>
        <span class="badge badge-ok">Rust/PyO3</span>
        <span class="badge badge-ok">y-py CRDT</span>
        <span class="badge badge-ok">Celery</span>
        <span class="badge badge-ok">Vue 3</span>
      </div>
    </div>
  </div>
</template>
