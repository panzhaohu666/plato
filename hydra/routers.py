"""
Database router for Plato.
- django-tenants handles schema routing for the 'default' database.
- We ADD a router for ClickHouse queries that bypass Django ORM.
- This router ensures NO Django migration touches the ClickHouse connection.
"""


class ClickHouseRouter:
    """
    ClickHouse is NOT managed by Django ORM.
    All ClickHouse operations use clickhouse-connect directly.
    This router exists to:
    1. Prevent migrations on the clickhouse database
    2. Prevent accidental ORM reads/writes to clickhouse
    """

    route_app_labels = set()  # No Django app uses ClickHouse ORM

    def db_for_read(self, model, **hints):
        return None  # Let django-tenants handle default routing

    def db_for_write(self, model, **hints):
        return None

    def allow_relation(self, obj1, obj2, **hints):
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if db == "clickhouse":
            return False  # NEVER migrate ClickHouse
        return None  # Let django-tenants decide
