"""
ClickHouse client — native connection for cold-data analytics.

Bypasses Django ORM entirely. Uses clickhouse-connect directly.
"""
import logging
from contextlib import contextmanager
from typing import Any
from django.conf import settings
import clickhouse_connect

logger = logging.getLogger(__name__)

_ch_client = None


def get_client():
    """Get or create the ClickHouse client (lazy init)."""
    global _ch_client
    if _ch_client is None:
        cfg = settings.CLICKHOUSE_CONFIG
        _ch_client = clickhouse_connect.get_client(
            host=cfg["host"],
            port=cfg["port"],
            username=cfg["username"],
            password=cfg["password"],
            database=cfg["database"],
            connect_timeout=cfg["connect_timeout"],
            send_receive_timeout=cfg["send_receive_timeout"],
        )
        logger.info("ClickHouse client connected to %s:%s", cfg["host"], cfg["port"])
    return _ch_client


@contextmanager
def ch_client():
    """Context manager for ClickHouse client operations."""
    client = get_client()
    try:
        yield client
    except Exception:
        global _ch_client
        _ch_client = None
        raise


def insert_event_log(
    tenant_schema: str,
    table_name: str,
    event_type: str,
    row_id: str,
    new_data: dict,
    old_data: dict | None = None,
    changed_by: str = "",
) -> None:
    """
    Insert a change event into the ClickHouse event log.

    Args:
        tenant_schema: The PostgreSQL schema name (tenant identifier)
        table_name: The dynamic table name
        event_type: 'INSERT', 'UPDATE', or 'DELETE'
        row_id: The row's primary key
        new_data: The new row data as dict
        old_data: Previous data (for UPDATE/DELETE)
        changed_by: User ID who made the change
    """
    import json

    event_map = {"INSERT": 1, "UPDATE": 2, "DELETE": 3}

    with ch_client() as client:
        client.insert(
            "dynamic_table_event_log",
            [[
                tenant_schema,
                table_name,
                event_map.get(event_type, 1),
                str(row_id),
                json.dumps(old_data or {}),
                json.dumps(new_data),
                changed_by,
            ]],
            column_names=[
                "tenant_schema",
                "table_name",
                "event_type",
                "row_id",
                "old_data",
                "new_data",
                "changed_by",
            ],
        )


def query_event_log(
    tenant_schema: str,
    table_name: str,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """
    Query the ClickHouse event log for a specific table.

    Returns list of event dicts.
    """
    import json

    conditions = [
        f"tenant_schema = '{tenant_schema}'",
        f"table_name = '{table_name}'",
    ]
    if start_time:
        conditions.append(f"event_time >= '{start_time}'")
    if end_time:
        conditions.append(f"event_time <= '{end_time}'")

    where = " AND ".join(conditions)
    sql = f"""
        SELECT event_id, event_type, row_id, old_data, new_data, changed_by, event_time
        FROM dynamic_table_event_log
        WHERE {where}
        ORDER BY event_time DESC
        LIMIT {limit}
    """

    with ch_client() as client:
        result = client.query(sql)
        rows = []
        for row in result.named_results():
            rows.append({
                "event_id": str(row["event_id"]),
                "event_type": str(row["event_type"])
                if row["event_type"] not in ("", None)
                else "UNKNOWN",
                "row_id": row["row_id"],
                "old_data": json.loads(row["old_data"]) if row["old_data"] else {},
                "new_data": json.loads(row["new_data"]) if row["new_data"] else {},
                "changed_by": row["changed_by"],
                "event_time": row["event_time"].isoformat(),
            })
        return rows
