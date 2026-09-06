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


class _FakeEstimate:
	value = 1.5


class _FakeCausalModel:
	def __init__(self, *args, **kwargs):
		pass

	def identify_effect(self):
		return _FakeIdentifiedEstimand()

	def estimate_effect(self, identified_estimand, method_name=None, **kwargs):
		return _FakeEstimate()


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

	def test_normalize_binary_outcome_preserves_continuous_outcomes(self):
		import pandas as pd

		from .services import normalize_binary_outcome

		continuous = pd.DataFrame({"y": [1.5, 2.7, 3.1, 4.9, 5.2, 6.8]})
		result = normalize_binary_outcome(continuous.copy(), "y")
		self.assertEqual(result["y"].tolist(), continuous["y"].tolist())

		binary_nonstandard = pd.DataFrame({"y": [5, 5, 9, 5, 9, 5]})
		result = normalize_binary_outcome(binary_nonstandard.copy(), "y")
		self.assertEqual(sorted(result["y"].unique().tolist()), [0, 1])
		self.assertEqual(result["y"].tolist(), [0, 0, 1, 0, 1, 0])

		already_binary = pd.DataFrame({"y": [0, 1, 1, 0]})
		result = normalize_binary_outcome(already_binary.copy(), "y")
		self.assertEqual(result["y"].tolist(), [0, 1, 1, 0])

	def test_confounder_sensitivity_sweep_is_a_real_bias_bound(self):
		import numpy as np
		import pandas as pd

		from .services import compute_confounder_sensitivity_sweep

		rng = np.random.default_rng(0)
		n = 400
		z = rng.normal(size=n)
		t = 0.8 * z + rng.normal(size=n)
		y = 2.0 * t + 1.5 * z + rng.normal(size=n)
		frame = pd.DataFrame({"t": t, "y": y, "z": z})

		sweep = compute_confounder_sensitivity_sweep(frame, "t", "y", ["z"], baseline_estimate=2.0)
		self.assertEqual(len(sweep["points"]), 5)
		self.assertGreater(sweep["robustness_value"], 0.5)  # a t-stat this large needs a huge confounder
		biases = [point["bias"] for point in sweep["points"]]
		self.assertEqual(biases, sorted(biases))  # bias grows with confounder strength
		self.assertLess(sweep["points"][0]["adjusted_effect"], 2.0)  # shrinks toward zero
		# Robustness value: the strength at which the bias bound equals the estimate.
		rv = sweep["robustness_value"]
		df = n - 3
		se = sweep["points"][0]["bias"] / (0.1 * np.sqrt(df / 0.9))
		self.assertAlmostEqual(se * rv * np.sqrt(df / (1 - rv)), abs(sweep["t_value"]) * se, places=6)

		degenerate = compute_confounder_sensitivity_sweep(frame, "t", "y", ["z"], baseline_estimate=None)
		self.assertEqual(degenerate["points"], [])

	def test_agent_suggests_log_transform_for_skewed_positive_columns(self):
		import numpy as np

		from .agent_service import apply_cleaning_plan, profile_data_frame, suggest_cleaning_plan
		import pandas as pd

		rng = np.random.default_rng(1)
		frame = pd.DataFrame({
			"income": np.exp(rng.normal(9.0, 1.2, size=300)),  # log-normal: heavy right tail
			"score": rng.normal(size=300),
		})
		profile = profile_data_frame(frame)
		skewed = [issue["column"] for issue in profile["issues"] if issue["issue_type"] == "skewed_positive"]
		self.assertEqual(skewed, ["income"])

		steps = suggest_cleaning_plan(profile)
		log_steps = [step for step in steps if step["step_type"] == "log_transform"]
		self.assertEqual([step["column"] for step in log_steps], ["income"])

		cleaned, applied = apply_cleaning_plan(frame, log_steps)
		self.assertAlmostEqual(float(cleaned["income"].mean()), float(np.log(frame["income"]).mean()))
		self.assertIn("natural log", applied[0]["detail"])

	def test_format_refutation_result_unwraps_list_output(self):
		from .services import _format_refutation_result

		class _FakeRefutation:
			p_value = 0.4
			new_effect = 1.0

			def __str__(self):
				return "Refute: readable summary"

		formatted = _format_refutation_result([_FakeRefutation()], baseline_value=2.0)
		self.assertEqual(formatted["status"], "ok")
		self.assertIn("readable summary", formatted["summary"])
		self.assertNotIn("object at 0x", formatted["summary"])

		formatted_empty = _format_refutation_result([], baseline_value=2.0)
		self.assertEqual(formatted_empty["status"], "unavailable")

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

	def upload_messy_csv(self):
		rows = [
			"customerID,Tenure,TotalCharges,Contract,Churn",
		]
		for index in range(30):
			charge = "" if index == 3 else str(20.5 + index)
			contract = "Month-to-month" if index % 2 else "Two year"
			churn = "Yes" if index % 3 == 0 else "No"
			rows.append(f"C{index:04d},{index},{charge},{contract},{churn}")
		rows.append(rows[1])
		csv_content = "\n".join(rows) + "\n"
		upload_file = SimpleUploadedFile(
			"messy.csv",
			csv_content.encode("utf-8"),
			content_type="text/csv",
		)
		response = self.client.post("/api/upload_csv/", {"file": upload_file}, format="multipart")
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		return response.data

	def test_agent_profile_flags_data_issues(self):
		response_data = self.upload_messy_csv()
		response = self.client.post(
			"/api/agent/profile/",
			{"graph_id": response_data["graph_id"]},
			format="json",
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data["dataset_source"], "raw")
		self.assertEqual(response.data["column_count"], 5)
		issue_types = {item["issue_type"] for item in response.data["issues"]}
		self.assertIn("id_like_column", issue_types)
		self.assertIn("duplicate_rows", issue_types)
		issue_columns = {
			item["column"] for item in response.data["issues"] if item["issue_type"] == "some_missing"
		}
		self.assertIn("TotalCharges", issue_columns)

	def test_agent_suggest_cleaning_returns_steps(self):
		response_data = self.upload_messy_csv()
		response = self.client.post(
			"/api/agent/suggest_cleaning/",
			{"graph_id": response_data["graph_id"]},
			format="json",
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		step_ids = {item["step_id"] for item in response.data["steps"]}
		self.assertIn("drop_column:customerID", step_ids)
		self.assertIn("drop_duplicate_rows:__dataset__", step_ids)
		self.assertIn("impute_missing:TotalCharges", step_ids)

	def test_agent_suggest_cleaning_flags_collinear_pair(self):
		rows = ["A,B,C"]
		for index in range(30):
			rows.append(f"{index},{index * 2},{(index * 7) % 13}")
		upload_file = SimpleUploadedFile(
			"collinear.csv",
			("\n".join(rows) + "\n").encode("utf-8"),
			content_type="text/csv",
		)
		upload_response = self.client.post(
			"/api/upload_csv/", {"file": upload_file}, format="multipart"
		)
		self.assertEqual(upload_response.status_code, status.HTTP_200_OK)

		profile_response = self.client.post(
			"/api/agent/profile/", {"graph_id": upload_response.data["graph_id"]}, format="json"
		)
		self.assertEqual(profile_response.status_code, status.HTTP_200_OK)
		issue_types = {item["issue_type"] for item in profile_response.data["issues"]}
		self.assertIn("collinear_pair", issue_types)

		plan_response = self.client.post(
			"/api/agent/suggest_cleaning/",
			{"graph_id": upload_response.data["graph_id"]},
			format="json",
		)
		self.assertEqual(plan_response.status_code, status.HTTP_200_OK)
		step_ids = {item["step_id"] for item in plan_response.data["steps"]}
		self.assertIn("drop_column:B", step_ids)

	def test_agent_apply_cleaning_persists_cleaned_file_and_drops_variables(self):
		response_data = self.upload_messy_csv()
		graph_id = response_data["graph_id"]

		suggest_response = self.client.post(
			"/api/agent/suggest_cleaning/", {"graph_id": graph_id}, format="json"
		)
		self.assertEqual(suggest_response.status_code, status.HTTP_200_OK)

		apply_response = self.client.post(
			"/api/agent/apply_cleaning/",
			{"graph_id": graph_id, "steps": suggest_response.data["steps"]},
			format="json",
		)

		self.assertEqual(apply_response.status_code, status.HTTP_200_OK)
		self.assertIn("customerID", apply_response.data["dropped_columns"])
		self.assertLess(
			apply_response.data["row_count_after"], apply_response.data["row_count_before"]
		)
		variable_names = {item["name"] for item in apply_response.data["variables"]}
		self.assertNotIn("customerID", variable_names)

		graph = CausalGraph.objects.get(id=graph_id)
		self.assertTrue(graph.cleaned_file)
		self.assertTrue(graph.cleaning_plan)

		profile_response = self.client.post(
			"/api/agent/profile/", {"graph_id": graph_id}, format="json"
		)
		self.assertEqual(profile_response.status_code, status.HTTP_200_OK)
		self.assertEqual(profile_response.data["dataset_source"], "cleaned")

	def test_agent_suggest_model_without_llm_uses_heuristics(self):
		response_data = self.upload_messy_csv()

		with override_settings(OPENAI_API_KEY=""):
			response = self.client.post(
				"/api/agent/suggest_model/",
				{"graph_id": response_data["graph_id"]},
				format="json",
			)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertFalse(response.data["llm_used"])
		self.assertTrue(response.data["outcome_candidates"])
		outcome_names = [item["name"] for item in response.data["outcome_candidates"]]
		self.assertIn("Churn", outcome_names)
		self.assertIn("recommended_estimator", response.data)
		self.assertIn("identification", response.data)
		self.assertTrue(response.data["reasoning"])
		self.assertGreater(len(response.data["reasoning"].split(". ")), 1)

	@patch("causal_app.services.get_causal_model_class", return_value=_FakeCausalModel)
	def test_agent_compare_models_reports_stability(self, _mock_model_class):
		response_data = self.upload_sample_csv()
		graph_id = response_data["graph_id"]
		variable_by_name = {item["name"]: item["id"] for item in response_data["variables"]}

		self.client.post(
			"/api/save_graph/",
			{
				"graph_id": graph_id,
				"name": "Comparison Graph",
				"edges": [
					{"source": "A", "target": "B", "directed": True},
					{"source": "C", "target": "B", "directed": True},
					{"source": "C", "target": "A", "directed": True},
				],
			},
			format="json",
		)

		response = self.client.post(
			"/api/agent/compare_models/",
			{
				"graph_id": graph_id,
				"treatment": variable_by_name["A"],
				"outcome": variable_by_name["B"],
			},
			format="json",
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertGreaterEqual(len(response.data["models"]), 2)
		model_names = [item["name"] for item in response.data["models"]]
		self.assertIn("Canvas model", model_names)
		effects = [item["estimated_effect"] for item in response.data["models"]]
		self.assertTrue(all(value == 1.5 for value in effects))
		self.assertEqual(response.data["stability"]["verdict"], "stable")
		self.assertIn("stable", response.data["stability"]["summary"])

	@patch(
		"causal_app.views.suggest_model_with_openai",
		return_value={
			"edges": [
				{"source": "Tenure", "target": "Churn", "directed": True, "reason": "Longer tenure reduces churn."}
			],
			"treatment_candidates": ["Contract"],
			"outcome_candidates": ["Churn"],
			"unobserved_confounders": ["customer income"],
			"notes": "Contract type is the most actionable lever.",
		},
	)
	@override_settings(OPENAI_API_KEY="test-key")
	def test_agent_suggest_model_with_llm(self, _mock_model):
		response_data = self.upload_messy_csv()

		response = self.client.post(
			"/api/agent/suggest_model/",
			{"graph_id": response_data["graph_id"], "context": "telco churn"},
			format="json",
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertTrue(response.data["llm_used"])
		edge = response.data["edges"][0]
		self.assertEqual(edge["source"], "Tenure")
		self.assertIn("verification_status", edge)
		treatment_names = [item["name"] for item in response.data["treatment_candidates"]]
		self.assertIn("Contract", treatment_names)
		variable_by_name = {item["name"]: item["id"] for item in response_data["variables"]}
		treatment = next(
			item for item in response.data["treatment_candidates"] if item["name"] == "Contract"
		)
		self.assertEqual(treatment["variable_id"], variable_by_name["Contract"])
		self.assertTrue(
			any("unobserved confounder" in note.lower() for note in response.data["notes"])
		)

	def test_agent_suggest_model_respects_excluded_variables(self):
		response_data = self.upload_messy_csv()

		with override_settings(OPENAI_API_KEY=""):
			response = self.client.post(
				"/api/agent/suggest_model/",
				{
					"graph_id": response_data["graph_id"],
					"excluded_variables": ["Tenure", "customerID"],
				},
				format="json",
			)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		mentioned = set()
		for edge in response.data["edges"]:
			mentioned.add(edge["source"])
			mentioned.add(edge["target"])
		for item in response.data["treatment_candidates"] + response.data["outcome_candidates"]:
			mentioned.add(item["name"])
		self.assertNotIn("Tenure", mentioned)
		self.assertNotIn("customerID", mentioned)

	@patch("causal_app.agent_service.get_causal_model_class", return_value=_FakeCausalModel)
	def test_agent_estimate_plan_uses_saved_canvas_graph(self, _mock_model_class):
		response_data = self.upload_sample_csv()
		graph_id = response_data["graph_id"]
		variable_by_name = {item["name"]: item["id"] for item in response_data["variables"]}

		self.client.post(
			"/api/save_graph/",
			{
				"graph_id": graph_id,
				"name": "Canvas Graph",
				"edges": [
					{"source": "A", "target": "B", "directed": True},
					{"source": "C", "target": "B", "directed": True},
					{"source": "C", "target": "A", "directed": True},
				],
			},
			format="json",
		)

		response = self.client.post(
			"/api/agent/estimate_plan/",
			{
				"graph_id": graph_id,
				"treatment": variable_by_name["A"],
				"outcome": variable_by_name["B"],
			},
			format="json",
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertTrue(response.data["identification"]["identifiable"])
		self.assertIn("C", response.data["identification"]["adjustment_set"])
		self.assertIn("method_name", response.data["recommended_estimator"])

		# Adapt the canvas: drop the confounder edges, keep only A -> B.
		self.client.post(
			"/api/save_graph/",
			{
				"graph_id": graph_id,
				"name": "Canvas Graph",
				"edges": [{"source": "A", "target": "B", "directed": True}],
			},
			format="json",
		)

		response = self.client.post(
			"/api/agent/estimate_plan/",
			{
				"graph_id": graph_id,
				"treatment": variable_by_name["A"],
				"outcome": variable_by_name["B"],
			},
			format="json",
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertTrue(response.data["identification"]["checked"])

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
