# 🏛️ Plato

**动态数据驱动的实时协同多维表格系统**

一个类似 Notion + Airtable + Zapier 的怪物级全栈项目。用户在前端画布上定义数据模型，后端实时生成物理表，支持多人 CRDT 协同编辑。

[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://python.org)
[![Django](https://img.shields.io/badge/Django-6.0-green)](https://djangoproject.com)
[![Rust](https://img.shields.io/badge/Rust-1.97-orange)](https://rust-lang.org)
[![Vue](https://img.shields.io/badge/Vue-3.5-42b883)](https://vuejs.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue)](https://postgresql.org)
[![ClickHouse](https://img.shields.io/badge/ClickHouse-24.8-yellow)](https://clickhouse.com)
[![Redis](https://img.shields.io/badge/Redis-7-red)](https://redis.io)

---

## 🎯 核心能力

| 关卡 | 能力 | 实现 |
|---|---|---|
| 1️⃣ | **动态 Schema 构建** | 前端 JSON → Django SchemaEditor → PostgreSQL 实时建表，软删除列，savepoint 防御 |
| 2️⃣ | **实时 CRDT 协同** | y-py（Yjs Python 实现）+ Django Channels + Redis Pub/Sub 多 Worker 同步 |
| 3️⃣ | **Rust 拓扑排序** | PyO3 绑定，Kahn 算法 + 循环检测 + 分层分组并行计算 |
| 4️⃣ | **ClickHouse 冷存储** | 双写架构：PG 热数据 + CH 事件日志，90 天 TTL |
| 5️⃣ | **Celery 动态调度** | DatabaseScheduler，运行时创建/删除 Cron 任务，AST 白名单表达式沙箱 |

---

## 🏗️ 架构

```
┌─────────────────────────────────────────────────┐
│                   Nginx :8080                    │
│         /api → Daphne  /ws → Daphne             │
└─────────────────────┬───────────────────────────┘
                      │
┌─────────────────────┴───────────────────────────┐
│              Django 6 (ASGI)                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ REST API │ │ GraphQL  │ │ Channels/WebSocket│ │
│  └────┬─────┘ └────┬─────┘ └────────┬─────────┘ │
│       │            │               │            │
│  ┌────┴────────────┴───────────────┴──────────┐ │
│  │         DynamicModelManager                │ │
│  │  运行时建表 · 软删除列 · SchemaEditor       │ │
│  └────────────────────┬───────────────────────┘ │
│                       │                          │
│  ┌────────────────────┼───────────────────────┐ │
│  │  YjsDocManager  │  TaskScheduler  │ Rust   │ │
│  │  CRDT 协同       │  Celery Beat    │ Engine │ │
│  └────────────────────┴─────────────────┴──────┘ │
└─────────────────────┬───────────────────────────┘
                      │
     ┌────────────────┼────────────────┐
     ▼                ▼                ▼
┌─────────┐    ┌──────────┐    ┌────────────┐
│PostgreSQL│    │  Redis   │    │ ClickHouse │
│  16      │    │    7     │    │   24.8     │
└─────────┘    └──────────┘    └────────────┘
```

---

## 🚀 快速开始

### 环境要求

- Python 3.12, Node.js 24, Rust 1.97
- PostgreSQL 16, Redis 7, Docker

### 1. 克隆并配置

```bash
git clone https://github.com/panzhaohu666/plato.git
cd plato

# 创建虚拟环境
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的数据库密码等
```

### 2. 数据库

```bash
# PostgreSQL — 创建数据库和用户
sudo -u postgres psql -c "CREATE USER hydra WITH PASSWORD 'hydra_pass_2024' CREATEDB;"
sudo -u postgres psql -c "CREATE DATABASE hydra_db OWNER hydra;"

# 运行迁移
python manage.py migrate

# 创建公共租户
python manage.py shell -c "
from apps.tenants.models import Tenant, Domain
t = Tenant.objects.create(schema_name='public', name='Plato')
Domain.objects.create(domain='localhost', tenant=t, is_primary=True)
"
```

### 3. ClickHouse

```bash
docker compose up -d clickhouse
docker exec hydra-clickhouse clickhouse-client -u hydra --password hydra_clickhouse_2024 -d hydra_analytics -q "
CREATE TABLE IF NOT EXISTS hydra_analytics.dynamic_table_event_log (
    event_id UUID DEFAULT generateUUIDv4(),
    tenant_schema LowCardinality(String),
    table_name LowCardinality(String),
    event_type Enum8('INSERT'=1,'UPDATE'=2,'DELETE'=3),
    row_id String, old_data String DEFAULT '', new_data String,
    changed_by String DEFAULT '', event_time DateTime64(3) DEFAULT now64(3)
) ENGINE = MergeTree() PARTITION BY toYYYYMM(event_time)
ORDER BY (tenant_schema, table_name, event_time)
TTL toDateTime(event_time) + INTERVAL 90 DAY
"
```

### 4. Rust 引擎

```bash
cd rust_engine
maturin develop --release
cd ..
```

### 5. 启动服务

```bash
# 终端 1：Django 后端
python manage.py runserver 8000

# 终端 2：Vue 前端
cd frontend && npm install && npx vite --host 0.0.0.0
```

### 6. 打开浏览器

`http://localhost:5173` → 登录 `admin / admin123`

---

## 📡 API 端点

### 认证
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/tenants/register/` | 注册 |
| POST | `/api/tenants/login/` | 登录（返回 JWT） |
| POST | `/api/tenants/token/refresh/` | 刷新 Token |

### 动态表
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/tables/` | 创建动态表 |
| GET | `/api/tables/list/` | 列出所有表 |
| GET | `/api/tables/{name}/` | 表元数据 |
| DELETE | `/api/tables/{name}/archive/` | 归档表 |
| POST | `/api/tables/{name}/columns/` | 添加列 |
| DELETE | `/api/tables/{name}/columns/{col}/` | 软删除列 |

### 行操作
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/tables/{name}/rows/` | 插入行 |
| GET | `/api/tables/{name}/rows/list/` | 查询行 |
| PUT | `/api/tables/{name}/rows/{id}/update/` | 更新行 |
| DELETE | `/api/tables/{name}/rows/{id}/delete/` | 删除行 |

### 定时任务
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/tasks/schedules/` | 列出任务 |
| POST | `/api/tasks/schedules/create/` | 创建 Cron 任务 |
| DELETE | `/api/tasks/schedules/{id}/delete/` | 删除任务 |

### 依赖分析
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/deps/analyze/` | Rust 引擎依赖分析 |

### WebSocket
| 协议 | 路径 | 说明 |
|---|---|---|
| WS | `/ws/table/{name}/` | Yjs CRDT 实时协同 |

---

## 🧪 测试

```bash
# Django 集成测试
python manage.py shell < tests.py

# Rust 测试
cd rust_engine && cargo test
```

## 📂 项目结构

```
plato/
├── apps/
│   ├── dynamic_models/     # 核心：动态ORM + Yjs + ClickHouse + Celery
│   │   ├── manager.py      # DynamicModelManager（运行时建表）
│   │   ├── yjs_service.py   # YjsDocManager（CRDT协同引擎）
│   │   ├── consumers.py     # WebSocket Yjs Sync Protocol
│   │   ├── task_registry.py # Celery动态调度
│   │   ├── expression_engine.py  # AST白名单沙箱
│   │   ├── clickhouse_client.py  # ClickHouse原生客户端
│   │   ├── models.py        # 元数据追踪 + DocumentState
│   │   ├── views.py         # REST API
│   │   └── tasks.py         # Celery任务
│   ├── tenants/             # 多租户 + JWT认证
│   └── workflows/           # FSM工作流（预留）
├── rust_engine/             # PyO3 Rust依赖分析引擎
│   └── src/lib.rs           # Kahn拓扑排序 + 循环检测
├── frontend/                # Vue 3 前端
│   └── src/pages/
│       ├── TableManager.vue # 动态表管理
│       ├── DataGrid.vue     # 数据视图
│       ├── CanvasEditor.vue # 依赖画布
│       └── Schedules.vue    # 定时任务
├── docker/                  # Nginx + Django Dockerfile
├── docker-compose.yml       # 7容器编排
└── hydra/                   # Django配置
```

---

## 🛠️ 技术栈

| 层级 | 技术 |
|---|---|
| 后端框架 | Django 6.0 + Django REST Framework |
| 数据库 | PostgreSQL 16（主存储）+ ClickHouse 24.8（分析） |
| 缓存/队列 | Redis 7（Channels + Celery Broker） |
| 实时协同 | y-py 0.6（Yjs CRDT）+ Django Channels 4 |
| 异步任务 | Celery 5 + django-celery-beat |
| 性能引擎 | Rust 1.97 + PyO3 0.29 |
| 多租户 | django-tenants（PostgreSQL Schema 隔离） |
| 认证 | djangorestframework-simplejwt |
| GraphQL | Strawberry Django（预留） |
| 前端 | Vue 3.5 + Vite 8 |
| 容器化 | Docker Compose（7 服务） |

---

## 📄 License

MIT
