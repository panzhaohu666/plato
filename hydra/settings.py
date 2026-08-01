"""
Plato — Dynamic Data-Driven Real-Time Collaborative Multi-Dimensional Table
Django settings for enterprise-grade multi-tenant architecture.

Key decisions:
- PostgreSQL with django-tenants (schema-per-tenant isolation)
- Channels + Redis for WebSocket real-time collaboration
- Celery + django-celery-beat for async task orchestration
- ClickHouse for cold-data analytics storage
- Strawberry GraphQL for complex multi-dimensional queries
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-plato-dev-key-change-in-production",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() in ("1", "true", "yes")

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

# ============================================================
# Application Definition
# ============================================================

SHARED_APPS = (
    # django-tenants: apps that live in the 'public' schema
    "django_tenants",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Custom shared apps
    "apps.tenants",  # Tenant model, custom user
    "apps.dynamic_models",  # Dynamic table metadata (shared infrastructure)
    # Celery infrastructure (shared across tenants)
    "django_celery_beat",
    "django_celery_results",
)

TENANT_APPS = (
    # django-tenants: apps that live in per-tenant schemas
    "django.contrib.admin",
    # Project apps
    "apps.workflows",       # FSM-based workflow engine
    # Third-party
    "django_fsm",
    "rest_framework",
    "corsheaders",
    "strawberry_django",
)

INSTALLED_APPS = list(SHARED_APPS) + list(TENANT_APPS)

MIDDLEWARE = [
    "django_tenants.middleware.main.TenantMainMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "hydra.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "hydra.wsgi.application"
ASGI_APPLICATION = "hydra.asgi.application"

# ============================================================
# Database — PostgreSQL with django-tenants
# ============================================================

DATABASES = {
    "default": {
        "ENGINE": "django_tenants.postgresql_backend",
        "NAME": os.environ.get("DB_NAME", "hydra_db"),
        "USER": os.environ.get("DB_USER", "hydra"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "hydra_pass_2024"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    },
    # ClickHouse — analytics / cold-data store, NOT managed by Django ORM
    "clickhouse": {
        "ENGINE": "django.db.backends.dummy",
        "HOST": os.environ.get("CH_HOST", "localhost"),
        "PORT": os.environ.get("CH_PORT", "8123"),
        "USER": os.environ.get("CH_USER", "hydra"),
        "PASSWORD": os.environ.get("CH_PASSWORD", "hydra_clickhouse_2024"),
        "NAME": os.environ.get("CH_DB", "hydra_analytics"),
    },
}

DATABASE_ROUTERS = [
    "django_tenants.routers.TenantSyncRouter",
    "hydra.routers.ClickHouseRouter",
]

# django-tenants
DATABASE_SCHEMA_ROUTERS = True
TENANT_MODEL = "tenants.Tenant"
TENANT_DOMAIN_MODEL = "tenants.Domain"

# ============================================================
# Redis
# ============================================================

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}"

# ============================================================
# Django Channels — WebSocket + ASGI
# ============================================================

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [(REDIS_HOST, REDIS_PORT)],
            "capacity": 1500,
            "expiry": 10,
        },
    },
}

# ============================================================
# Celery — Async Task Queue
# ============================================================

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", f"{REDIS_URL}/0")
CELERY_RESULT_BACKEND = "django-db"
CELERY_CACHE_BACKEND = "django-cache"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Asia/Shanghai"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# Prevent beat from creating thousands of periodic-task history rows
CELERY_BEAT_MAX_LOOP_INTERVAL = 300

# ============================================================
# ClickHouse — native connection (NOT Django ORM)
# ============================================================

CLICKHOUSE_CONFIG = {
    "host": os.environ.get("CH_HOST", "localhost"),
    "port": int(os.environ.get("CH_HTTP_PORT", "8123")),
    "username": os.environ.get("CH_USER", "hydra"),
    "password": os.environ.get("CH_PASSWORD", "hydra_clickhouse_2024"),
    "database": os.environ.get("CH_DB", "hydra_analytics"),
    "connect_timeout": 10,
    "send_receive_timeout": 30,
}

# ============================================================
# REST Framework
# ============================================================

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.CursorPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

# ============================================================
# CORS
# ============================================================

CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",  # Vite dev server
    "http://localhost:8080",  # Nginx
]

# ============================================================
# Custom User Model
# ============================================================

AUTH_USER_MODEL = "tenants.User"

# ============================================================
# Internationalization
# ============================================================

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

# ============================================================
# Static & Media
# ============================================================

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ============================================================
# Default primary key field
# ============================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ============================================================
# Dynamic Model Constraints
# ============================================================

# All runtime-created tables live in this schema — NEVER public
DYNAMIC_TABLE_SCHEMA = "dynamic_data"

# Max columns per dynamic table (prevent abuse)
DYNAMIC_TABLE_MAX_COLUMNS = 200

# Column types users are allowed to create
DYNAMIC_TABLE_ALLOWED_TYPES = {
    "string": "VARCHAR(255)",
    "text": "TEXT",
    "integer": "INTEGER",
    "bigint": "BIGINT",
    "float": "DOUBLE PRECISION",
    "decimal": "NUMERIC(18, 4)",
    "boolean": "BOOLEAN",
    "date": "DATE",
    "datetime": "TIMESTAMP WITH TIME ZONE",
    "json": "JSONB",
    "uuid": "UUID",
}

# ============================================================
# Logging
# ============================================================

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {module}:{lineno} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.environ.get("LOG_LEVEL", "INFO"),
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django_tenants": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps.dynamic_models": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}
