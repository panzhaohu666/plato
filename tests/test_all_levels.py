"""Comprehensive test suite for Plato - all 5 levels."""
from django.test import TestCase, override_settings
from django.db import connection
from unittest import skipIf
import socket

def _clickhouse_available():
    try:
        s = socket.create_connection(("localhost", 8123), timeout=1)
        s.close()
        return True
    except OSError:
        return False


class PlatoBaseTestCase(TestCase):
    """Base: creates tenant, user, and dynamic_data schema for all tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with connection.cursor() as c:
            c.execute("CREATE SCHEMA IF NOT EXISTS dynamic_data")
        from apps.tenants.models import Tenant, Domain, User
        cls.tenant = Tenant.objects.create(schema_name="public", name="TestTenant")
        Domain.objects.create(domain="test.local", tenant=cls.tenant, is_primary=True)
        cls.demo_user = User.objects.create_user(username="admin", password="admin123")

    @classmethod
    def tearDownClass(cls):
        from apps.dynamic_models.models import DynamicTableMetadata
        DynamicTableMetadata.objects.filter(table_name__startswith="tdyn").update(status="archived")
        with connection.cursor() as c:
            c.execute("DROP TABLE IF EXISTS dynamic_data.tdyn")
            c.execute("DROP TABLE IF EXISTS dynamic_data.tdyn2")
        super().tearDownClass()

    def setUp(self):
        from apps.dynamic_models.manager import dynamic_model_manager, ColumnDef, TableSchema
        from apps.dynamic_models.models import DynamicTableMetadata
        from apps.dynamic_models.registry import registry

        # Always drop and recreate — Django TestCase wraps each test in a transaction
        DynamicTableMetadata.objects.filter(table_name="tdyn").update(status="archived")
        with connection.cursor() as c:
            c.execute("DROP TABLE IF EXISTS dynamic_data.tdyn")
        registry.unregister("tdyn")

        schema = TableSchema(
            name="tdyn", display_name="Test",
            columns=[ColumnDef(name="title", col_type="string", nullable=False),
                     ColumnDef(name="score", col_type="integer", default=0)],
        )
        dynamic_model_manager.create_table(schema)


class TestLevel1_DynamicSchema(PlatoBaseTestCase):
    def test_create_table(self):
        from apps.dynamic_models.manager import dynamic_model_manager, ColumnDef, TableSchema
        from apps.dynamic_models.models import DynamicTableMetadata
        schema = TableSchema(name="tdyn2", columns=[ColumnDef(name="val", col_type="integer")])
        m = dynamic_model_manager.create_table(schema)
        self.assertEqual(m.__name__, "Tdyn2")
        DynamicTableMetadata.objects.filter(table_name="tdyn2").update(status="archived")
        with connection.cursor() as c:
            c.execute("DROP TABLE IF EXISTS dynamic_data.tdyn2")

    def test_insert_query(self):
        from apps.dynamic_models.registry import registry
        m = registry.get("tdyn")
        self.assertIsNotNone(m)
        m.objects.create(title="A", score=10)
        m.objects.create(title="B", score=90)
        self.assertEqual(m.objects.count(), 2)
        self.assertEqual(m.objects.filter(score__gte=50).count(), 1)

    def test_add_column(self):
        from apps.dynamic_models.manager import dynamic_model_manager, ColumnDef
        from apps.dynamic_models.models import DynamicTableMetadata
        dynamic_model_manager.add_column("tdyn", ColumnDef(name="tag", col_type="string"))
        meta = DynamicTableMetadata.objects.get(table_name="tdyn")
        self.assertEqual(meta.columns.filter(is_deleted=False).count(), 3)

    def test_list_tables(self):
        from apps.dynamic_models.manager import dynamic_model_manager
        self.assertTrue(any(t["name"] == "tdyn" for t in dynamic_model_manager.list_tables()))


class TestLevel2_YjsCRDT(PlatoBaseTestCase):
    def test_crdt_convergence(self):
        import y_py as Y
        from apps.dynamic_models.yjs_service import yjs_manager
        a, b = Y.YDoc(), Y.YDoc()
        with a.begin_transaction() as txn:
            a.get_text("x").extend(txn, "Hello CRDT")
        yjs_manager.apply_update("tdyn", Y.encode_state_as_update(a), broadcast=False)
        Y.apply_update(b, yjs_manager.handle_step1("tdyn", Y.encode_state_vector(b)))
        self.assertEqual(str(b.get_text("x")), "Hello CRDT")

    def test_persistence(self):
        from apps.dynamic_models.yjs_service import yjs_manager
        from apps.dynamic_models.models import DocumentState
        yjs_manager.persist_to_db("tdyn")
        self.assertTrue(DocumentState.objects.filter(table_name="tdyn").exists())
        yjs_manager._docs.pop("tdyn", None)
        self.assertIsNotNone(yjs_manager.get_or_create("tdyn"))


class TestLevel3_RustEngine(TestCase):
    def test_topo_sort(self):
        import json, rust_engine
        r = json.loads(rust_engine.resolve_dependencies(json.dumps([
            {"name":"c","dependencies":["b"]},{"name":"b","dependencies":["a"]},{"name":"a"}])))
        self.assertEqual(r["order"], [["a"],["b"],["c"]])

    def test_parallel(self):
        import json, rust_engine
        r = json.loads(rust_engine.resolve_dependencies(json.dumps([
            {"name":"t","dependencies":["x","y"]},{"name":"x"},{"name":"y"},{"name":"z"}])))
        self.assertEqual(len(r["order"][0]), 3)

    def test_cycle(self):
        import json, rust_engine
        r = json.loads(rust_engine.detect_cycles(json.dumps([
            {"name":"a","dependencies":["b"]},{"name":"b","dependencies":["a"]}])))
        self.assertTrue(r["has_cycle"])

    def test_self_loop(self):
        import json, rust_engine
        r = json.loads(rust_engine.detect_cycles(json.dumps([
            {"name":"x","dependencies":["x"]}])))
        self.assertTrue(r["has_cycle"])


class TestLevel4_ClickHouse(PlatoBaseTestCase):

    def setUp(self):
        if not _clickhouse_available():
            self.skipTest("ClickHouse not available in CI")
        super().setUp()

    def test_insert_query(self):
        from apps.dynamic_models.clickhouse_client import insert_event_log, query_event_log
        insert_event_log("public","tdyn","INSERT","1",{"title":"CH"})
        self.assertGreaterEqual(len(query_event_log("public","tdyn",limit=1)), 1)

    def test_event_type(self):
        from apps.dynamic_models.clickhouse_client import insert_event_log, query_event_log
        insert_event_log("public","tdyn","UPDATE","2",{"title":"N"},{"title":"O"})
        self.assertTrue(any(e["event_type"]=="UPDATE" for e in query_event_log("public","tdyn",limit=5)))


class TestLevel5_Celery(PlatoBaseTestCase):
    def test_crud(self):
        from apps.dynamic_models.task_registry import task_scheduler
        from django_celery_beat.models import PeriodicTask
        pt = task_scheduler.create_schedule("T","validate_table","tdyn","crontab",{"minute":"0","hour":"3"})
        self.assertEqual(len(task_scheduler.list_schedules("tdyn")), 1)
        pk = pt.pk
        task_scheduler.delete_schedule(pk)
        self.assertFalse(PeriodicTask.objects.filter(pk=pk).exists())

    def test_toggle(self):
        from apps.dynamic_models.task_registry import task_scheduler
        pt = task_scheduler.create_schedule("Tog","recalculate_table","tdyn","crontab",{"minute":"0","hour":"0"})
        task_scheduler.toggle_schedule(pt.pk, enabled=False)
        pt.refresh_from_db()
        self.assertFalse(pt.enabled)
        pt.delete()


class TestExpression(TestCase):
    def test_math(self):
        from apps.dynamic_models.expression_engine import evaluate_expression
        self.assertEqual(evaluate_expression("a*b+c",{"a":2,"b":3,"c":1}), 7)

    def test_security(self):
        from apps.dynamic_models.expression_engine import evaluate_expression
        self.assertIsNone(evaluate_expression("__import__('os')",{}))
        self.assertIsNone(evaluate_expression("eval('1+1')",{}))


class TestAuth(PlatoBaseTestCase):
    def test_demo_user(self):
        from apps.tenants.models import User
        self.assertTrue(User.objects.filter(username="admin").exists())

    def test_tenant(self):
        from apps.tenants.models import Tenant
        self.assertTrue(Tenant.objects.filter(schema_name="public").exists())

    def test_jwt(self):
        from apps.tenants.models import User
        from rest_framework_simplejwt.tokens import RefreshToken
        u = User.objects.create_user(username="jwt", password="p")
        self.assertGreater(len(str(RefreshToken.for_user(u).access_token)), 10)
