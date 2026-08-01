"""
DynamicModelRegistry — keeps track of runtime-generated Django model classes.

Since we can't rely on Django's app registry for dynamic models (they don't
come from INSTALLED_APPS), we maintain our own mapping of table_name → Model class.
"""
from django.db import models


class DynamicModelRegistry:
    """Thread-safe registry for runtime-generated model classes."""

    def __init__(self):
        self._models: dict[str, type[models.Model]] = {}

    def register(self, table_name: str, model_class: type[models.Model]):
        """Register a dynamically generated model and connect signals."""
        self._models[table_name] = model_class
        # Connect post_save/post_delete signals for ClickHouse + WebSocket push
        from .signals import connect_model_signals
        connect_model_signals(model_class, table_name)

    def get(self, table_name: str) -> type[models.Model] | None:
        """Get a registered model by table name."""
        return self._models.get(table_name)

    def unregister(self, table_name: str):
        """Remove a model from the registry and disconnect signals."""
        if table_name in self._models:
            model_class = self._models.pop(table_name)
            # Disconnect signals
            from django.db.models.signals import post_save, post_delete
            post_save.disconnect(dispatch_uid=f"dynamic_save_{table_name}")
            post_delete.disconnect(dispatch_uid=f"dynamic_delete_{table_name}")

    def all(self) -> dict[str, type[models.Model]]:
        """Return all registered models."""
        return dict(self._models)

    def __contains__(self, table_name: str) -> bool:
        return table_name in self._models


# Global singleton
registry = DynamicModelRegistry()
