"""
Metadata models for tracking dynamic tables and their columns.

These are regular Django models that live in the tenant schema.
They track the structure of all runtime-created tables so we can:
1. Rebuild model classes on server restart
2. Track soft-deleted columns
3. Provide schema introspection for the frontend
"""
from django.db import models


class DynamicTableMetadata(models.Model):
    """Tracks every runtime-created dynamic table."""

    table_name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Physical table name in the dynamic_data schema",
    )
    display_name = models.CharField(
        max_length=300,
        help_text="Human-readable name shown in the UI",
    )
    description = models.TextField(blank=True, default="")

    STATUS_CHOICES = [
        ("creating", "Creating"),
        ("active", "Active"),
        ("failed", "Failed"),
        ("archived", "Archived"),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="creating",
    )
    error_message = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "dynamic_table_metadata"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["table_name"]),
        ]

    def __str__(self):
        return f"{self.table_name} ({self.status})"


class DynamicColumnMetadata(models.Model):
    """Tracks columns of each dynamic table."""

    table = models.ForeignKey(
        DynamicTableMetadata,
        on_delete=models.CASCADE,
        related_name="columns",
    )
    column_name = models.CharField(max_length=200)
    column_type = models.CharField(
        max_length=50,
        help_text="Type key from DYNAMIC_TABLE_ALLOWED_TYPES",
    )
    nullable = models.BooleanField(default=True)
    default_value = models.TextField(null=True, blank=True)
    max_length = models.IntegerField(null=True, blank=True)

    # Soft delete support
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    position = models.IntegerField(default=0, help_text="Column display order")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dynamic_column_metadata"
        ordering = ["table", "position"]
        unique_together = [("table", "column_name")]
        indexes = [
            models.Index(fields=["table", "is_deleted"]),
        ]

    def __str__(self):
        deleted = " [DELETED]" if self.is_deleted else ""
        return f"{self.table.table_name}.{self.column_name} ({self.column_type}){deleted}"


class DocumentState(models.Model):
    """Persisted Yjs document state for collaborative table editing.

    Each dynamic table that has collaborative editing gets one row here.
    The ydoc_state field stores the full Yjs update encoding as binary,
    which can be replayed to reconstruct the Y.Doc on server restart.
    """
    table_name = models.CharField(
        max_length=200,
        unique=True,
        help_text="The dynamic table this Yjs document belongs to",
    )
    ydoc_state = models.BinaryField(
        help_text="Full Yjs document state encoded as update bytes",
    )
    version = models.IntegerField(
        default=1,
        help_text="Monotonic version counter for conflict detection",
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "document_state"
        indexes = [
            models.Index(fields=["table_name"]),
        ]

    def __str__(self):
        return f"YDoc({self.table_name} v{self.version} {len(self.ydoc_state)}b)"
