"""
DynamicModelManager — Runtime table creation & schema evolution for Plato.

THE HARD PROBLEM: PostgreSQL's CREATE TABLE is an implicit COMMIT.
If a tenant request fails mid-DDL, we get zombie tables that can't be rolled back.

OUR DEFENSE:
1. Pre-validation: validate the JSON schema BEFORE touching the database.
2. Savepoint wrapping: wrap DDL in a savepoint so we can catch errors.
3. Soft-delete columns: never DROP COLUMN — mark as deleted_at instead.
4. Schema isolation: ALL dynamic tables live in the `dynamic_data` schema.
5. Metadata table: track every dynamic table/column in DynamicTableMetadata.

Architecture:
    Frontend JSON Schema
        │
        ▼
    DynamicModelManager.validate_schema()  ← pre-validate
        │
        ▼
    DynamicModelManager.create_table()      ← DDL + metadata
        │
        ▼
    DynamicModelRegistry.register()         ← generate model class
        │
        ▼
    Django ORM can query the new table
"""
import logging
from dataclasses import dataclass, field
from typing import Any
from django.conf import settings
from django.db import connection, models, transaction, ProgrammingError
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.apps import apps

from .registry import DynamicModelRegistry
from .exceptions import (
    DynamicTableError,
    SchemaValidationError,
    TableAlreadyExistsError,
    ColumnLimitExceededError,
    InvalidColumnTypeError,
)

logger = logging.getLogger(__name__)

# ============================================================
# Column Type Definitions
# ============================================================

COLUMN_TYPE_MAP = settings.DYNAMIC_TABLE_ALLOWED_TYPES
MAX_COLUMNS = settings.DYNAMIC_TABLE_MAX_COLUMNS
DYNAMIC_SCHEMA = settings.DYNAMIC_TABLE_SCHEMA

# Reserved column names (can't be used as user-defined columns)
RESERVED_COLUMNS = {
    "id", "pk", "_pk", "created_at", "updated_at", "deleted_at",
    "_version", "_tenant_id",
}


@dataclass
class ColumnDef:
    """A single column definition from the frontend JSON schema."""
    name: str
    col_type: str          # key into COLUMN_TYPE_MAP
    nullable: bool = True
    default: Any = None
    max_length: int | None = None
    unique: bool = False
    index: bool = False


@dataclass
class TableSchema:
    """Complete table schema from the frontend JSON."""
    name: str
    display_name: str = ""
    description: str = ""
    columns: list[ColumnDef] = field(default_factory=list)


# ============================================================
# Core Manager
# ============================================================

class DynamicModelManager:
    """
    Orchestrates runtime table creation and schema evolution.

    Usage:
        manager = DynamicModelManager()
        schema = TableSchema(
            name="sales_leads",
            columns=[
                ColumnDef(name="company", col_type="string", nullable=False),
                ColumnDef(name="revenue", col_type="decimal"),
            ]
        )
        manager.create_table(schema)
    """

    def __init__(self):
        from .registry import registry
        self.registry = registry

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def create_table(self, schema: TableSchema) -> type[models.Model]:
        """
        Create a new dynamic table from a TableSchema.

        Returns the generated Django model class, registered and ready to use.

        Raises:
            SchemaValidationError: schema is invalid
            TableAlreadyExistsError: table name already taken
            ColumnLimitExceededError: too many columns
        """
        # Step 1: Validate
        self._validate_schema(schema)

        # Step 2: Create metadata entry
        with transaction.atomic():
            metadata = self._create_metadata(schema)

        # Step 3: Execute DDL (wrapped in savepoint — best effort)
        try:
            with transaction.atomic():
                sid = transaction.savepoint()
                try:
                    self._execute_ddl(schema)
                    transaction.savepoint_commit(sid)
                except Exception:
                    transaction.savepoint_rollback(sid)
                    raise
        except Exception as e:
            # DDL failed — mark metadata as failed, don't leave zombie table
            metadata.status = "failed"
            metadata.error_message = str(e)[:500]
            metadata.save(update_fields=["status", "error_message"])
            logger.error("DDL failed for table %s: %s", schema.name, e)
            raise DynamicTableError(
                f"Failed to create table '{schema.name}': {e}"
            ) from e

        # Step 4: Generate & register Django model
        model_class = self._build_model_class(schema)
        self.registry.register(schema.name, model_class)

        # Step 5: Update metadata status
        metadata.status = "active"
        metadata.save(update_fields=["status"])

        logger.info(
            "Dynamic table '%s' created successfully (%d columns)",
            schema.name,
            len(schema.columns),
        )
        return model_class

    def add_column(self, table_name: str, column: ColumnDef):
        """Add a column to an existing dynamic table."""
        self._validate_column(column, table_name=table_name)
        full_table = f'"{DYNAMIC_SCHEMA}"."{table_name}"'

        try:
            with connection.cursor() as cursor:
                sql_type = self._column_sql(column)
                nullable = "" if column.nullable else "NOT NULL"
                default_clause = self._default_clause(column)
                sql = f"ALTER TABLE {full_table} ADD COLUMN \"{column.name}\" {sql_type} {nullable} {default_clause}"
                cursor.execute(sql)

            self._add_column_metadata(table_name, column)
            logger.info("Added column '%s' to table '%s'", column.name, table_name)

        except Exception as e:
            logger.error("Failed to add column '%s' to '%s': %s", column.name, table_name, e)
            raise DynamicTableError(
                f"Failed to add column '{column.name}' to '{table_name}': {e}"
            ) from e

    def drop_column(self, table_name: str, column_name: str):
        """Soft-delete a column: rename it with _deleted_ prefix (no DROP, no lock)."""
        try:
            with connection.cursor() as cursor:
                full_table = f'"{DYNAMIC_SCHEMA}"."{table_name}"'
                old_name = column_name
                new_name = f"_deleted_{old_name}"
                sql = f'ALTER TABLE {full_table} RENAME COLUMN "{old_name}" TO "{new_name}"'
                cursor.execute(sql)

            self._soft_delete_column_metadata(table_name, column_name)
            logger.info("Soft-deleted column '%s' from table '%s'", column_name, table_name)

        except Exception as e:
            logger.error("Failed to drop column '%s' from '%s': %s", column_name, table_name, e)
            raise DynamicTableError(
                f"Failed to remove column '{column_name}' from '{table_name}': {e}"
            ) from e

    def list_tables(self) -> list[dict]:
        """List all active dynamic tables with their columns."""
        from .models import DynamicTableMetadata
        tables = DynamicTableMetadata.objects.filter(
            status="active"
        ).prefetch_related("columns")
        return [
            {
                "name": t.table_name,
                "display_name": t.display_name,
                "description": t.description,
                "columns": [
                    {
                        "name": c.column_name,
                        "type": c.column_type,
                        "nullable": c.nullable,
                        "is_deleted": c.is_deleted,
                    }
                    for c in t.columns.filter(is_deleted=False)
                ],
                "created_at": t.created_at.isoformat(),
            }
            for t in tables
        ]

    # ----------------------------------------------------------
    # Validation
    # ----------------------------------------------------------

    def _validate_schema(self, schema: TableSchema):
        """Full schema validation before touching the database."""
        # Sanitize: only allow lowercase letters, numbers, underscores, max 63 chars
        import re
        if not re.match(r'^[a-z][a-z0-9_]{0,62}$', schema.name):
            raise SchemaValidationError(
                f"Invalid table name: '{schema.name}'. "
                "Use lowercase letters, numbers, underscores (max 63 chars, start with letter)."
            )
        if schema.name in RESERVED_COLUMNS:
            raise SchemaValidationError(
                f"Table name '{schema.name}' is reserved."
            )
        if len(schema.columns) > MAX_COLUMNS:
            raise ColumnLimitExceededError(
                f"Max {MAX_COLUMNS} columns allowed, got {len(schema.columns)}."
            )
        if self._table_exists(schema.name):
            raise TableAlreadyExistsError(
                f"Table '{schema.name}' already exists."
            )

        seen = set()
        for col in schema.columns:
            self._validate_column(col)
            if col.name in seen:
                raise SchemaValidationError(
                    f"Duplicate column name: '{col.name}'"
                )
            seen.add(col.name)

    def _validate_column(self, column: ColumnDef, table_name: str = ""):
        """Validate a single column definition."""
        if column.name in RESERVED_COLUMNS:
            raise SchemaValidationError(
                f"Column name '{column.name}' is reserved."
            )
        if column.col_type not in COLUMN_TYPE_MAP:
            raise InvalidColumnTypeError(
                f"Unknown column type: '{column.col_type}'. "
                f"Allowed: {list(COLUMN_TYPE_MAP.keys())}"
            )

    # ----------------------------------------------------------
    # DDL Execution
    # ----------------------------------------------------------

    def _execute_ddl(self, schema: TableSchema):
        """Execute CREATE TABLE DDL directly on PostgreSQL."""
        full_table = f'"{DYNAMIC_SCHEMA}"."{schema.name}"'
        columns_sql = self._build_column_defs(schema)
        sql = f"CREATE TABLE {full_table} (\n{columns_sql}\n)"

        with connection.cursor() as cursor:
            try:
                cursor.execute(sql)
            except Exception:
                # Try to clean up if table was partially created
                try:
                    cursor.execute(
                        f"DROP TABLE IF EXISTS {full_table} CASCADE"
                    )
                except Exception:
                    pass
                raise

    def _build_column_defs(self, schema: TableSchema) -> str:
        """Build the SQL column definitions from schema."""
        defs = [
            "    id          BIGSERIAL PRIMARY KEY",
            "    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()",
            "    updated_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()",
            "    _version    INTEGER DEFAULT 1",
        ]
        for col in schema.columns:
            col_sql = self._column_sql(col)
            nullable = "NULL" if col.nullable else "NOT NULL"
            default = self._default_clause(col)
            defs.append(f'    "{col.name}"  {col_sql} {nullable} {default}'.strip())
        return ",\n".join(defs)

    def _column_sql(self, column: ColumnDef) -> str:
        """Map ColumnDef to PostgreSQL column type."""
        base = COLUMN_TYPE_MAP[column.col_type]
        if column.col_type == "string" and column.max_length:
            return f"VARCHAR({column.max_length})"
        return base

    def _default_clause(self, column: ColumnDef) -> str:
        """Build DEFAULT clause for a column."""
        if column.default is None:
            return ""
        if isinstance(column.default, str):
            # Escape single quotes
            escaped = column.default.replace("'", "''")
            return f"DEFAULT '{escaped}'"
        if isinstance(column.default, bool):
            return f"DEFAULT {'TRUE' if column.default else 'FALSE'}"
        return f"DEFAULT {column.default}"

    # ----------------------------------------------------------
    # Model Class Generation
    # ----------------------------------------------------------

    def _build_model_class(self, schema: TableSchema) -> type[models.Model]:
        """
        Dynamically generate a Django Model class for the new table.

        Uses Python's type() metaclass to create the model at runtime,
        attaching field instances that map to the physical columns.
        """
        full_table = f'"{DYNAMIC_SCHEMA}"."{schema.name}"'

        # Build model attributes dict
        attrs: dict[str, Any] = {
            "__module__": "__dynamic_models__",  # Avoid Django app registry
            "Meta": type(
                "Meta",
                (),
                {
                    "db_table": full_table,
                    "managed": False,  # Don't let Django manage migrations
                    "app_label": "dynamic_models",
                },
            ),
            # System fields
            "id": models.BigAutoField(primary_key=True),
            "created_at": models.DateTimeField(auto_now_add=True),
            "updated_at": models.DateTimeField(auto_now=True),
            "_version": models.IntegerField(default=1),
        }

        # Map column types to Django fields
        for col in schema.columns:
            attrs[col.name] = self._column_to_field(col)

        # Create the class
        model_class = type(
            schema.name.title().replace("_", ""),  # PascalCase class name
            (models.Model,),
            attrs,
        )
        return model_class

    def _column_to_field(self, column: ColumnDef) -> models.Field:
        """Map ColumnDef to a Django model field."""
        field_kwargs = {
            "null": column.nullable,
            "blank": column.nullable,
        }
        if column.default is not None:
            field_kwargs["default"] = column.default

        field_map = {
            "string": models.CharField,
            "text": models.TextField,
            "integer": models.IntegerField,
            "bigint": models.BigIntegerField,
            "float": models.FloatField,
            "decimal": models.DecimalField,
            "boolean": models.BooleanField,
            "date": models.DateField,
            "datetime": models.DateTimeField,
            "json": models.JSONField,
            "uuid": models.UUIDField,
        }

        field_cls = field_map.get(column.col_type)
        if field_cls is None:
            raise InvalidColumnTypeError(
                f"No Django field mapping for '{column.col_type}'"
            )

        # Type-specific kwargs
        if column.col_type == "string":
            field_kwargs["max_length"] = column.max_length or 255
        elif column.col_type == "decimal":
            field_kwargs["max_digits"] = 18
            field_kwargs["decimal_places"] = 4

        return field_cls(**field_kwargs)

    # ----------------------------------------------------------
    # Metadata Management
    # ----------------------------------------------------------

    def _create_metadata(self, schema: TableSchema):
        """Create the metadata tracking record."""
        from .models import DynamicTableMetadata, DynamicColumnMetadata
        metadata = DynamicTableMetadata.objects.create(
            table_name=schema.name,
            display_name=schema.display_name or schema.name,
            description=schema.description,
            status="creating",
        )
        for col in schema.columns:
            DynamicColumnMetadata.objects.create(
                table=metadata,
                column_name=col.name,
                column_type=col.col_type,
                nullable=col.nullable,
                default_value=str(col.default) if col.default is not None else None,
            )
        return metadata

    def _add_column_metadata(self, table_name: str, column: ColumnDef):
        from .models import DynamicTableMetadata, DynamicColumnMetadata
        metadata = DynamicTableMetadata.objects.get(table_name=table_name)
        DynamicColumnMetadata.objects.create(
            table=metadata,
            column_name=column.name,
            column_type=column.col_type,
            nullable=column.nullable,
        )

    def _soft_delete_column_metadata(self, table_name: str, column_name: str):
        from .models import DynamicTableMetadata, DynamicColumnMetadata
        metadata = DynamicTableMetadata.objects.get(table_name=table_name)
        DynamicColumnMetadata.objects.filter(
            table=metadata,
            column_name=column_name,
        ).update(is_deleted=True, deleted_at=models.functions.Now())

    def _table_exists(self, table_name: str) -> bool:
        """Check if a dynamic table already exists (metadata or physical)."""
        from .models import DynamicTableMetadata
        # Check metadata
        if DynamicTableMetadata.objects.filter(
            table_name=table_name, status__in=("active", "creating")
        ).exists():
            return True
        # Check physical table
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.tables "
                "  WHERE table_schema = %s AND table_name = %s"
                ")",
                [DYNAMIC_SCHEMA, table_name],
            )
            return cursor.fetchone()[0]


# Singleton instance
dynamic_model_manager = DynamicModelManager()
