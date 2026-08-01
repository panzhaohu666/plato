"""
REST API for dynamic table CRUD operations.

Endpoints:
    POST   /api/tables/              — Create a new dynamic table
    GET    /api/tables/              — List all dynamic tables
    GET    /api/tables/{name}/       — Get table metadata
    DELETE /api/tables/{name}/       — Archive a dynamic table
    POST   /api/tables/{name}/rows/  — Insert row into dynamic table
    GET    /api/tables/{name}/rows/  — Query rows with filters
    PUT    /api/tables/{name}/rows/{id}/ — Update a row
    DELETE /api/tables/{name}/rows/{id}/ — Delete a row
    POST   /api/tables/{name}/columns/ — Add column to existing table
    DELETE /api/tables/{name}/columns/{col}/ — Soft-delete a column
"""
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .manager import dynamic_model_manager, ColumnDef, TableSchema
from .registry import registry
from .exceptions import DynamicTableError, SchemaValidationError


# ============================================================
# Table Management
# ============================================================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_table(request):
    """
    Create a new dynamic table.

    Request body:
    {
        "name": "sales_leads",
        "display_name": "Sales Leads",
        "description": "Track sales pipeline",
        "columns": [
            {"name": "company", "col_type": "string", "nullable": false},
            {"name": "revenue", "col_type": "decimal", "default": 0}
        ]
    }
    """
    try:
        schema = _parse_schema(request.data)
        model_class = dynamic_model_manager.create_table(schema)
        return Response(
            {
                "success": True,
                "table_name": schema.name,
                "message": f"Table '{schema.name}' created successfully",
            },
            status=status.HTTP_201_CREATED,
        )
    except SchemaValidationError as e:
        return Response(
            {"success": False, "error": str(e)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except DynamicTableError as e:
        return Response(
            {"success": False, "error": str(e)},
            status=status.HTTP_409_CONFLICT,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_tables(request):
    """List all active dynamic tables with their column schemas."""
    tables = dynamic_model_manager.list_tables()
    return Response({"success": True, "tables": tables})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_table(request, table_name: str):
    """Get metadata for a specific dynamic table."""
    tables = dynamic_model_manager.list_tables()
    table = next((t for t in tables if t["name"] == table_name), None)
    if table is None:
        return Response(
            {"success": False, "error": f"Table '{table_name}' not found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response({"success": True, "table": table})


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def archive_table(request, table_name: str):
    """Archive (soft-delete) a dynamic table."""
    from .models import DynamicTableMetadata
    try:
        meta = DynamicTableMetadata.objects.get(table_name=table_name)
        meta.status = "archived"
        meta.save(update_fields=["status"])
        registry.unregister(table_name)
        return Response(
            {"success": True, "message": f"Table '{table_name}' archived"},
        )
    except DynamicTableMetadata.DoesNotExist:
        return Response(
            {"success": False, "error": f"Table '{table_name}' not found"},
            status=status.HTTP_404_NOT_FOUND,
        )


# ============================================================
# Column Management
# ============================================================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_column(request, table_name: str):
    """Add a column to an existing dynamic table."""
    try:
        col_def = ColumnDef(**request.data)
        dynamic_model_manager.add_column(table_name, col_def)
        return Response(
            {"success": True, "message": f"Column '{col_def.name}' added"},
            status=status.HTTP_201_CREATED,
        )
    except DynamicTableError as e:
        return Response(
            {"success": False, "error": str(e)},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_column(request, table_name: str, column_name: str):
    """Soft-delete a column from a dynamic table."""
    try:
        dynamic_model_manager.drop_column(table_name, column_name)
        return Response(
            {"success": True, "message": f"Column '{column_name}' removed"},
        )
    except DynamicTableError as e:
        return Response(
            {"success": False, "error": str(e)},
            status=status.HTTP_400_BAD_REQUEST,
        )


def _get_model_or_load(table_name: str):
    """Get model from registry, or load from DB if not in memory."""
    model = registry.get(table_name)
    if model is not None:
        return model

    from .models import DynamicTableMetadata
    from .manager import dynamic_model_manager, ColumnDef, TableSchema
    try:
        meta = DynamicTableMetadata.objects.get(table_name=table_name, status="active")
        columns = [
            ColumnDef(name=c.column_name, col_type=c.column_type, nullable=c.nullable)
            for c in meta.columns.filter(is_deleted=False)
        ]
        schema = TableSchema(name=meta.table_name, columns=columns)
        model = dynamic_model_manager._build_model_class(schema)
        registry.register(table_name, model)
        return model
    except DynamicTableMetadata.DoesNotExist:
        return None


# ============================================================
# Row CRUD (on dynamic tables)
# ============================================================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_row(request, table_name: str):
    """Insert a row into a dynamic table."""
    model = _get_model_or_load(table_name)
    if model is None:
        return Response(
            {"success": False, "error": f"Table '{table_name}' not found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    try:
        instance = model.objects.create(**request.data)
        return Response(
            {"success": True, "id": instance.pk, "data": _serialize_row(instance)},
            status=status.HTTP_201_CREATED,
        )
    except Exception as e:
        return Response(
            {"success": False, "error": str(e)},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_rows(request, table_name: str):
    """Query rows from a dynamic table with optional filters.

    Query params:
        ?limit=50&offset=0&order_by=-created_at
        &filter_company=Acme  (dynamic filter on any column)
    """
    model = _get_model_or_load(table_name)
    if model is None:
        return Response(
            {"success": False, "error": f"Table '{table_name}' not found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    try:
        qs = model.objects.all()

        # Dynamic filtering from query params
        for key, value in request.query_params.items():
            if key in ("limit", "offset", "order_by"):
                continue
            lookup = {key: value}
            qs = qs.filter(**lookup)

        # Ordering
        order_by = request.query_params.get("order_by", "-created_at")
        qs = qs.order_by(order_by)

        # Pagination
        try:
            limit = int(request.query_params.get("limit", 50))
            offset = int(request.query_params.get("offset", 0))
        except (TypeError, ValueError):
            limit, offset = 50, 0

        total = qs.count()
        rows = [_serialize_row(r) for r in qs[offset : offset + limit]]

        return Response({
            "success": True,
            "total": total,
            "limit": limit,
            "offset": offset,
            "rows": rows,
        })
    except Exception as e:
        return Response(
            {"success": False, "error": str(e)},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_row(request, table_name: str, row_id: int):
    """Get a single row by ID."""
    model = _get_model_or_load(table_name)
    if model is None:
        return Response(
            {"success": False, "error": f"Table '{table_name}' not found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    try:
        instance = model.objects.get(pk=row_id)
        return Response({"success": True, "data": _serialize_row(instance)})
    except model.DoesNotExist:
        return Response(
            {"success": False, "error": f"Row {row_id} not found"},
            status=status.HTTP_404_NOT_FOUND,
        )


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_row(request, table_name: str, row_id: int):
    """Update a row in a dynamic table."""
    model = _get_model_or_load(table_name)
    if model is None:
        return Response(
            {"success": False, "error": f"Table '{table_name}' not found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    try:
        instance = model.objects.get(pk=row_id)
        for key, value in request.data.items():
            setattr(instance, key, value)
        instance.save(update_fields=list(request.data.keys()))
        return Response({"success": True, "data": _serialize_row(instance)})
    except model.DoesNotExist:
        return Response(
            {"success": False, "error": f"Row {row_id} not found"},
            status=status.HTTP_404_NOT_FOUND,
        )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_row(request, table_name: str, row_id: int):
    """Delete a row from a dynamic table."""
    model = _get_model_or_load(table_name)
    if model is None:
        return Response(
            {"success": False, "error": f"Table '{table_name}' not found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    try:
        instance = model.objects.get(pk=row_id)
        instance.delete()
        return Response({"success": True, "message": f"Row {row_id} deleted"})
    except model.DoesNotExist:
        return Response(
            {"success": False, "error": f"Row {row_id} not found"},
            status=status.HTTP_404_NOT_FOUND,
        )


# ============================================================
# Helpers
# ============================================================

def _parse_schema(data: dict) -> TableSchema:
    """Parse frontend JSON into a validated TableSchema."""
    columns = []
    for col_data in data.get("columns", []):
        columns.append(ColumnDef(
            name=col_data["name"],
            col_type=col_data["col_type"],
            nullable=col_data.get("nullable", True),
            default=col_data.get("default"),
            max_length=col_data.get("max_length"),
            unique=col_data.get("unique", False),
            index=col_data.get("index", False),
        ))
    return TableSchema(
        name=data["name"],
        display_name=data.get("display_name", ""),
        description=data.get("description", ""),
        columns=columns,
    )


def _serialize_row(instance) -> dict:
    """Serialize a dynamic model instance to a JSON-safe dict."""
    data = {}
    for field in instance._meta.get_fields():
        if field.is_relation or field.auto_created:
            continue
        value = getattr(instance, field.name, None)
        # Convert non-JSON-serializable types
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        elif isinstance(value, bytes):
            value = value.hex()
        data[field.name] = value
    return data


# ============================================================
# Scheduled Tasks API
# ============================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_schedules(request):
    """List all scheduled periodic tasks, optionally filtered by table."""
    from .task_registry import task_scheduler, TASK_REGISTRY
    table_name = request.query_params.get("table_name")
    schedules = task_scheduler.list_schedules(table_name)
    return Response({
        "success": True,
        "schedules": schedules,
        "available_task_types": [
            {"name": t.name, "display_name": t.display_name, "description": t.description}
            for t in TASK_REGISTRY.values()
        ],
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_schedule(request):
    """
    Create a new periodic task schedule.

    Request body:
    {
        "name": "Daily recalculation",
        "task_type": "recalculate_table",
        "table_name": "sales_leads",
        "schedule_type": "crontab",
        "schedule_config": {"minute": "0", "hour": "2"},
        "args": {"full_scan": true}
    }
    """
    from .task_registry import task_scheduler

    try:
        pt = task_scheduler.create_schedule(
            name=request.data["name"],
            task_type=request.data["task_type"],
            table_name=request.data["table_name"],
            schedule_type=request.data["schedule_type"],
            schedule_config=request.data["schedule_config"],
            args=request.data.get("args"),
            enabled=request.data.get("enabled", True),
        )
        return Response({
            "success": True,
            "id": pt.pk,
            "message": f"Schedule '{pt.name}' created",
        }, status=201)
    except ValueError as e:
        return Response({"success": False, "error": str(e)}, status=400)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_schedule(request, schedule_id: int):
    """Delete a scheduled task."""
    from .task_registry import task_scheduler
    ok = task_scheduler.delete_schedule(schedule_id)
    if ok:
        return Response({"success": True, "message": f"Schedule {schedule_id} deleted"})
    return Response({"success": False, "error": "Not found"}, status=404)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def toggle_schedule(request, schedule_id: int):
    """Enable or disable a scheduled task."""
    from .task_registry import task_scheduler
    enabled = request.data.get("enabled", True)
    ok = task_scheduler.toggle_schedule(schedule_id, enabled)
    if ok:
        return Response({"success": True, "enabled": enabled})
    return Response({"success": False, "error": "Not found"}, status=404)


# ============================================================
# Dependency Analysis (Rust Engine)
# ============================================================

@api_view(["POST"])
def analyze_dependencies(request):
    """Analyze column dependencies using the Rust engine."""
    import json
    try:
        import rust_engine
        columns = request.data.get("columns", [])
        result = json.loads(rust_engine.resolve_dependencies(json.dumps(columns)))
        return Response(result)
    except ImportError:
        cols = request.data.get("columns", [])
        return Response({
            "order": [[c["name"] for c in cols]],
            "has_cycle": False,
            "cycles": [],
        })
