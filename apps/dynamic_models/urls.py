"""URL routing for dynamic_models REST API."""
from django.urls import path
from . import views

urlpatterns = [
    # Table management
    path("tables/", views.create_table, name="create-table"),
    path("tables/list/", views.list_tables, name="list-tables"),
    path("tables/<str:table_name>/", views.get_table, name="get-table"),
    path("tables/<str:table_name>/archive/", views.archive_table, name="archive-table"),
    # Column management
    path("tables/<str:table_name>/columns/", views.add_column, name="add-column"),
    path("tables/<str:table_name>/columns/<str:column_name>/", views.delete_column, name="delete-column"),
    # Row CRUD
    path("tables/<str:table_name>/rows/", views.create_row, name="create-row"),
    path("tables/<str:table_name>/rows/list/", views.list_rows, name="list-rows"),
    path("tables/<str:table_name>/rows/<int:row_id>/", views.get_row, name="get-row"),
    path("tables/<str:table_name>/rows/<int:row_id>/update/", views.update_row, name="update-row"),
    path("tables/<str:table_name>/rows/<int:row_id>/delete/", views.delete_row, name="delete-row"),
    # Scheduled tasks
    path("tasks/schedules/", views.list_schedules, name="list-schedules"),
    path("tasks/schedules/create/", views.create_schedule, name="create-schedule"),
    path("tasks/schedules/<int:schedule_id>/delete/", views.delete_schedule, name="delete-schedule"),
    path("tasks/schedules/<int:schedule_id>/toggle/", views.toggle_schedule, name="toggle-schedule"),
    # Dependency analysis (Rust engine)
    path("deps/analyze/", views.analyze_dependencies, name="analyze-deps"),
]
