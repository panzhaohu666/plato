-- ClickHouse initialization for Plato
CREATE DATABASE IF NOT EXISTS hydra_analytics;

-- Event log for dynamic table changes (cold storage)
CREATE TABLE IF NOT EXISTS hydra_analytics.dynamic_table_event_log (
    event_id        UUID DEFAULT generateUUIDv4(),
    tenant_schema   LowCardinality(String),
    table_name      LowCardinality(String),
    event_type      Enum8('INSERT' = 1, 'UPDATE' = 2, 'DELETE' = 3),
    row_id          String,
    old_data        String DEFAULT '',   -- JSON, only for UPDATE/DELETE
    new_data        String,              -- JSON snapshot
    changed_by      String DEFAULT '',
    event_time      DateTime64(3) DEFAULT now64(3),
    INDEX idx_tenant_schema tenant_schema TYPE minmax GRANULARITY 1,
    INDEX idx_table_name table_name TYPE minmax GRANULARITY 1,
    INDEX idx_event_time event_time TYPE minmax GRANULARITY 1
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_time)
ORDER BY (tenant_schema, table_name, event_time)
TTL toDateTime(event_time) + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;
