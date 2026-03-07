import logging
import os

import networkx as nx
import pandas as pd
from django.conf import settings
from django.db import transaction
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from .models import CausalEdge, CausalGraph, EdgeEvidence, Variable
from .openai_service import suggest_edges_with_openai
from .serializers import (
    AssessQueryRequestSerializer,
    AssessQueryResponseSerializer,
    CausalInferenceRequestSerializer,
    CausalInferenceResponseSerializer,
    GraphDetailsResponseSerializer,
    OpenAIDraftGraphRequestSerializer,
    OpenAIDraftGraphResponseSerializer,
    OpenAISuggestEdgesRequestSerializer,
    OpenAISuggestEdgesResponseSerializer,
    RobustnessDashboardRequestSerializer,
    RobustnessDashboardResponseSerializer,
    RootCauseRequestSerializer,
    RootCauseResponseSerializer,
    SaveGraphRequestSerializer,
    SaveGraphResponseSerializer,
    UploadCsvResponseSerializer,
    WhatIfRequestSerializer,
    WhatIfResponseSerializer,
)
from .services import (
    build_dot_graph,
    compute_root_cause_attributions,
    compute_simple_counterfactual,
    derive_graph_hypotheses,
    edge_status_from_evidence,
    estimate_effect,
    get_causal_model_class,
    generate_graph_image,
    normalize_binary_outcome,
    run_estimator_comparison,
    run_refutations_and_sensitivity,
    select_estimation_method,
    verify_proposed_edges,
)

logger = logging.getLogger("causal")


def _first_error(errors):
    if isinstance(errors, list) and errors:
        return _first_error(errors[0])
    if isinstance(errors, dict):
        first_key = next(iter(errors), None)
        if first_key is None:
            return "Invalid request data."
        return _first_error(errors[first_key])
    return str(errors)


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def upload_csv(request):
    file_obj = request.FILES.get("file")
    if not file_obj:
        return Response({"error": "No file provided."}, status=400)

    if not file_obj.name.lower().endswith(".csv"):
        return Response({"error": "Only CSV files are accepted."}, status=400)

    graph = CausalGraph.objects.create(name=f"Graph from {file_obj.name}")
    graph.data_file.save(file_obj.name, file_obj, save=True)

    try:
        data_frame = pd.read_csv(graph.data_file.path)
    except Exception as exc:
        return Response({"error": f"Could not parse CSV: {exc}"}, status=400)

    columns = list(data_frame.columns)
    if not columns:
        return Response({"error": "CSV has no columns."}, status=400)

    variables = []
    for column in columns:
        variable = Variable.objects.create(name=column, graph=graph)
        variables.append({"id": variable.id, "name": variable.name})

    preview_data = data_frame.head(3).to_dict(orient="records")
    response_payload = {
        "graph_id": graph.id,
        "graph_name": graph.name,
        "variables": variables,
        "preview": preview_data,
    }
    response_serializer = UploadCsvResponseSerializer(data=response_payload)
    response_serializer.is_valid(raise_exception=True)
    return Response(response_serializer.data)


@api_view(["GET"])
def get_variables(request):
    variables = Variable.objects.exclude(name__regex=r".*_\d+$")
    names = variables.values_list("name", flat=True).distinct()
    return Response(list(names))


@api_view(["POST"])
def save_graph(request):
    serializer = SaveGraphRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"error": _first_error(serializer.errors)}, status=400)

    graph_id = serializer.validated_data.get("graph_id")
    name = serializer.validated_data.get("name", "Unnamed Graph")
    edges = serializer.validated_data.get("edges", [])

    if graph_id:
        try:
            graph = CausalGraph.objects.get(id=graph_id)
            graph.name = name
            graph.save(update_fields=["name"])
        except CausalGraph.DoesNotExist:
            return Response({"error": "Graph not found."}, status=404)
    else:
        graph = CausalGraph.objects.create(name=name)

    try:
        with transaction.atomic():
            graph.edges.all().delete()

            for edge in edges:
                source_name = edge["source"]
                target_name = edge["target"]
                directed = edge["directed"]

                try:
                    source_var = Variable.objects.get(name=source_name, graph=graph)
                    target_var = Variable.objects.get(name=target_name, graph=graph)
                except Variable.DoesNotExist:
                    return Response(
                        {
                            "error": (
                                f"Variable '{source_name}' or '{target_name}' "
                                "not found in this graph."
                            )
                        },
                        status=400,
                    )

                edge_object = CausalEdge.objects.create(
                    graph=graph,
                    source=source_var,
                    target=target_var,
                    directed=directed,
                    manual_lock=bool(edge.get("manual_lock", False)),
                )

                evidence_items = edge.get("evidence", [])
                if not evidence_items:
                    evidence_items = [
                        {
                            "evidence_type": "manual",
                            "status": "supported",
                            "details": {"reason": "User-authored edge"},
                        }
                    ]

                for evidence_item in evidence_items:
                    evidence_type = str(evidence_item.get("evidence_type", "manual"))
                    status_value = str(evidence_item.get("status", "supported"))
                    if evidence_type not in {
                        "semantic_prior",
                        "ci_test",
                        "score_search",
                        "temporal_prior",
                        "manual",
                        "llm",
                    }:
                        evidence_type = "manual"
                    if status_value not in {"supported", "weak", "rejected", "conflict"}:
                        status_value = "supported"

                    EdgeEvidence.objects.create(
                        edge=edge_object,
                        evidence_type=evidence_type,
                        status=status_value,
                        score=evidence_item.get("score"),
                        details=evidence_item.get("details", {}),
                    )
    except Exception as exc:
        logger.exception("Failed to save graph edges")
        return Response({"error": f"Failed to save graph: {exc}"}, status=400)

    response_serializer = SaveGraphResponseSerializer(
        data={"message": "Graph saved", "graph_id": graph.id}
    )
    response_serializer.is_valid(raise_exception=True)
    return Response(response_serializer.data)


@api_view(["POST"])
def causal_inference(request):
    serializer = CausalInferenceRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"error": _first_error(serializer.errors)}, status=400)

    graph_id = serializer.validated_data["graph_id"]
    treatment_id = serializer.validated_data["treatment"]
    outcome_id = serializer.validated_data["outcome"]
    requested_method = serializer.validated_data.get("method_name")

    try:
        graph = CausalGraph.objects.get(id=graph_id)
    except CausalGraph.DoesNotExist:
        return Response({"error": "Graph not found."}, status=404)

    if not graph.data_file:
        return Response({"error": "No dataset file linked to graph."}, status=400)

    dataset_path = graph.data_file.path
    if not os.path.exists(dataset_path):
        logger.error("Dataset file not found: %s", dataset_path)
        return Response(
            {"error": f"Dataset file not found: {graph.data_file.name}"},
            status=400,
        )

    try:
        treatment_var = Variable.objects.get(id=treatment_id, graph=graph)
        outcome_var = Variable.objects.get(id=outcome_id, graph=graph)
    except Variable.DoesNotExist:
        return Response(
            {"error": "Treatment or outcome variable was not found in the graph."},
            status=400,
        )

    try:
        data_frame = pd.read_csv(dataset_path)
    except Exception as exc:
        return Response({"error": f"Failed to read dataset: {exc}"}, status=400)

    treatment_name = treatment_var.name
    outcome_name = outcome_var.name

    if treatment_name not in data_frame.columns or outcome_name not in data_frame.columns:
        return Response(
            {"error": "Treatment or outcome variable not found in dataset."},
            status=400,
        )

    edges = CausalEdge.objects.filter(graph_id=graph_id)
    if not edges.exists():
        return Response({"error": "No causal graph found for the given graph_id."}, status=404)

    edge_list = [(edge.source.name, edge.target.name) for edge in edges]
    dot_graph, directed_graph, node_names = build_dot_graph(edge_list)

    if treatment_name not in node_names or outcome_name not in node_names:
        return Response(
            {"error": "Treatment or outcome is not a node in the causal graph."},
            status=400,
        )

    missing_columns = [name for name in node_names if name not in data_frame.columns]
    if missing_columns:
        return Response(
            {
                "error": (
                    "Variables from graph not found in dataset: "
                    + ", ".join(sorted(missing_columns))
                )
            },
            status=400,
        )

    if not nx.is_directed_acyclic_graph(directed_graph):
        return Response(
            {"error": "The causal graph contains cycles (must be a DAG)."},
            status=400,
        )

    try:
        data_frame = normalize_binary_outcome(data_frame, outcome_name)
        inference_result = estimate_effect(
            data_frame,
            treatment_name,
            outcome_name,
            dot_graph,
            requested_method,
        )
        graph_image_url = generate_graph_image(int(graph_id), directed_graph)
    except ImportError:
        return Response({"error": "DoWhy library is not installed on the server."}, status=500)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=400)
    except Exception as exc:
        logger.exception("Causal inference failed")
        return Response({"error": f"Causal inference failed: {exc}"}, status=400)

    response_payload = {
        "estimated_effect": float(inference_result["estimated_effect"]),
        "method_name": inference_result["method_name"],
        "graph_image": graph_image_url,
        "estimand_string": inference_result["estimand_string"],
    }
    response_serializer = CausalInferenceResponseSerializer(data=response_payload)
    response_serializer.is_valid(raise_exception=True)
    return Response(response_serializer.data, status=200)


@api_view(["POST"])
def openai_suggest_edges(request):
    serializer = OpenAISuggestEdgesRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"error": _first_error(serializer.errors)}, status=400)

    if not settings.OPENAI_API_KEY:
        return Response(
            {"error": "OPENAI_API_KEY is not configured on the server."},
            status=400,
        )

    variables = serializer.validated_data["variables"]
    context = serializer.validated_data.get("context", "")
    max_edges = serializer.validated_data.get("max_edges", 10)

    try:
        edges = suggest_edges_with_openai(variables=variables, context=context, max_edges=max_edges)
    except ImportError:
        return Response({"error": "OpenAI package is not installed on the server."}, status=500)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=400)
    except Exception as exc:
        logger.exception("OpenAI edge suggestion failed")
        return Response({"error": f"OpenAI request failed: {exc}"}, status=502)

    response_serializer = OpenAISuggestEdgesResponseSerializer(data={"edges": edges})
    response_serializer.is_valid(raise_exception=True)
    return Response(response_serializer.data, status=200)


@api_view(["POST"])
def openai_draft_graph(request):
    serializer = OpenAIDraftGraphRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"error": _first_error(serializer.errors)}, status=400)

    if not settings.OPENAI_API_KEY:
        return Response({"error": "OPENAI_API_KEY is not configured on the server."}, status=400)

    graph_id = serializer.validated_data["graph_id"]
    context = serializer.validated_data.get("context", "")
    max_edges = serializer.validated_data.get("max_edges", 10)

    try:
        graph = CausalGraph.objects.get(id=graph_id)
    except CausalGraph.DoesNotExist:
        return Response({"error": "Graph not found."}, status=404)

    if not graph.data_file:
        return Response({"error": "No dataset file linked to graph."}, status=400)

    dataset_path = graph.data_file.path
    if not os.path.exists(dataset_path):
        return Response({"error": f"Dataset file not found: {graph.data_file.name}"}, status=400)

    try:
        data_frame = pd.read_csv(dataset_path)
    except Exception as exc:
        return Response({"error": f"Failed to read dataset: {exc}"}, status=400)

    variable_names = list(graph.variables.values_list("name", flat=True))
    if len(variable_names) < 2:
        return Response({"error": "At least two variables are required."}, status=400)

    try:
        proposed_edges = suggest_edges_with_openai(
            variables=variable_names,
            context=context,
            max_edges=max_edges,
        )
        verified_edges = verify_proposed_edges(data_frame, proposed_edges)
        hypotheses = derive_graph_hypotheses(variable_names, verified_edges)
    except ImportError:
        return Response({"error": "OpenAI package is not installed on the server."}, status=500)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=400)
    except Exception as exc:
        logger.exception("OpenAI draft graph failed")
        return Response({"error": f"OpenAI draft failed: {exc}"}, status=502)

    response_payload = {
        "edges": verified_edges,
        "confounder_candidates": hypotheses["confounder_candidates"],
        "iv_candidates": hypotheses["iv_candidates"],
        "missing_confounder_hypotheses": hypotheses["missing_confounder_hypotheses"],
    }
    response_serializer = OpenAIDraftGraphResponseSerializer(data=response_payload)
    response_serializer.is_valid(raise_exception=True)
    return Response(response_serializer.data, status=200)


@api_view(["GET"])
def graph_details(request, graph_id: int):
    try:
        graph = CausalGraph.objects.get(id=graph_id)
    except CausalGraph.DoesNotExist:
        return Response({"error": "Graph not found."}, status=404)

    edge_payloads = []
    for edge in graph.edges.select_related("source", "target").prefetch_related("evidences").all():
        evidence_items = [
            {
                "evidence_type": evidence.evidence_type,
                "status": evidence.status,
                "score": evidence.score,
                "details": evidence.details,
            }
            for evidence in edge.evidences.all()
        ]
        edge_payloads.append(
            {
                "source": edge.source.name,
                "target": edge.target.name,
                "directed": edge.directed,
                "manual_lock": edge.manual_lock,
                "status": edge_status_from_evidence(evidence_items),
                "evidence": evidence_items,
            }
        )

    response_serializer = GraphDetailsResponseSerializer(
        data={
            "graph_id": graph.id,
            "edges": edge_payloads,
        }
    )
    response_serializer.is_valid(raise_exception=True)
    return Response(response_serializer.data, status=200)


@api_view(["POST"])
def assess_query(request):
    serializer = AssessQueryRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"error": _first_error(serializer.errors)}, status=400)

    graph_id = serializer.validated_data["graph_id"]
    treatment_id = serializer.validated_data["treatment"]
    outcome_id = serializer.validated_data["outcome"]
    estimand = serializer.validated_data["estimand"]

    try:
        graph = CausalGraph.objects.get(id=graph_id)
    except CausalGraph.DoesNotExist:
        return Response({"error": "Graph not found."}, status=404)

    if not graph.data_file:
        return Response({"error": "No dataset file linked to graph."}, status=400)

    try:
        treatment_var = Variable.objects.get(id=treatment_id, graph=graph)
        outcome_var = Variable.objects.get(id=outcome_id, graph=graph)
    except Variable.DoesNotExist:
        return Response({"error": "Treatment or outcome variable was not found in the graph."}, status=400)

    try:
        data_frame = pd.read_csv(graph.data_file.path)
    except Exception as exc:
        return Response({"error": f"Failed to read dataset: {exc}"}, status=400)

    edges = CausalEdge.objects.filter(graph_id=graph_id)
    if not edges.exists():
        return Response({"error": "No causal graph found for the given graph_id."}, status=404)

    edge_list = [(edge.source.name, edge.target.name) for edge in edges]
    dot_graph, _, node_names = build_dot_graph(edge_list)

    if treatment_var.name not in node_names or outcome_var.name not in node_names:
        return Response({"error": "Treatment or outcome is not a node in the causal graph."}, status=400)

    try:
        model = get_causal_model_class()(
            data=data_frame,
            treatment=treatment_var.name,
            outcome=outcome_var.name,
            graph=dot_graph,
        )
        identified_estimand = model.identify_effect()
    except Exception as exc:
        return Response({"error": f"Identification failed: {exc}"}, status=400)

    if identified_estimand is None:
        response_payload = {
            "identifiable": False,
            "selected_estimand": estimand,
            "suggested_method": "",
            "adjustment_set": [],
            "iv_candidates": [],
            "frontdoor_variables": [],
            "overlap_ok": False,
            "overlap_warnings": ["Causal effect is not identifiable from current graph."],
            "badge": "reject",
            "reasons": ["Identification failed."],
        }
    else:
        method_name = select_estimation_method(identified_estimand, None) or ""
        adjustment_set = list((identified_estimand.get_backdoor_variables() or []))
        iv_candidates = list((identified_estimand.get_instrumental_variables() or []))
        frontdoor_variables = list((identified_estimand.get_frontdoor_variables() or []))

        overlap_warnings = []
        overlap_ok = True
        treatment_series = pd.to_numeric(data_frame[treatment_var.name], errors="coerce").dropna()
        if not treatment_series.empty:
            min_value = float(treatment_series.min())
            max_value = float(treatment_series.max())
            if min_value == max_value:
                overlap_ok = False
                overlap_warnings.append("Treatment has no variation; overlap assumption likely fails.")

        if not overlap_ok:
            badge = "reject"
            reasons = ["Overlap check failed."]
        elif method_name and (adjustment_set or iv_candidates or frontdoor_variables):
            badge = "trust"
            reasons = ["Identification and admissibility checks passed."]
        else:
            badge = "caution"
            reasons = ["Identification found but admissibility evidence is limited."]

        response_payload = {
            "identifiable": True,
            "selected_estimand": estimand,
            "suggested_method": method_name,
            "adjustment_set": adjustment_set,
            "iv_candidates": iv_candidates,
            "frontdoor_variables": frontdoor_variables,
            "overlap_ok": overlap_ok,
            "overlap_warnings": overlap_warnings,
            "badge": badge,
            "reasons": reasons,
        }

    response_serializer = AssessQueryResponseSerializer(data=response_payload)
    response_serializer.is_valid(raise_exception=True)
    return Response(response_serializer.data, status=200)


def _load_graph_dataset_and_nodes(graph_id: int):
    try:
        graph = CausalGraph.objects.get(id=graph_id)
    except CausalGraph.DoesNotExist:
        return None, None, None, Response({"error": "Graph not found."}, status=404)

    if not graph.data_file:
        return None, None, None, Response({"error": "No dataset file linked to graph."}, status=400)

    try:
        data_frame = pd.read_csv(graph.data_file.path)
    except Exception as exc:
        return None, None, None, Response({"error": f"Failed to read dataset: {exc}"}, status=400)

    edges = CausalEdge.objects.filter(graph_id=graph_id)
    if not edges.exists():
        return None, None, None, Response({"error": "No causal graph found for the given graph_id."}, status=404)

    edge_list = [(edge.source.name, edge.target.name) for edge in edges]
    dot_graph, _, node_names = build_dot_graph(edge_list)
    return graph, data_frame, (dot_graph, node_names), None


@api_view(["POST"])
def robustness_dashboard(request):
    serializer = RobustnessDashboardRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"error": _first_error(serializer.errors)}, status=400)

    graph_id = serializer.validated_data["graph_id"]
    treatment_id = serializer.validated_data["treatment"]
    outcome_id = serializer.validated_data["outcome"]
    requested_estimators = serializer.validated_data.get("estimators") or []

    graph, data_frame, graph_data, error_response = _load_graph_dataset_and_nodes(graph_id)
    if error_response is not None:
        return error_response
    dot_graph, node_names = graph_data

    try:
        treatment_var = Variable.objects.get(id=treatment_id, graph=graph)
        outcome_var = Variable.objects.get(id=outcome_id, graph=graph)
    except Variable.DoesNotExist:
        return Response({"error": "Treatment or outcome variable was not found in the graph."}, status=400)

    if treatment_var.name not in node_names or outcome_var.name not in node_names:
        return Response({"error": "Treatment or outcome is not a node in the causal graph."}, status=400)

    try:
        model = get_causal_model_class()(
            data=data_frame,
            treatment=treatment_var.name,
            outcome=outcome_var.name,
            graph=dot_graph,
        )
        identified_estimand = model.identify_effect()
    except Exception as exc:
        return Response({"error": f"Failed to build causal model: {exc}"}, status=400)

    if identified_estimand is None:
        return Response({"error": "Causal effect not identifiable for this query."}, status=400)

    method_names = requested_estimators or [
        "backdoor.linear_regression",
        "backdoor.propensity_score_matching",
        "backdoor.propensity_score_weighting",
        "backdoor.doubly_robust_estimator",
    ]

    estimator_comparison = run_estimator_comparison(model, identified_estimand, method_names)
    successful = next((item for item in estimator_comparison if not item.get("error")), None)
    baseline_method = successful["method_name"] if successful else ""

    baseline_estimate = None
    if baseline_method:
        try:
            baseline_estimate = model.estimate_effect(identified_estimand, method_name=baseline_method)
        except Exception:
            baseline_estimate = None

    if baseline_estimate is not None:
        refutations, sensitivity = run_refutations_and_sensitivity(
            model,
            identified_estimand,
            baseline_estimate,
        )
    else:
        refutations = {
            "placebo_treatment": {"status": "error", "summary": "No baseline estimate available.", "p_value": None},
            "dummy_outcome": {"status": "error", "summary": "No baseline estimate available.", "p_value": None},
            "random_common_cause": {"status": "error", "summary": "No baseline estimate available.", "p_value": None},
            "data_subsample": {"status": "error", "summary": "No baseline estimate available.", "p_value": None},
        }
        sensitivity = {
            "partial_r2": {"status": "error", "summary": "No baseline estimate available.", "p_value": None},
            "non_linear": {"status": "error", "summary": "No baseline estimate available.", "p_value": None},
        }

    response_payload = {
        "baseline_method": baseline_method,
        "estimator_comparison": estimator_comparison,
        "refutations": refutations,
        "sensitivity": sensitivity,
    }
    response_serializer = RobustnessDashboardResponseSerializer(data=response_payload)
    response_serializer.is_valid(raise_exception=True)
    return Response(response_serializer.data, status=200)


@api_view(["POST"])
def what_if_analysis(request):
    serializer = WhatIfRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"error": _first_error(serializer.errors)}, status=400)

    graph_id = serializer.validated_data["graph_id"]
    treatment_id = serializer.validated_data["treatment"]
    outcome_id = serializer.validated_data["outcome"]
    treatment_value = serializer.validated_data["treatment_value"]

    graph, data_frame, graph_data, error_response = _load_graph_dataset_and_nodes(graph_id)
    if error_response is not None:
        return error_response
    dot_graph, node_names = graph_data

    try:
        treatment_var = Variable.objects.get(id=treatment_id, graph=graph)
        outcome_var = Variable.objects.get(id=outcome_id, graph=graph)
    except Variable.DoesNotExist:
        return Response({"error": "Treatment or outcome variable was not found in the graph."}, status=400)

    if treatment_var.name not in node_names or outcome_var.name not in node_names:
        return Response({"error": "Treatment or outcome is not a node in the causal graph."}, status=400)

    estimated_ate = None
    try:
        model = get_causal_model_class()(
            data=data_frame,
            treatment=treatment_var.name,
            outcome=outcome_var.name,
            graph=dot_graph,
        )
        identified_estimand = model.identify_effect()
        if identified_estimand is not None:
            method_name = select_estimation_method(identified_estimand, None)
            if method_name:
                estimate = model.estimate_effect(identified_estimand, method_name=method_name)
                value = getattr(estimate, "value", None)
                if value is not None:
                    estimated_ate = float(value)
    except Exception:
        estimated_ate = None

    response_payload = compute_simple_counterfactual(
        data_frame=data_frame,
        treatment_name=treatment_var.name,
        outcome_name=outcome_var.name,
        estimated_ate=estimated_ate,
        treatment_value=float(treatment_value),
    )
    response_serializer = WhatIfResponseSerializer(data=response_payload)
    response_serializer.is_valid(raise_exception=True)
    return Response(response_serializer.data, status=200)


@api_view(["POST"])
def root_cause_analysis(request):
    serializer = RootCauseRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"error": _first_error(serializer.errors)}, status=400)

    graph_id = serializer.validated_data["graph_id"]
    outcome_id = serializer.validated_data["outcome"]

    graph, data_frame, _graph_data, error_response = _load_graph_dataset_and_nodes(graph_id)
    if error_response is not None:
        return error_response

    try:
        outcome_var = Variable.objects.get(id=outcome_id, graph=graph)
    except Variable.DoesNotExist:
        return Response({"error": "Outcome variable was not found in the graph."}, status=400)

    attributions = compute_root_cause_attributions(data_frame, outcome_var.name)
    response_serializer = RootCauseResponseSerializer(data=attributions)
    response_serializer.is_valid(raise_exception=True)
    return Response(response_serializer.data, status=200)
