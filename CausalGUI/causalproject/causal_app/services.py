import os
from typing import Any

import matplotlib
import networkx as nx
import pandas as pd
from django.conf import settings

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def get_causal_model_class():
    from dowhy import CausalModel

    return CausalModel


def normalize_binary_outcome(data_frame: pd.DataFrame, outcome_name: str) -> pd.DataFrame:
    outcome_values = sorted(data_frame[outcome_name].dropna().unique().tolist())
    if outcome_values == [0, 1]:
        return data_frame

    most_common_value = data_frame[outcome_name].mode()[0]
    data_frame[outcome_name] = data_frame[outcome_name].apply(
        lambda value: 0 if value == most_common_value else 1
    )
    return data_frame


def build_dot_graph(edges: list[tuple[str, str]]) -> tuple[str, nx.DiGraph, set[str]]:
    graph = nx.DiGraph()
    graph.add_edges_from(edges)
    nodes = set(graph.nodes())
    dot_edges = [f'"{source}" -> "{target}"' for source, target in edges]
    dot_graph = "digraph {" + ";".join(dot_edges) + ";}"
    return dot_graph, graph, nodes


def select_estimation_method(identified_estimand: Any, requested_method: str | None) -> str | None:
    if requested_method:
        return requested_method

    try:
        if identified_estimand.get_backdoor_variables() is not None:
            return "backdoor.linear_regression"
        if identified_estimand.get_instrumental_variables() is not None:
            return "iv.instrumental_variable"
        if identified_estimand.get_frontdoor_variables() is not None:
            return "frontdoor.two_stage_regression"
    except Exception:
        return "backdoor.linear_regression"

    return None


def estimate_effect(
    data_frame: pd.DataFrame,
    treatment_name: str,
    outcome_name: str,
    dot_graph: str,
    requested_method: str | None,
) -> dict[str, Any]:
    causal_model_class = get_causal_model_class()
    model = causal_model_class(
        data=data_frame,
        treatment=treatment_name,
        outcome=outcome_name,
        graph=dot_graph,
    )

    identified_estimand = model.identify_effect()
    if identified_estimand is None:
        raise ValueError("Causal effect not identifiable from the given graph.")

    method_name = select_estimation_method(identified_estimand, requested_method)
    if method_name is None:
        raise ValueError("No valid estimation method for the identified effect.")

    causal_estimate = model.estimate_effect(identified_estimand, method_name=method_name)
    estimated_effect = (
        causal_estimate.value
        if hasattr(causal_estimate, "value")
        else getattr(causal_estimate, "estimate", str(causal_estimate))
    )

    return {
        "estimated_effect": estimated_effect,
        "method_name": method_name,
        "estimand_string": str(identified_estimand),
    }


def generate_graph_image(graph_id: int, graph: nx.DiGraph) -> str:
    graph_directory = os.path.join(settings.MEDIA_ROOT, "causal_graphs")
    os.makedirs(graph_directory, exist_ok=True)

    image_name = f"causal_graph_{graph_id}.png"
    image_path = os.path.join(graph_directory, image_name)

    positions = nx.spring_layout(graph)
    plt.figure(figsize=(6, 4))
    nx.draw_networkx_nodes(graph, positions, node_size=800, node_color="#a0cbe2")
    nx.draw_networkx_edges(
        graph,
        positions,
        arrows=True,
        arrowstyle="->",
        arrowsize=10,
        edge_color="gray",
    )
    nx.draw_networkx_labels(graph, positions, font_size=8, font_color="black")
    plt.tight_layout()
    plt.savefig(image_path)
    plt.close()

    return settings.MEDIA_URL.rstrip("/") + f"/causal_graphs/{image_name}"
