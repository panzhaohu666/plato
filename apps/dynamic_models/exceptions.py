"""
Custom exceptions for the dynamic_models app.
"""


class DynamicTableError(Exception):
    """Base exception for dynamic table operations."""


class SchemaValidationError(DynamicTableError):
    """Schema validation failed — fix the JSON and retry."""


class TableAlreadyExistsError(DynamicTableError):
    """A table with this name already exists."""


class TableNotFoundError(DynamicTableError):
    """The requested dynamic table does not exist."""


class ColumnLimitExceededError(DynamicTableError):
    """Requested column count exceeds the maximum."""


class InvalidColumnTypeError(DynamicTableError):
    """The column type is not in the allowed types list."""


class ColumnAlreadyExistsError(DynamicTableError):
    """A column with this name already exists in the table."""
