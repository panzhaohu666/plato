"""
Dynamic Celery Task Registry for Plato.

Allows users to schedule periodic operations on dynamic tables.
Uses django-celery-beat's DatabaseScheduler for runtime schedule management.

Built-in task types:
  - recalculate_table: Recompute formula/computed columns
  - archive_old_rows: Move rows older than N days to cold storage
  - validate_table: Run data integrity checks
"""
from dataclasses import dataclass, field
from typing import Any, Callable
from celery import shared_task
from django_celery_beat.models import PeriodicTask, CrontabSchedule, IntervalSchedule
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class TaskTypeDef:
    """Definition of a schedulable task type shown in the UI."""
    name: str
    display_name: str
    description: str
    default_args: dict = field(default_factory=dict)


# Available task types users can schedule
TASK_REGISTRY: dict[str, TaskTypeDef] = {
    "recalculate_table": TaskTypeDef(
        name="recalculate_table",
        display_name="Recalculate Table",
        description="Recompute all formula/computed columns on a dynamic table",
        default_args={"table_name": "", "full_scan": True},
    ),
    "archive_old_rows": TaskTypeDef(
        name="archive_old_rows",
        display_name="Archive Old Rows",
        description="Move rows older than specified days to ClickHouse cold storage",
        default_args={"table_name": "", "older_than_days": 90},
    ),
    "validate_table": TaskTypeDef(
        name="validate_table",
        display_name="Validate Table",
        description="Run data integrity checks on all rows",
        default_args={"table_name": "", "checks": ["not_null", "unique"]},
    ),
}


class TaskScheduler:
    """Manage dynamic periodic tasks via django-celery-beat ORM."""

    @staticmethod
    def create_schedule(
        name: str,
        task_type: str,
        table_name: str,
        schedule_type: str,  # "crontab" or "interval"
        schedule_config: dict,
        args: dict | None = None,
        enabled: bool = True,
    ) -> PeriodicTask:
        """
        Create a new periodic task schedule.

        Args:
            name: Human-readable name
            task_type: One of TASK_REGISTRY keys
            table_name: Target dynamic table
            schedule_type: "crontab" or "interval"
            schedule_config: {"minute": "*", "hour": "2"} for crontab,
                            {"every": 3600, "period": "seconds"} for interval
            args: Extra task arguments
            enabled: Whether the schedule is active
        """
        if task_type not in TASK_REGISTRY:
            raise ValueError(f"Unknown task type: {task_type}")

        if schedule_type == "crontab":
            schedule, _ = CrontabSchedule.objects.get_or_create(
                minute=schedule_config.get("minute", "0"),
                hour=schedule_config.get("hour", "*"),
                day_of_week=schedule_config.get("day_of_week", "*"),
                day_of_month=schedule_config.get("day_of_month", "*"),
                month_of_year=schedule_config.get("month_of_year", "*"),
            )
        elif schedule_type == "interval":
            schedule, _ = IntervalSchedule.objects.get_or_create(
                every=schedule_config["every"],
                period=schedule_config.get("period", "seconds"),
            )
        else:
            raise ValueError(f"Unknown schedule type: {schedule_type}")

        task_args = json.dumps({
            "table_name": table_name,
            "task_type": task_type,
            **(args or {}),
        })

        # Celery task path must be a registered shared_task
        task_path = "apps.dynamic_models.tasks.execute_scheduled_task"

        periodic_task = PeriodicTask.objects.create(
            name=name,
            task=task_path,
            crontab=schedule if schedule_type == "crontab" else None,
            interval=schedule if schedule_type == "interval" else None,
            args=task_args,
            enabled=enabled,
            description=f"{task_type} on table '{table_name}'",
        )

        logger.info(
            "Created periodic task '%s' (%s on %s, %s)",
            name, task_type, table_name, schedule_type,
        )
        return periodic_task

    @staticmethod
    def list_schedules(table_name: str | None = None) -> list[dict]:
        """List all dynamic scheduled tasks, optionally filtered by table."""
        qs = PeriodicTask.objects.filter(
            task="apps.dynamic_models.tasks.execute_scheduled_task",
        )
        if table_name:
            qs = qs.filter(args__contains=table_name)

        results = []
        for pt in qs:
            args = json.loads(pt.args) if pt.args else {}
            schedule_info = {}
            if pt.crontab:
                schedule_info = {
                    "type": "crontab",
                    "minute": pt.crontab.minute,
                    "hour": pt.crontab.hour,
                    "day_of_week": pt.crontab.day_of_week,
                }
            elif pt.interval:
                schedule_info = {
                    "type": "interval",
                    "every": pt.interval.every,
                    "period": pt.interval.period,
                }

            results.append({
                "id": pt.pk,
                "name": pt.name,
                "task_type": args.get("task_type", "unknown"),
                "table_name": args.get("table_name", ""),
                "schedule": schedule_info,
                "enabled": pt.enabled,
                "last_run_at": pt.last_run_at.isoformat() if pt.last_run_at else None,
                "total_run_count": pt.total_run_count,
            })

        return results

    @staticmethod
    def delete_schedule(schedule_id: int) -> bool:
        """Delete a periodic task schedule."""
        try:
            pt = PeriodicTask.objects.get(pk=schedule_id)
            pt.delete()
            logger.info("Deleted periodic task #%d", schedule_id)
            return True
        except PeriodicTask.DoesNotExist:
            return False

    @staticmethod
    def toggle_schedule(schedule_id: int, enabled: bool) -> bool:
        """Enable or disable a schedule."""
        try:
            pt = PeriodicTask.objects.get(pk=schedule_id)
            pt.enabled = enabled
            pt.save(update_fields=["enabled"])
            return True
        except PeriodicTask.DoesNotExist:
            return False


# Singleton
task_scheduler = TaskScheduler()
