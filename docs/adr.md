# Architecture Decision Records (ADR)

## ADR-001: PostgreSQL Schema 多租户隔离

**状态**: 已采纳  
**日期**: 2026-08-01  
**决策者**: Plato 团队

### 背景
需要支持多个组织（租户）在同一套代码和数据基础设施上运行，且数据完全隔离。

### 决策
使用 `django-tenants` 实现 PostgreSQL Schema 级别的多租户隔离。每个租户拥有独立的 PostgreSQL Schema，共享应用使用 `public` Schema。

### 替代方案
- **行级隔离（tenant_id 字段）**: 实现简单，但每条查询都需要 WHERE 过滤，性能差且容易漏过滤导致数据泄露。
- **独立数据库**: 隔离性最好，但运维成本高，管理 N 个数据库的迁移和备份复杂。

### 后果
- ✅ 数据隔离由数据库层面保证
- ✅ 迁移管理清晰（shared vs tenant 迁移分离）
- ❌ PostgreSQL Schema 数量有限制（理论 ~2^31，实际建议 < 1000）
- ❌ 动态元数据表（DynamicTableMetadata）必须放在 SHARED_APPS 以避免迁移路由问题

---

## ADR-002: Yjs CRDT 替代 OT 算法

**状态**: 已采纳  
**日期**: 2026-08-01

### 背景
实时协同编辑需要解决多人同时操作同一数据时的冲突问题。

### 决策
使用 Yjs CRDT（Conflict-free Replicated Data Type）替代传统的 OT（Operational Transformation）算法。后端使用 `y-py`（Yjs 的 Python 实现），通过 Django Channels WebSocket 传输二进制更新。

### 替代方案
- **手写 OT**: 实现极其复杂（需处理操作变换、意图保留），且 Google Docs 的 OT 实现有专利风险。
- **ShareDB（JSON OT）**: Node.js 生态，与 Django 集成困难。

### 后果
- ✅ CRDT 无需中央服务器仲裁冲突，离线操作天然支持
- ✅ y-py 性能优异（Rust 实现）
- ❌ Yjs 二进制协议在 WebSocket 上需要自定义帧格式（0x00/0x01/0x02）
- ❌ y-py YDoc 实例线程绑定（Rust 限制），多 Worker 需 Redis Pub/Sub 桥接

---

## ADR-003: Rust/PyO3 性能引擎

**状态**: 已采纳  
**日期**: 2026-08-01

### 背景
公式列的依赖解析需要拓扑排序，Python 实现在大规模（1000+ 列）场景下性能不足。

### 决策
用 Rust 编写拓扑排序引擎，通过 PyO3 编译为 Python 原生扩展（.so）。使用 Kahn 算法实现 O(V+E) 时间复杂度的拓扑排序，同时进行循环检测和分层分组。

### 替代方案
- **纯 Python**: 开发快但性能差（GIL 限制）
- **Cython**: 语法接近 Python 但调试困难
- **Go + gRPC**: 进程间通信开销大

### 后果
- ✅ 原生性能（直接调用，无 IPC 开销）
- ✅ Rust 编译器保证内存安全
- ❌ 需要 Rust 工具链（cargo + maturin）
- ❌ CI 需要额外的 Rust 编译步骤

---

## ADR-004: ClickHouse 冷热数据分离

**状态**: 已采纳  
**日期**: 2026-08-01

### 背景
动态表的历史变更记录可能非常庞大（每天数十万行），全部存在 PostgreSQL 中会影响热数据查询性能。

### 决策
PostgreSQL 存储当前数据（热数据），ClickHouse 存储历史事件日志（冷数据）。通过 Celery 异步任务将变更事件推送到 ClickHouse，ClickHouse 表设置 90 天 TTL 自动清理。

### 替代方案
- **PostgreSQL 分区表**: 运维简单，但分析查询性能远不如 ClickHouse
- **TimescaleDB**: PostgreSQL 扩展，分析能力强但冷数据压缩不如 ClickHouse

### 后果
- ✅ ClickHouse 列存储在分析查询上比 PG 快 10-100x
- ✅ 自动 TTL 清理无需运维介入
- ❌ 双写一致性需要补偿机制（PG 成功但 CH 失败时）
- ❌ 增加了一个基础设施组件的运维复杂度

---

## ADR-005: Celery DatabaseScheduler 动态定时任务

**状态**: 已采纳  
**日期**: 2026-08-01

### 背景
用户需要在前端界面上动态创建/删除定时任务（如"每天凌晨 2 点重新计算公式列"），而不能重启 Celery Beat。

### 决策
使用 `django-celery-beat` 的 DatabaseScheduler，通过 ORM 操作 PeriodTask / CrontabSchedule / IntervalSchedule 模型来动态管理定时任务，无需重启进程。

### 替代方案
- **Celery Beat 文件配置**: 安全可靠，但修改需要重启
- **Redis + custom scheduler**: 灵活但需要自己实现复杂的调度逻辑

### 后果
- ✅ 前端 CRUD 定时任务无需后端重启
- ✅ 支持 crontab 和 interval 两种调度方式
- ❌ DatabaseScheduler 有同步开销（每 N 秒查一次数据库）
- ❌ 修改后的任务需要等一个 beat 周期才能生效

---

## ADR-006: 表达式安全沙箱

**状态**: 已采纳  
**日期**: 2026-08-01

### 背景
用户需要定义计算公式（如 `revenue - cost`），但直接执行用户输入的 Python 代码存在严重安全风险。

### 决策
使用 AST（抽象语法树）白名单方案：将用户表达式解析为 AST，白名单检查每个节点类型（只允许 BinOp、Name、Constant 等安全节点），然后在受限的 builtins 环境中执行。

### 替代方案
- **自定义 DSL**: 最安全，但实现复杂且表达能力受限
- **Django 模板引擎 eval**: 不够灵活
- **RestrictedPython**: 包依赖重，且维护不活跃

### 后果
- ✅ 阻止了 `__import__`、`eval`、`exec`、`open` 等危险调用
- ✅ 支持常见数学和字符串操作
- ❌ 白名单可能遗漏新的攻击向量，需要定期审查
- ❌ 不支持函数定义和复杂控制流
