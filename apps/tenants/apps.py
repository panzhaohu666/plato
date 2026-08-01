"""App config for tenants — tenant lifecycle management."""
from django.apps import AppConfig


class TenantsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tenants"
    verbose_name = "Tenants"

    def ready(self):
        try:
            from .startup import create_demo_user
            create_demo_user()
        except Exception:
            pass  # Table doesn't exist yet (running migrations)
        import apps.tenants.signals
