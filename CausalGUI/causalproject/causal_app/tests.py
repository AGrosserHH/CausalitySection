import shutil
import tempfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .models import CausalEdge, CausalGraph


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
