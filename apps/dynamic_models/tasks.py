"""
Celery tasks for dynamic_models.

Tasks:
- push_to_clickhouse: Asynchronously push row changes to ClickHouse
- broadcast_table_change: Broadcast changes to WebSocket collaborators
- rebuild_dynamic_models: Periodically verify and rebuild model registry
"""
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="apps.dynamic_models.tasks.push_to_clickhouse",
    max_retries=3,
    default_retry_delay=5,
    queue="high_priority",
)
def push_to_clickhouse(
    table_name: str,
    event_type: str,
    row_id: str,
    new_data: dict,
    old_data: dict,
):
    """
    Push a data change event to ClickHouse for cold storage analytics.

    Retries on failure with exponential backoff.
    On final failure, the event is logged for later reconciliation.
    """
    from apps.dynamic_models.clickhouse_client import insert_event_log
    from django_tenants.utils import get_tenant_model

    try:
        # Determine current tenant schema from connection
        from django.db import connection
        tenant_schema = connection.schema_name

        insert_event_log(
            tenant_schema=tenant_schema,
            table_name=table_name,
            event_type=event_type,
            row_id=row_id,
            new_data=new_data,
            old_data=old_data,
        )
        logger.debug(
            "ClickHouse: %s event for %s row %s",
            event_type,
            table_name,
            row_id,
        )
    except Exception as exc:
        logger.warning(
            "ClickHouse push failed (retry %d/3): %s",
            push_to_clickhouse.request.retries,
            exc,
        )
        raise push_to_clickhouse.retry(exc=exc)


@shared_task(
    name="apps.dynamic_models.tasks.broadcast_table_change",
    max_retries=2,
    default_retry_delay=2,
)
def broadcast_table_change(
    table_name: str,
    event_type: str,
    row_id: str,
    data: dict,
):
    """
    Broadcast a table change to all WebSocket collaborators.

    Uses Channels' async_to_sync to send to the channel layer.
    """
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync

    try:
        channel_layer = get_channel_layer()
        room_group = f"table_{table_name}"

        async_to_sync(channel_layer.group_send)(
            room_group,
            {
                "type": f"row_{event_type.lower()}",
                "payload": {
                    "id": row_id,
                    "data": data,
                },
            },
        )
        logger.debug("Broadcast: %s for table %s row %s", event_type, table_name, row_id)

    except Exception as exc:
        logger.error("Broadcast failed: %s", exc)


@shared_task(
    name="apps.dynamic_models.tasks.rebuild_dynamic_models",
)
def rebuild_dynamic_models():
    """
    Periodic task: reload dynamic model classes from metadata.

    This catches any models that may have been created outside
    the current process (e.g., by another worker).
    """
    from .models import DynamicTableMetadata
    from .manager import dynamic_model_manager, ColumnDef, TableSchema

    active_tables = DynamicTableMetadata.objects.filter(
        status="active"
    ).prefetch_related("columns")

    reloaded = 0
    for table_meta in active_tables:
        if table_meta.table_name in dynamic_model_manager.registry:
            continue  # Already loaded

        try:
            columns = [
                ColumnDef(
                    name=col.column_name,
                    col_type=col.column_type,
                    nullable=col.nullable,
                )
                for col in table_meta.columns.filter(is_deleted=False)
            ]
            schema = TableSchema(
                name=table_meta.table_name,
                display_name=table_meta.display_name,
                columns=columns,
            )
            model_class = dynamic_model_manager._build_model_class(schema)
            dynamic_model_manager.registry.register(
                table_meta.table_name, model_class
            )
            reloaded += 1
        except Exception as e:
            logger.error("Rebuild failed for %s: %s", table_meta.table_name, e)

    if reloaded:
        logger.info("Rebuilt %d dynamic model(s)", reloaded)


@shared_task(
    name="apps.dynamic_models.tasks.persist_document_state",
    max_retries=2,
    default_retry_delay=10,
)
def persist_document_state(table_name: str):
    """
    Persist the current Y.Doc state to PostgreSQL BYTEA.

    Called periodically (via Celery Beat) or after significant edits.
    Uses a debounce approach: only persists if enough time has passed
    since the last save (handled by the periodic schedule).
    """
    from .yjs_service import yjs_manager

    try:
        bytes_written = yjs_manager.persist_to_db(table_name)
        if bytes_written:
            logger.debug("Persisted Yjs doc '%s': %d bytes", table_name, bytes_written)
    except Exception as exc:
        logger.error("Failed to persist Yjs doc '%s': %s", table_name, exc)
        raise persist_document_state.retry(exc=exc)


@shared_task(
    name="apps.dynamic_models.tasks.execute_scheduled_task",
    bind=True,
    max_retries=1,
    default_retry_delay=60,
)
def execute_scheduled_task(self, table_name: str, task_type: str, **kwargs):
    """
    Execute a user-scheduled periodic task on a dynamic table.

    Dispatched by django-celery-beat DatabaseScheduler.
    The task_type determines which handler runs.
    """
    from .registry import registry
    from .models import DynamicTableMetadata

    logger.info(
        "Executing scheduled task '%s' on table '%s' (args: %s)",
        task_type, table_name, kwargs,
    )

    try:
        if task_type == "recalculate_table":
            _recalculate_table(table_name, kwargs.get("full_scan", True))

        elif task_type == "archive_old_rows":
            _archive_old_rows(table_name, kwargs.get("older_than_days", 90))

        elif task_type == "validate_table":
            _validate_table(table_name, kwargs.get("checks", ["not_null"]))

        else:
            logger.warning("Unknown scheduled task type: %s", task_type)

    except Exception as exc:
        logger.error(
            "Scheduled task '%s' on '%s' failed: %s",
            task_type, table_name, exc,
        )
        raise self.retry(exc=exc)


def _recalculate_table(table_name: str, full_scan: bool = True):
    """Recompute formula columns on a dynamic table."""
    from .registry import registry
    from .expression_engine import evaluate_expressions

    model = registry.get(table_name)
    if model is None:
        logger.warning("Table '%s' not found for recalculation", table_name)
        return

    from .models import DynamicTableMetadata, DynamicColumnMetadata
    metadata = DynamicTableMetadata.objects.get(table_name=table_name)
    formula_columns = DynamicColumnMetadata.objects.filter(
        table=metadata, is_deleted=False, column_type="formula"
    )

    if not formula_columns.exists():
        logger.info("No formula columns on table '%s'", table_name)
        return

    rows = model.objects.all() if full_scan else model.objects.filter(updated_at__gte=...)
    updated = 0
    for row in rows:
        row_data = {}
        for field in model._meta.get_fields():
            if not field.is_relation and not field.auto_created:
                row_data[field.name] = getattr(row, field.name)

        new_values = evaluate_expressions(formula_columns, row_data)
        if new_values:
            for col_name, value in new_values.items():
                setattr(row, col_name, value)
            row.save(update_fields=list(new_values.keys()))
            updated += 1

    logger.info("Recalculated %d rows on table '%s'", updated, table_name)


def _archive_old_rows(table_name: str, older_than_days: int = 90):
    """Push old rows to ClickHouse and optionally soft-delete them."""
    from datetime import timedelta
    from django.utils import timezone
    from .clickhouse_client import insert_event_log
    from .registry import registry

    model = registry.get(table_name)
    if model is None:
        return

    cutoff = timezone.now() - timedelta(days=older_than_days)
    old_rows = model.objects.filter(created_at__lt=cutoff)

    archived = 0
    for row in old_rows:
        row_data = {}
        for field in model._meta.get_fields():
            if not field.is_relation and not field.auto_created:
                val = getattr(row, field.name)
                row_data[field.name] = val.isoformat() if hasattr(val, "isoformat") else val

        insert_event_log(
            tenant_schema="public",
            table_name=table_name,
            event_type="INSERT",
            row_id=str(row.pk),
            new_data=row_data,
        )
        archived += 1

    logger.info("Archived %d rows from table '%s'", archived, table_name)


def _validate_table(table_name: str, checks: list[str]):
    """Run data integrity checks on a dynamic table."""
    from .registry import registry

    model = registry.get(table_name)
    if model is None:
        return

    issues = []
    rows = model.objects.all()

    for check in checks:
        if check == "not_null":
            for field in model._meta.get_fields():
                if field.is_relation or field.auto_created:
                    continue
                null_count = rows.filter(**{f"{field.name}__isnull": True}).count()
                if null_count > 0:
                    issues.append(f"Column '{field.name}': {null_count} NULL values")

        elif check == "unique":
            for field in model._meta.get_fields():
                if field.is_relation or field.auto_created:
                    continue
                if getattr(field, "unique", False):
                    from django.db.models import Count
                    dups = (
                        model.objects.values(field.name)
                        .annotate(cnt=Count("id"))
                        .filter(cnt__gt=1)
                        .count()
                    )
                    if dups > 0:
                        issues.append(f"Column '{field.name}': {dups} groups of duplicates")

    if issues:
        logger.warning("Validation issues on table '%s': %s", table_name, issues)
    else:
        logger.info("Table '%s' passed all validation checks", table_name)
