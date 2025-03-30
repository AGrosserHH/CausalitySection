# views.py

import os
import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt
from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import Variable, CausalGraph, CausalEdge
from dowhy import CausalModel


# Load the dataset (update path if needed)
DATA_PATH = os.path.join(settings.BASE_DIR, "data.csv")
df = pd.read_csv(DATA_PATH) if os.path.exists(DATA_PATH) else pd.DataFrame()


@api_view(['GET'])
def get_variables(request):
    """
    Returns only clean variable names (dataset columns).
    Filters out names like 'age_12345678'.
    """
    variables = Variable.objects.exclude(name__regex=r'.*_\d+$')
    names = variables.values_list('name', flat=True).distinct()
    return Response(list(names))


@api_view(['POST'])
def save_graph(request):
    """
    Save a graph with directed edges.
    JSON body:
    {
        "name": "GraphName",
        "edges": [
            { "source": "age", "target": "income", "directed": true },
            ...
        ]
    }
    """
    name = request.data.get("name", "Unnamed Graph")
    edges = request.data.get("edges", [])

    graph = CausalGraph.objects.create(name=name)

    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        directed = edge.get("directed", True)

        # Ensure all nodes exist
        source_var, _ = Variable.objects.get_or_create(name=source)
        target_var, _ = Variable.objects.get_or_create(name=target)

        CausalEdge.objects.create(
            graph=graph,
            source=source_var,
            target=target_var,
            directed=directed
        )

    return Response({"message": "Graph saved", "graph_id": graph.id})


@api_view(['POST'])
def causal_inference(request):
    """
    Computes causal inference and saves a PNG of the graph.
    JSON body:
    {
        "treatment": "age_1234",
        "outcome": "income_5678",
        "graph_id": 1
    }
    """
    treatment = request.data.get("treatment")
    outcome = request.data.get("outcome")
    graph_id = request.data.get("graph_id")

    try:
        graph = CausalGraph.objects.get(id=graph_id)
    except CausalGraph.DoesNotExist:
        return Response({"error": "Graph not found"}, status=404)

    edges = graph.edges.select_related("source", "target")

    # Ensure all referenced nodes exist in the DB
    for edge in edges:
        for var in [edge.source.name, edge.target.name]:
            Variable.objects.get_or_create(name=var)

    # Build DOT format
    dot = "digraph { " + "; ".join(
        f"{e.source.name} -> {e.target.name}"
        for e in edges if e.directed
    ) + " }"

    # Build CausalModel
    if df.empty or treatment not in df.columns or outcome not in df.columns:
        return Response({"error": "Dataset missing treatment/outcome"}, status=400)

    model = CausalModel(
        data=df,
        treatment=[treatment],
        outcome=[outcome],
        graph=dot
    )

    identified_estimand = model.identify_effect()
    estimate = model.estimate_effect(identified_estimand, method_name="backdoor.linear_regression")

    # Draw graph with NetworkX
    G = nx.DiGraph()
    for edge in edges:
        G.add_edge(edge.source.name, edge.target.name)

    plt.figure(figsize=(8, 6))
    pos = nx.spring_layout(G)
    nx.draw(G, pos, with_labels=True, arrows=True, node_color="skyblue", node_size=1500)
    nx.draw_networkx_edges(G, pos, arrows=True)

    # Save graph PNG
    graph_dir = os.path.join(settings.MEDIA_ROOT, "graphs")
    os.makedirs(graph_dir, exist_ok=True)
    image_name = f"graph_{graph.id}.png"
    image_path = os.path.join(graph_dir, image_name)
    plt.savefig(image_path)
    plt.close()

    # Save path to DB
    graph.image_path = f"graphs/{image_name}"
    graph.save()

    return Response({
        "treatment": treatment,
        "outcome": outcome,
        "estimated_effect": estimate.value,
        "graph_image": f"{settings.MEDIA_URL}graphs/{image_name}"
    })
