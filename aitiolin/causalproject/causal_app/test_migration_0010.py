"""Migration 0010 carries rows over from the tables of the former "p0" app before dropping them.

The test database never contains those tables, so the test builds them by hand at the previous
migration state, fills them the way the old app did, and migrates forward.
"""
import json
import uuid

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from .models import Artifact, CausalGraph, GraphOwnership, LLMPermit, RunRecord, Workspace

BEFORE = ("causal_app", "0009_causalgraph_cleaned_file_causalgraph_cleaning_plan")
AFTER = ("causal_app", "0010_workspace_models")

# The old app's tables as Django created them on SQLite.
OLD_TABLES = {
    "p0_workspace": "token_hash varchar(64) NOT NULL PRIMARY KEY, created_at datetime NOT NULL, "
                    "expires_at datetime NOT NULL, busy bool NOT NULL, deleting bool NOT NULL",
    "p0_graphownership": "id integer NOT NULL PRIMARY KEY AUTOINCREMENT, sample_id varchar(64) NOT NULL, "
                         "cleaning_history text NOT NULL, graph_id bigint NOT NULL UNIQUE, "
                         "workspace_id varchar(64) NOT NULL",
    "p0_artifact": "id integer NOT NULL PRIMARY KEY AUTOINCREMENT, storage_name varchar(500) NOT NULL, "
                   "graph_id bigint NOT NULL, workspace_id varchar(64) NOT NULL",
    "p0_runrecord": "id char(32) NOT NULL PRIMARY KEY, created_at datetime NOT NULL, "
                    "analysis_key varchar(64) NOT NULL, operation varchar(64) NOT NULL, payload text NOT NULL, "
                    "graph_id bigint NOT NULL, workspace_id varchar(64) NOT NULL",
    "p0_llmpermit": "id char(32) NOT NULL PRIMARY KEY, payload_hash varchar(64) NOT NULL, "
                    "operation varchar(100) NOT NULL, expires_at datetime NOT NULL, used bool NOT NULL, "
                    "workspace_id varchar(64) NOT NULL",
}


def migrate_to(target):
    MigrationExecutor(connection).migrate([target])


def old_tables_present():
    return set(OLD_TABLES) & set(connection.introspection.table_names())


class WorkspaceMigrationTests(TransactionTestCase):
    def tearDown(self):
        migrate_to(AFTER)  # leave the schema current for the rest of the suite

    def test_rows_from_the_old_p0_tables_are_carried_over(self):
        migrate_to(BEFORE)
        graph = CausalGraph.objects.create(name="carried over")
        token, run_id, permit_id = "ab" * 32, uuid.uuid4().hex, uuid.uuid4().hex
        with connection.cursor() as cursor:
            for table, columns in OLD_TABLES.items():
                cursor.execute(f"CREATE TABLE {table} ({columns})")
            cursor.execute("INSERT INTO p0_workspace VALUES (%s, %s, %s, 0, 0)",
                           [token, "2026-09-16 10:00:00", "2026-09-16 12:00:00"])
            cursor.execute("INSERT INTO p0_graphownership (sample_id, cleaning_history, graph_id, workspace_id) "
                           "VALUES (%s, %s, %s, %s)", ["churn", json.dumps([{"at": "t"}]), graph.pk, token])
            cursor.execute("INSERT INTO p0_artifact (storage_name, graph_id, workspace_id) VALUES (%s, %s, %s)",
                           ["datasets/p0/old.csv", graph.pk, token])
            cursor.execute("INSERT INTO p0_runrecord VALUES (%s, %s, %s, %s, %s, %s, %s)",
                           [run_id, "2026-09-16 11:00:00", "k" * 64, "causal_inference",
                            json.dumps({"result": {"estimated_effect": -0.25}}), graph.pk, token])
            cursor.execute("INSERT INTO p0_llmpermit VALUES (%s, %s, %s, %s, 0, %s)",
                           [permit_id, "h" * 64, "openai_suggest_edges", "2026-09-16 11:02:00", token])
            cursor.execute("INSERT INTO django_migrations (app, name, applied) VALUES ('p0', '0001_initial', %s)",
                           ["2026-09-16 09:00:00"])
        self.assertEqual(old_tables_present(), set(OLD_TABLES))

        migrate_to(AFTER)

        workspace = Workspace.objects.get(token_hash=token)
        self.assertEqual(workspace.expires_at.strftime("%Y-%m-%d %H:%M"), "2026-09-16 12:00")
        self.assertFalse(workspace.busy)
        ownership = GraphOwnership.objects.get(graph=graph)
        self.assertEqual(ownership.workspace, workspace)
        self.assertEqual(ownership.sample_id, "churn")
        self.assertEqual(ownership.cleaning_history, [{"at": "t"}])
        self.assertEqual(Artifact.objects.get(workspace=workspace, storage_name="datasets/p0/old.csv").graph, graph)
        record = RunRecord.objects.get(pk=uuid.UUID(run_id))
        self.assertEqual((record.workspace, record.graph, record.operation), (workspace, graph, "causal_inference"))
        self.assertEqual(record.payload["result"]["estimated_effect"], -0.25)
        self.assertFalse(LLMPermit.objects.get(pk=uuid.UUID(permit_id)).used)
        # The old tables and the old app's migration bookkeeping are gone.
        self.assertEqual(old_tables_present(), set())
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM django_migrations WHERE app = 'p0'")
            self.assertEqual(cursor.fetchone()[0], 0)

    def test_migration_copies_nothing_where_the_old_app_never_existed(self):
        migrate_to(BEFORE)
        self.assertEqual(old_tables_present(), set())
        migrate_to(AFTER)
        self.assertEqual(Workspace.objects.count(), 0)
        self.assertEqual(RunRecord.objects.count(), 0)
