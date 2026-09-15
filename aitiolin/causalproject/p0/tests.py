"""API regression tests. Run with: python manage.py test p0 --noinput.

These require the patched application, migrations and declared dependencies.
No real provider request is made by this test suite.
"""
import io
import json
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import zipfile

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from causal_app.models import CausalGraph
from .core import token_digest
from .models import Artifact, GraphOwnership, LLMPermit, RunRecord, Workspace
from .service import WorkspaceError, query_for, reserve, release, snapshot


class P0ApiTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp(prefix="aitiolin-p0-test-")
        self.override = override_settings(MEDIA_ROOT=self.media, OPENAI_API_KEY="",
            STORAGES={"default": {"BACKEND": "p0.storage.PrivateStorage"},
                      "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(shutil.rmtree, self.media, True)
        self.client = self.new_client("ab" * 32)
        self.other = self.new_client("cd" * 32)

    @staticmethod
    def new_client(token, mode="off"):
        client = APIClient(enforce_csrf_checks=True)
        client.credentials(HTTP_X_AITIOLIN_SESSION=token, HTTP_X_AITIOLIN_SEED="42",
                           HTTP_X_AITIOLIN_LLM_MODE=mode)
        return client

    def upload(self, client=None, content=b"T,Y,C\n0,0,1\n1,1,2\n0,1,3\n1,0,4\n"):
        file = SimpleUploadedFile("example.csv", content, content_type="text/csv")
        response = (client or self.client).post("/api/upload_csv/", {"file": file}, format="multipart")
        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        return response.json()

    def graph(self):
        data = self.upload()
        payload = {"graph_id": data["graph_id"], "nodes": [
            {**v, "position": {"x": 50 + i * 150, "y": 100}} for i, v in enumerate(data["variables"])],
            "edges": [{"source": "C", "target": "T"}, {"source": "C", "target": "Y"},
                      {"source": "T", "target": "Y"}]}
        response = self.client.post("/api/save_graph/", payload, format="json")
        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        return CausalGraph.objects.get(pk=data["graph_id"]), data

    def estimate(self, graph, data):
        def image(graph_id, *args, **kwargs):
            relative = f"causal_graphs/causal_graph_{graph_id}.png"
            path = Path(settings.MEDIA_ROOT) / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"\x89PNG\r\n\x1a\nprototype-test")
            return settings.MEDIA_URL + relative
        ids = {v["name"]: v["id"] for v in data["variables"]}
        with patch("causal_app.views.estimate_effect", return_value={"estimated_effect": -.25,
                "method_name": "backdoor.linear_regression", "estimand_string": "ATE under the test DAG"}), \
                patch("causal_app.views.generate_graph_image", side_effect=image):
            response = self.client.post("/api/causal_inference/", {"graph_id": graph.pk,
                "treatment": ids["T"], "outcome": ids["Y"],
                "method_name": "backdoor.linear_regression"}, format="json")
        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        return response.json()

    def test_requires_strong_session_header(self):
        self.assertEqual(APIClient().get("/api/p0/session/").status_code, 401)
        weak = self.new_client("guessable")
        self.assertEqual(weak.get("/api/p0/session/").status_code, 401)

    def test_invalid_csv_has_no_database_or_file_residue(self):
        file = SimpleUploadedFile("empty.csv", b"T,T\n1,2\n", content_type="text/csv")
        response = self.client.post("/api/upload_csv/", {"file": file}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CausalGraph.objects.count(), 0)
        self.assertFalse(any(p.is_file() for p in Path(self.media).rglob("*")))

    def test_other_session_cannot_read_write_or_enumerate_graph(self):
        graph, _ = self.graph()
        self.assertEqual(self.other.get(f"/api/graphs/{graph.pk}/").status_code, 404)
        self.assertEqual(self.other.post("/api/save_graph/", {"graph_id": graph.pk, "edges": []}, format="json").status_code, 404)
        self.assertEqual(self.other.get("/api/variables/").json(), [])
        self.assertEqual(self.client.get(f"/api/graphs/{graph.pk}/").status_code, 200)

    def test_samples_are_allowlisted_and_have_no_network_dependency(self):
        names = {item["id"] for item in self.client.get("/api/p0/samples/").json()["samples"]}
        self.assertEqual(names, {"churn", "worldbank"})
        self.assertEqual(self.client.post("/api/p0/samples/not-a-sample/load/", {}, format="json").status_code, 404)
        with patch("openai.OpenAI") as provider:
            for sample in sorted(names):
                result = self.client.post(f"/api/p0/samples/{sample}/load/", {}, format="json")
                self.assertEqual(result.status_code, 200, getattr(result, "data", None))
                self.assertTrue(result.json()["treatment_id"])
                self.assertTrue(result.json()["outcome_id"])
            provider.assert_not_called()

    def test_sample_modified_file_is_rejected(self):
        with patch("p0.views.manifest", return_value=[{"id": "churn", "file": "Churn.csv", "git_blob_sha1": "0" * 40}]):
            response = self.client.post("/api/p0/samples/churn/load/", {}, format="json")
        self.assertEqual(response.status_code, 409)

    def test_bundle_is_recorded_not_recomputed_and_excludes_data_files(self):
        graph, data = self.graph()
        result = self.estimate(graph, data)
        run = result["p0_run_id"]
        original = self.client.get(f"/api/p0/runs/{run}/bundle/?file_format=zip")
        self.assertEqual(original.status_code, 200)
        self.assertEqual(original["Content-Type"], "application/zip")
        graph.node_positions = {"T": {"x": 999, "y": 999}}
        graph.save(update_fields=["node_positions"])
        with patch("causal_app.views.estimate_effect", side_effect=AssertionError("Export must not estimate")):
            again = self.client.get(f"/api/p0/runs/{run}/bundle/?file_format=zip")
        self.assertEqual(original.content, again.content)
        with zipfile.ZipFile(io.BytesIO(again.content)) as archive:
            self.assertFalse(any(name.endswith(".csv") for name in archive.namelist()))
            record = json.loads(archive.read("run.json"))
            self.assertFalse(record["raw_data_included"])
            self.assertEqual(record["result"]["estimated_effect"], -.25)
            self.assertNotIn("graph_image", record["result"])
            self.assertEqual(record["seed"]["requested"], 42)
        self.assertEqual(self.other.get(f"/api/p0/runs/{run}/bundle/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/p0/runs/{run}/bundle/?file_format=json").status_code, 200)
        self.assertEqual(self.client.get(f"/api/p0/runs/{run}/bundle/?file_format=bad").status_code, 400)

    def test_private_graph_image_requires_owner(self):
        graph, data = self.graph()
        result = self.estimate(graph, data)
        self.assertTrue(result["graph_image"].startswith("/api/p0/graphs/"))
        image = self.client.get(result["graph_image"])
        self.assertEqual(image.status_code, 200)
        b"".join(image.streaming_content)
        self.assertEqual(self.other.get(result["graph_image"]).status_code, 404)
        self.assertEqual(self.client.get(f"/media/causal_graphs/causal_graph_{graph.pk}.png").status_code, 404)

    def test_delete_removes_only_owned_data(self):
        graph, data = self.graph()
        self.estimate(graph, data)
        other = self.upload(self.other)
        other_graph = CausalGraph.objects.get(pk=other["graph_id"])
        other_file = Path(other_graph.data_file.path)
        owned_files = [Path(self.media) / a.storage_name for a in Artifact.objects.filter(graph=graph)]
        response = self.client.delete("/api/p0/session/data/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CausalGraph.objects.filter(pk=graph.pk).exists())
        self.assertFalse(any(p.exists() for p in owned_files))
        self.assertTrue(other_file.exists())
        self.assertTrue(CausalGraph.objects.filter(pk=other_graph.pk).exists())

    def test_expiry_blocks_access_but_allows_deletion(self):
        data = self.upload()
        Workspace.objects.filter(pk=token_digest("ab" * 32)).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get(f'/api/graphs/{data["graph_id"]}/').status_code, 410)
        self.assertEqual(self.client.delete("/api/p0/session/data/").status_code, 200)

    def test_failed_deletion_remains_locked_and_retryable(self):
        data = self.upload()
        with patch("pathlib.Path.unlink", side_effect=PermissionError("test")):
            response = self.client.delete("/api/p0/session/data/")
        self.assertEqual(response.status_code, 500)
        workspace = Workspace.objects.get(pk=token_digest("ab" * 32))
        self.assertTrue(workspace.deleting)
        self.assertFalse(workspace.busy)
        self.assertTrue(CausalGraph.objects.filter(pk=data["graph_id"]).exists())
        self.assertEqual(self.client.delete("/api/p0/session/data/").status_code, 200)

    def test_busy_session_rejects_deletion(self):
        self.upload()
        Workspace.objects.filter(pk=token_digest("ab" * 32)).update(busy=True)
        response = self.client.delete("/api/p0/session/data/")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "session_busy")

    def test_retention_does_not_silently_extend_beyond_maximum(self):
        self.client.get("/api/p0/session/")
        response = self.client.patch("/api/p0/session/", {"retention_hours": 1}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.patch("/api/p0/session/", {"retention_hours": 8760}, format="json").status_code, 400)

    def test_purge_only_expired_sessions(self):
        self.upload(); self.upload(self.other)
        Workspace.objects.filter(pk=token_digest("ab" * 32)).update(expires_at=timezone.now() - timedelta(seconds=1))
        call_command("purge_p0_sessions", stdout=io.StringIO())
        self.assertFalse(Workspace.objects.filter(pk=token_digest("ab" * 32)).exists())
        self.assertTrue(Workspace.objects.filter(pk=token_digest("cd" * 32)).exists())

    def test_identification_and_default_estimation_queries_match(self):
        graph, data = self.graph()
        ids = {v["name"]: v["id"] for v in data["variables"]}
        payload = {"treatment": ids["T"], "outcome": ids["Y"]}
        self.assertEqual(query_for(graph, payload), query_for(graph, {**payload, "estimand": "ATE"}))
        self.assertNotEqual(query_for(graph, payload), query_for(graph, {**payload, "estimand": "ATT"}))

    @override_settings(OPENAI_API_KEY="test-key-not-used", OPENAI_MODEL="test-model")
    def test_llm_default_off_then_review_exact_payload_once(self):
        payload = {"variables": ["T", "Y"], "context": "Educational graph"}
        with patch("openai.OpenAI") as provider:
            provider.return_value.chat.completions.create.return_value = SimpleNamespace(choices=[
                SimpleNamespace(message=SimpleNamespace(content='{"edges":[{"source":"T","target":"Y","directed":true,"reason":"hypothesis"}]}'))])
            self.assertEqual(self.client.post("/api/openai/suggest_edges/", payload, format="json").status_code, 403)
            provider.assert_not_called()
            reviewed_client = self.new_client("ab" * 32, "review")
            pending = reviewed_client.post("/api/openai/suggest_edges/", payload, format="json")
            self.assertEqual(pending.status_code, 409)
            provider.return_value.chat.completions.create.assert_not_called()
            preview = pending.json()["review"]
            approved = reviewed_client.post("/api/openai/suggest_edges/", payload, format="json",
                HTTP_X_AITIOLIN_LLM_APPROVAL=preview["approval_token"])
            self.assertEqual(approved.status_code, 200, getattr(approved, "data", None))
            self.assertEqual(provider.return_value.chat.completions.create.call_args.kwargs, preview["payload"])
            self.assertFalse(preview["payload"]["store"])
            replay = reviewed_client.post("/api/openai/suggest_edges/", payload, format="json",
                HTTP_X_AITIOLIN_LLM_APPROVAL=preview["approval_token"])
            self.assertEqual(replay.status_code, 409)
            self.assertEqual(provider.return_value.chat.completions.create.call_count, 1)

    @override_settings(OPENAI_API_KEY="test-key-not-used", OPENAI_MODEL="test-model")
    def test_changed_or_cross_session_llm_payload_requires_new_review(self):
        first = self.new_client("ab" * 32, "review")
        other = self.new_client("cd" * 32, "review")
        payload = {"variables": ["T", "Y"]}
        with patch("openai.OpenAI") as provider:
            preview = first.post("/api/openai/suggest_edges/", payload, format="json").json()["review"]
            token = preview["approval_token"]
            self.assertEqual(other.post("/api/openai/suggest_edges/", payload, format="json",
                HTTP_X_AITIOLIN_LLM_APPROVAL=token).status_code, 409)
            self.assertEqual(first.post("/api/openai/suggest_edges/", {**payload, "context": "Changed"}, format="json",
                HTTP_X_AITIOLIN_LLM_APPROVAL=token).status_code, 409)
            provider.return_value.chat.completions.create.assert_not_called()
