"""
Signal handlers for dynamic_models.

Monitors dynamic table row changes and:
1. Pushes change events to ClickHouse via Celery task
2. Broadcasts changes to WebSocket collaborators
"""
import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)

# Signal handlers are registered lazily when a dynamic model is created.
# We can't use @receiver decorator because the model class doesn't exist at import time.
# Instead, the DynamicModelRegistry connects signals when registering a new model.


def connect_model_signals(model_class, table_name: str):
    """Connect post_save/post_delete signals for a dynamic model."""

    @receiver(post_save, sender=model_class, weak=False, dispatch_uid=f"dynamic_save_{table_name}")
    def on_row_save(sender, instance, created, **kwargs):
        _handle_row_change(table_name, instance, created=created)

    @receiver(post_delete, sender=model_class, weak=False, dispatch_uid=f"dynamic_delete_{table_name}")
    def on_row_delete(sender, instance, **kwargs):
        _handle_row_change(table_name, instance, created=False, deleted=True)


def _handle_row_change(table_name: str, instance, created: bool = False, deleted: bool = False):
    """
    Handle a row change: push to ClickHouse and broadcast via Channels.
    This is the hook point for Celery task dispatch.
    """
    from apps.dynamic_models.tasks import push_to_clickhouse, broadcast_table_change

    row_id = str(instance.pk)
    data = _instance_to_dict(instance)

    if deleted:
        event_type = "DELETE"
        new_data = {}
        old_data = data
    elif created:
        event_type = "INSERT"
        new_data = data
        old_data = None
    else:
        event_type = "UPDATE"
        new_data = data
        old_data = None  # Could fetch old state with django-pghistory

    # Push to ClickHouse asynchronously
    push_to_clickhouse.delay(
        table_name=table_name,
        event_type=event_type,
        row_id=row_id,
        new_data=new_data,
        old_data=old_data or {},
    )

    # Broadcast to WebSocket collaborators
    broadcast_table_change.delay(
        table_name=table_name,
        event_type=event_type,
        row_id=row_id,
        data=data,
    )


def _instance_to_dict(instance) -> dict:
    """Convert a dynamic model instance to a JSON-safe dict."""
    data = {}
    for field in instance._meta.get_fields():
        if field.is_relation or field.auto_created:
            continue
        value = getattr(instance, field.name, None)
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        elif isinstance(value, bytes):
            value = value.hex()
        data[field.name] = value
    return data
