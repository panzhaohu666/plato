"""
Celery configuration for Plato.
Uses Redis as broker and django-celery-beat DatabaseScheduler.
"""
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hydra.settings")

app = Celery("plato")

# Load config from Django settings, using the CELERY_ namespace
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Health-check task for diagnosing Celery connectivity."""
    print(f"Celery debug task: {self.request.id!r}")
