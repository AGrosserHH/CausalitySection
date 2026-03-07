import logging
import os

import networkx as nx
import pandas as pd
from django.db import transaction
from django.conf import settings
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from .models import CausalEdge, CausalGraph, Variable
from .openai_service import suggest_edges_with_openai
from .serializers import (
    CausalInferenceRequestSerializer,
    CausalInferenceResponseSerializer,
    OpenAISuggestEdgesRequestSerializer,
    OpenAISuggestEdgesResponseSerializer,
    SaveGraphRequestSerializer,
    SaveGraphResponseSerializer,
    UploadCsvResponseSerializer,
)
from .services import (
    build_dot_graph,
    estimate_effect,
    generate_graph_image,
    normalize_binary_outcome,
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

                CausalEdge.objects.create(
                    graph=graph,
                    source=source_var,
                    target=target_var,
                    directed=directed,
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
