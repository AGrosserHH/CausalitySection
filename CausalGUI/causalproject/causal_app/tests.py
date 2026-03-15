import shutil
import tempfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .models import CausalEdge, CausalGraph, EdgeEvidence


class _FakeIdentifiedEstimand:
	def get_backdoor_variables(self):
		return ["C"]

	def get_instrumental_variables(self):
		return []

	def get_frontdoor_variables(self):
		return []


class _FakeCausalModel:
	def __init__(self, *args, **kwargs):
		pass

	def identify_effect(self):
		return _FakeIdentifiedEstimand()


class CausalApiTests(APITestCase):
	def setUp(self):
		self.temp_media = tempfile.mkdtemp(prefix="causal_test_media_")
		self.override = override_settings(MEDIA_ROOT=self.temp_media)
		self.override.enable()

	def tearDown(self):
		self.override.disable()
		shutil.rmtree(self.temp_media, ignore_errors=True)

	def upload_sample_csv(self):
		csv_content = "A,B,C\n1,0,3\n2,1,2\n3,0,1\n"
		upload_file = SimpleUploadedFile(
			"sample.csv",
			csv_content.encode("utf-8"),
			content_type="text/csv",
		)
		response = self.client.post("/api/upload_csv/", {"file": upload_file}, format="multipart")
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		return response.data

	def upload_time_series_csv(self):
		csv_content = (
			"timestamp,entity,A,B,C\n"
			"2024-01-01,u1,1,0,3\n"
			"2024-01-02,u1,2,1,2\n"
			"2024-01-03,u1,3,1,1\n"
			"2024-01-04,u1,4,2,1\n"
			"2024-01-01,u2,1,1,2\n"
			"2024-01-02,u2,2,1,2\n"
			"2024-01-03,u2,3,2,1\n"
			"2024-01-04,u2,4,3,1\n"
		)
		upload_file = SimpleUploadedFile(
			"timeseries.csv",
			csv_content.encode("utf-8"),
			content_type="text/csv",
		)
		response = self.client.post("/api/upload_csv/", {"file": upload_file}, format="multipart")
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		return response.data

	def test_upload_csv_creates_graph_and_variables(self):
		response_data = self.upload_sample_csv()

		self.assertIn("graph_id", response_data)
		self.assertEqual(len(response_data["variables"]), 3)
		self.assertTrue(CausalGraph.objects.filter(id=response_data["graph_id"]).exists())

	def test_save_graph_persists_edges(self):
		response_data = self.upload_sample_csv()
		graph_id = response_data["graph_id"]

		save_response = self.client.post(
			"/api/save_graph/",
			{
				"graph_id": graph_id,
				"name": "My Graph",
				"edges": [{"source": "A", "target": "B", "directed": True}],
			},
			format="json",
		)

		self.assertEqual(save_response.status_code, status.HTTP_200_OK)
		self.assertEqual(
			CausalEdge.objects.filter(graph_id=graph_id, source__name="A", target__name="B").count(),
			1,
		)
		self.assertEqual(CausalGraph.objects.get(id=graph_id).node_positions, {})

	def test_save_graph_persists_node_positions_and_graph_details_returns_nodes(self):
		response_data = self.upload_sample_csv()
		graph_id = response_data["graph_id"]

		save_response = self.client.post(
			"/api/save_graph/",
			{
				"graph_id": graph_id,
				"name": "Position Graph",
				"nodes": [
					{"id": response_data["variables"][0]["id"], "name": "A", "position": {"x": 120.5, "y": 88.25}},
					{"id": response_data["variables"][1]["id"], "name": "B", "position": {"x": 320.0, "y": 180.0}},
				],
				"edges": [{"source": "A", "target": "B", "directed": True}],
			},
			format="json",
		)

		self.assertEqual(save_response.status_code, status.HTTP_200_OK)
		graph = CausalGraph.objects.get(id=graph_id)
		self.assertEqual(graph.node_positions["A"], {"x": 120.5, "y": 88.25})

		response = self.client.get(f"/api/graphs/{graph_id}/")
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(response.data["nodes"]), 2)
		nodes_by_name = {item["name"]: item for item in response.data["nodes"]}
		self.assertEqual(nodes_by_name["A"]["position"], {"x": 120.5, "y": 88.25})
		self.assertEqual(nodes_by_name["B"]["position"], {"x": 320.0, "y": 180.0})

	def test_causal_inference_requires_params(self):
		response = self.client.post("/api/causal_inference/", {}, format="json")
		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

	@patch(
		"causal_app.views.suggest_edges_with_openai",
		return_value=[
			{
				"source": "A",
				"target": "B",
				"directed": True,
				"reason": "A likely influences B",
			}
		],
	)
	@override_settings(OPENAI_API_KEY="test-key")
	def test_openai_suggest_edges_success(self, _mock_suggestions):
		response = self.client.post(
			"/api/openai/suggest_edges/",
			{
				"variables": ["A", "B", "C"],
				"context": "Customer churn factors",
				"max_edges": 5,
			},
			format="json",
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(response.data["edges"]), 1)
		self.assertEqual(response.data["edges"][0]["source"], "A")

	def test_openai_suggest_edges_requires_api_key(self):
		with override_settings(OPENAI_API_KEY=""):
			response = self.client.post(
				"/api/openai/suggest_edges/",
				{"variables": ["A", "B"]},
				format="json",
			)

		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

	@patch("causal_app.views.generate_graph_image", return_value="/media/causal_graphs/test.png")
	@patch(
		"causal_app.views.estimate_effect",
		return_value={
			"estimated_effect": 1.23,
			"method_name": "backdoor.linear_regression",
			"estimand_string": "estimand",
		},
	)
	def test_causal_inference_success(self, _mock_estimate, _mock_image):
		response_data = self.upload_sample_csv()
		graph_id = response_data["graph_id"]

		self.client.post(
			"/api/save_graph/",
			{
				"graph_id": graph_id,
				"name": "Inference Graph",
				"edges": [{"source": "A", "target": "B", "directed": True}],
			},
			format="json",
		)

		variable_by_name = {item["name"]: item["id"] for item in response_data["variables"]}

		response = self.client.post(
			"/api/causal_inference/",
			{
				"graph_id": graph_id,
				"treatment": variable_by_name["A"],
				"outcome": variable_by_name["B"],
				"method_name": "backdoor.linear_regression",
			},
			format="json",
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data["estimated_effect"], 1.23)
		self.assertEqual(response.data["graph_image"], "/media/causal_graphs/test.png")

	@patch("causal_app.views.get_causal_model_class", return_value=_FakeCausalModel)
	def test_assess_query_success(self, _mock_model_class):
		response_data = self.upload_sample_csv()
		graph_id = response_data["graph_id"]

		self.client.post(
			"/api/save_graph/",
			{
				"graph_id": graph_id,
				"name": "Assess Graph",
				"edges": [
					{"source": "A", "target": "B", "directed": True},
					{"source": "C", "target": "B", "directed": True},
				],
			},
			format="json",
		)

		variable_by_name = {item["name"]: item["id"] for item in response_data["variables"]}

		response = self.client.post(
			"/api/assess_query/",
			{
				"graph_id": graph_id,
				"treatment": variable_by_name["A"],
				"outcome": variable_by_name["B"],
				"estimand": "ATE",
			},
			format="json",
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertTrue(response.data["identifiable"])
		self.assertEqual(response.data["badge"], "trust")
		self.assertIn("C", response.data["adjustment_set"])
		self.assertIn("minimal_adjustment_sets", response.data)
		self.assertIn("admissibility_checklist", response.data)

	def test_graph_details_returns_evidence_status(self):
		response_data = self.upload_sample_csv()
		graph_id = response_data["graph_id"]

		save_response = self.client.post(
			"/api/save_graph/",
			{
				"graph_id": graph_id,
				"name": "Evidence Graph",
				"edges": [
					{
						"source": "A",
						"target": "B",
						"directed": True,
						"manual_lock": True,
						"evidence": [
							{
								"evidence_type": "llm",
								"status": "supported",
								"score": 0.85,
								"details": {"reason": "strong"},
							}
						],
					},
				],
			},
			format="json",
		)
		self.assertEqual(save_response.status_code, status.HTTP_200_OK)

		self.assertEqual(EdgeEvidence.objects.count(), 1)

		response = self.client.get(f"/api/graphs/{graph_id}/")
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(response.data["edges"]), 1)
		edge_data = response.data["edges"][0]
		self.assertTrue(edge_data["manual_lock"])
		self.assertEqual(edge_data["status"], "supported")

	@patch(
		"causal_app.views.suggest_edges_with_openai",
		return_value=[
			{
				"source": "A",
				"target": "B",
				"directed": True,
				"reason": "A likely influences B",
			}
		],
	)
	@override_settings(OPENAI_API_KEY="test-key")
	def test_openai_draft_graph_success(self, _mock_suggestions):
		response_data = self.upload_sample_csv()
		graph_id = response_data["graph_id"]

		response = self.client.post(
			"/api/openai/draft_graph/",
			{
				"graph_id": graph_id,
				"context": "churn analysis",
				"max_edges": 3,
			},
			format="json",
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertIn("edges", response.data)
		self.assertEqual(len(response.data["edges"]), 1)
		self.assertIn("verification_status", response.data["edges"][0])
		self.assertIn("confidence", response.data["edges"][0])
		self.assertIn("recommended_action", response.data["edges"][0])
		self.assertIn("summary", response.data)
		self.assertIn("confounder_candidates", response.data)

	@patch("causal_app.views.get_causal_model_class", return_value=_FakeCausalModel)
	def test_robustness_dashboard_returns_enhanced_fields(self, _mock_model_class):
		response_data = self.upload_sample_csv()
		graph_id = response_data["graph_id"]

		self.client.post(
			"/api/save_graph/",
			{
				"graph_id": graph_id,
				"name": "Robustness Graph",
				"edges": [
					{"source": "A", "target": "B", "directed": True},
					{"source": "C", "target": "B", "directed": True},
				],
			},
			format="json",
		)

		variable_by_name = {item["name"]: item["id"] for item in response_data["variables"]}
		response = self.client.post(
			"/api/robustness_dashboard/",
			{
				"graph_id": graph_id,
				"treatment": variable_by_name["A"],
				"outcome": variable_by_name["B"],
			},
			format="json",
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertIn("baseline_estimate", response.data)
		self.assertIn("diagnostics", response.data)
		self.assertIn("sensitivity_points", response.data)
		self.assertIn("robustness_score", response.data)

	def test_time_series_analysis_returns_edge_stability(self):
		response_data = self.upload_time_series_csv()
		graph_id = response_data["graph_id"]

		self.client.post(
			"/api/save_graph/",
			{
				"graph_id": graph_id,
				"name": "Time Graph",
				"edges": [
					{"source": "A", "target": "B", "directed": True},
					{"source": "C", "target": "B", "directed": True},
				],
			},
			format="json",
		)

		response = self.client.post(
			"/api/time_series_analysis/",
			{
				"graph_id": graph_id,
				"time_column": "timestamp",
				"entity_column": "entity",
				"window_count": 3,
				"max_lag": 2,
			},
			format="json",
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data["mode"], "time-series")
		self.assertTrue(len(response.data["edge_stability"]) >= 1)
		self.assertTrue(len(response.data["dynamic_graphs"]) >= 1)
