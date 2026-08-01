"""Create demo user on startup if none exists."""
from apps.tenants.models import User


def create_demo_user():
    if not User.objects.filter(username="admin").exists():
        User.objects.create_superuser(
            username="admin",
            password="admin123",
            email="admin@plato.local",
        )
    if not User.objects.filter(username="demo").exists():
        User.objects.create_user(
            username="demo",
            password="demo123",
        )
