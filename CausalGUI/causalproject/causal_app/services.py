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


def _safe_numeric_correlation(data_frame: pd.DataFrame, source: str, target: str) -> float | None:
    if source not in data_frame.columns or target not in data_frame.columns:
        return None

    try:
        pair = data_frame[[source, target]].apply(pd.to_numeric, errors="coerce").dropna()
    except Exception:
        return None

    if pair.empty:
        return None

    corr = pair[source].corr(pair[target])
    if corr is None or pd.isna(corr):
        return None
    return float(abs(corr))


def verify_proposed_edges(data_frame: pd.DataFrame, proposed_edges: list[dict]) -> list[dict]:
    verified_edges: list[dict] = []

    for item in proposed_edges:
        source = str(item.get("source", "")).strip()
        target = str(item.get("target", "")).strip()
        directed = bool(item.get("directed", True))
        reason = str(item.get("reason", "")).strip()

        if not source or not target or source == target:
            continue

        evidence = [
            {
                "evidence_type": "llm",
                "status": "supported",
                "details": {"reason": reason or "LLM-proposed edge"},
            }
        ]

        support_score = _safe_numeric_correlation(data_frame, source, target)

        if support_score is None:
            verification_status = "weak"
            evidence.append(
                {
                    "evidence_type": "score_search",
                    "status": "weak",
                    "score": None,
                    "details": {"note": "Insufficient numeric evidence for correlation check."},
                }
            )
        elif support_score >= 0.2:
            verification_status = "supported"
            evidence.append(
                {
                    "evidence_type": "score_search",
                    "status": "supported",
                    "score": support_score,
                    "details": {"metric": "abs_pearson_corr"},
                }
            )
        elif support_score >= 0.1:
            verification_status = "weak"
            evidence.append(
                {
                    "evidence_type": "score_search",
                    "status": "weak",
                    "score": support_score,
                    "details": {"metric": "abs_pearson_corr"},
                }
            )
        else:
            verification_status = "conflict"
            evidence.append(
                {
                    "evidence_type": "score_search",
                    "status": "rejected",
                    "score": support_score,
                    "details": {
                        "metric": "abs_pearson_corr",
                        "note": "LLM suggests edge, data support is weak.",
                    },
                }
            )

        verified_edges.append(
            {
                "source": source,
                "target": target,
                "directed": directed,
                "reason": reason,
                "verification_status": verification_status,
                "verification_score": support_score,
                "evidence": evidence,
            }
        )

    return verified_edges


def derive_graph_hypotheses(variable_names: list[str], verified_edges: list[dict]) -> dict[str, list[str]]:
    outgoing_counts: dict[str, int] = {name: 0 for name in variable_names}
    incoming_counts: dict[str, int] = {name: 0 for name in variable_names}

    for edge in verified_edges:
        if edge.get("verification_status") in {"supported", "weak"}:
            source = edge["source"]
            target = edge["target"]
            if source in outgoing_counts:
                outgoing_counts[source] += 1
            if target in incoming_counts:
                incoming_counts[target] += 1

    confounders = [
        name
        for name in variable_names
        if outgoing_counts.get(name, 0) >= 2 and incoming_counts.get(name, 0) >= 1
    ]
    iv_candidates = [
        name
        for name in variable_names
        if outgoing_counts.get(name, 0) >= 1 and incoming_counts.get(name, 0) == 0
    ]

    conflict_edges = [
        edge
        for edge in verified_edges
        if edge.get("verification_status") in {"conflict", "rejected"}
    ]
    missing_confounders = []
    if conflict_edges:
        missing_confounders.append(
            "Several LLM-proposed edges conflict with data evidence; latent confounding may exist."
        )

    return {
        "confounder_candidates": confounders[:8],
        "iv_candidates": iv_candidates[:8],
        "missing_confounder_hypotheses": missing_confounders,
    }


def edge_status_from_evidence(evidences: list[dict]) -> str:
    statuses = [str(item.get("status", "")).lower() for item in evidences]
    if any(status in {"conflict", "rejected"} for status in statuses):
        return "conflict"
    if any(status == "weak" for status in statuses):
        return "weak"
    return "supported"


def _format_refutation_result(result: Any) -> dict[str, Any]:
    if result is None:
        return {"status": "unavailable", "summary": "No refutation output."}

    p_value = getattr(result, "p_value", None)
    if p_value is not None:
        try:
            p_value = float(p_value)
        except Exception:
            p_value = None

    return {
        "status": "ok",
        "summary": str(result),
        "p_value": p_value,
    }


def run_estimator_comparison(
    model: Any,
    identified_estimand: Any,
    method_names: list[str],
) -> list[dict[str, Any]]:
    results = []
    for method_name in method_names:
        try:
            estimate = model.estimate_effect(identified_estimand, method_name=method_name)
            value = getattr(estimate, "value", None)
            if value is None:
                value = getattr(estimate, "estimate", None)
            value = float(value) if value is not None else None
            results.append(
                {
                    "method_name": method_name,
                    "estimated_effect": value,
                    "error": "",
                }
            )
        except Exception as exc:
            results.append(
                {
                    "method_name": method_name,
                    "estimated_effect": None,
                    "error": str(exc),
                }
            )
    return results


def run_refutations_and_sensitivity(
    model: Any,
    identified_estimand: Any,
    baseline_estimate: Any,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    refutations: dict[str, dict[str, Any]] = {}
    refuter_map = {
        "placebo_treatment": ("placebo_treatment_refuter", {}),
        "dummy_outcome": ("dummy_outcome_refuter", {}),
        "random_common_cause": ("random_common_cause", {}),
        "data_subsample": (
            "data_subset_refuter",
            {
                "subset_fraction": 0.8,
                "num_simulations": 20,
            },
        ),
    }

    for key, (method_name, kwargs) in refuter_map.items():
        try:
            output = model.refute_estimate(
                identified_estimand,
                baseline_estimate,
                method_name=method_name,
                **kwargs,
            )
            refutations[key] = _format_refutation_result(output)
        except Exception as exc:
            refutations[key] = {
                "status": "error",
                "summary": str(exc),
                "p_value": None,
            }

    sensitivity: dict[str, dict[str, Any]] = {}
    sensitivity_map = {
        "partial_r2": "linear-partial-R2",
        "non_linear": "non-parametric-partial-R2",
    }
    for key, simulation_method in sensitivity_map.items():
        try:
            output = model.refute_estimate(
                identified_estimand,
                baseline_estimate,
                method_name="add_unobserved_common_cause",
                simulation_method=simulation_method,
            )
            sensitivity[key] = _format_refutation_result(output)
        except Exception as exc:
            sensitivity[key] = {
                "status": "error",
                "summary": str(exc),
                "p_value": None,
            }

    return refutations, sensitivity


def compute_simple_counterfactual(
    data_frame: pd.DataFrame,
    treatment_name: str,
    outcome_name: str,
    estimated_ate: float | None,
    treatment_value: float,
) -> dict[str, float | str | None]:
    baseline_outcome_mean = float(pd.to_numeric(data_frame[outcome_name], errors="coerce").dropna().mean())
    baseline_treatment_mean = float(
        pd.to_numeric(data_frame[treatment_name], errors="coerce").dropna().mean()
    )

    if estimated_ate is None:
        return {
            "baseline_outcome_mean": baseline_outcome_mean,
            "baseline_treatment_mean": baseline_treatment_mean,
            "estimated_ate": None,
            "counterfactual_outcome_mean": None,
            "note": "ATE unavailable; counterfactual mean could not be computed.",
        }

    counterfactual_outcome_mean = baseline_outcome_mean + estimated_ate * (
        float(treatment_value) - baseline_treatment_mean
    )
    return {
        "baseline_outcome_mean": baseline_outcome_mean,
        "baseline_treatment_mean": baseline_treatment_mean,
        "estimated_ate": float(estimated_ate),
        "counterfactual_outcome_mean": float(counterfactual_outcome_mean),
        "note": "Counterfactual computed from estimated ATE and treatment shift.",
    }


def compute_root_cause_attributions(
    data_frame: pd.DataFrame,
    outcome_name: str,
    top_k: int = 5,
) -> dict[str, list[dict[str, Any]]]:
    if outcome_name not in data_frame.columns:
        return {
            "anomaly_attribution": [],
            "distribution_change_attribution": [],
        }

    numeric = data_frame.apply(pd.to_numeric, errors="coerce")
    numeric = numeric.dropna(axis=1, how="all")
    if outcome_name not in numeric.columns:
        return {
            "anomaly_attribution": [],
            "distribution_change_attribution": [],
        }

    y = numeric[outcome_name].dropna()
    if y.empty:
        return {
            "anomaly_attribution": [],
            "distribution_change_attribution": [],
        }

    aligned = numeric.loc[y.index]
    threshold = y.quantile(0.9)
    anomaly_index = y[y >= threshold].index
    normal_index = y[y < threshold].index

    anomaly_scores = []
    dist_change_scores = []
    half = max(1, len(aligned) // 2)
    first_half = aligned.iloc[:half]
    second_half = aligned.iloc[half:]

    for column in aligned.columns:
        if column == outcome_name:
            continue
        series = aligned[column]
        corr = series.corr(y)
        corr = 0.0 if corr is None or pd.isna(corr) else float(abs(corr))

        anomaly_shift = 0.0
        if len(anomaly_index) > 0 and len(normal_index) > 0:
            anomaly_mean = aligned.loc[anomaly_index, column].mean()
            normal_mean = aligned.loc[normal_index, column].mean()
            if pd.notna(anomaly_mean) and pd.notna(normal_mean):
                anomaly_shift = float(abs(anomaly_mean - normal_mean))

        dist_shift = 0.0
        if not second_half.empty:
            first_mean = first_half[column].mean()
            second_mean = second_half[column].mean()
            if pd.notna(first_mean) and pd.notna(second_mean):
                dist_shift = float(abs(second_mean - first_mean))

        anomaly_scores.append(
            {
                "variable": column,
                "score": anomaly_shift * corr,
                "details": "Anomaly mean shift × |corr(var, outcome)|",
            }
        )
        dist_change_scores.append(
            {
                "variable": column,
                "score": dist_shift * corr,
                "details": "Temporal distribution shift × |corr(var, outcome)|",
            }
        )

    anomaly_scores.sort(key=lambda item: item["score"], reverse=True)
    dist_change_scores.sort(key=lambda item: item["score"], reverse=True)

    return {
        "anomaly_attribution": anomaly_scores[:top_k],
        "distribution_change_attribution": dist_change_scores[:top_k],
    }
