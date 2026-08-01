"""App config for dynamic_models — reload models on startup."""
import logging
import sys
from django.apps import AppConfig

logger = logging.getLogger(__name__)


class DynamicModelsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.dynamic_models"
    verbose_name = "Dynamic Models"

    def ready(self):
        # Skip dynamic model reload during migration commands
        if any(cmd in sys.argv for cmd in ("makemigrations", "migrate", "sqlmigrate", "showmigrations")):
            logger.debug("Skipping dynamic model reload (migration command)")
            return

        self._reload_dynamic_models()

    def _reload_dynamic_models(self):
        """Rebuild model classes for all active dynamic tables."""
        from .models import DynamicTableMetadata
        from .manager import dynamic_model_manager, ColumnDef, TableSchema

        try:
            active_tables = DynamicTableMetadata.objects.filter(
                status="active"
            ).prefetch_related("columns")

            count = 0
            for table_meta in active_tables:
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
                        description=table_meta.description,
                        columns=columns,
                    )
                    model_class = dynamic_model_manager._build_model_class(schema)
                    dynamic_model_manager.registry.register(
                        table_meta.table_name, model_class
                    )
                    count += 1
                except Exception as e:
                    logger.error(
                        "Failed to reload dynamic table '%s': %s",
                        table_meta.table_name, e,
                    )

            if count > 0:
                logger.info("Reloaded %d dynamic table(s) on startup", count)

        except Exception as e:
            logger.debug("Skipping dynamic model reload: %s", e)
