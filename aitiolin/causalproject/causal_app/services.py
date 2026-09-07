import functools
import os
import warnings
from typing import Any

import matplotlib
import networkx as nx
import numpy as np
import pandas as pd
from django.conf import settings

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def get_causal_model_class():
    from dowhy import CausalModel

    return CausalModel


def suppress_numeric_estimation_warnings(func):
    """Silence numpy/statsmodels RuntimeWarnings raised during estimation.

    A singular regression design matrix (constant or perfectly collinear
    columns) makes statsmodels' condition-number check divide by zero. The
    estimate is still returned; the underlying data problem is surfaced to the
    user through the agent profiler (constant_column / collinear_pair issues)
    rather than as console spam on every run.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return func(*args, **kwargs)

    return wrapper


def normalize_binary_outcome(data_frame: pd.DataFrame, outcome_name: str) -> pd.DataFrame:
    unique_values = data_frame[outcome_name].dropna().unique()
    if len(unique_values) > 2:
        # Continuous or multi-valued outcome: collapsing it to 0/1 around the mode
        # would destroy the signal (e.g. a 186-value mortality rate becomes 185x"1"
        # and 1x"0"). Only genuinely binary outcomes are normalized.
        return data_frame

    outcome_values = sorted(unique_values.tolist())
    if outcome_values == [0, 1]:
        return data_frame

    most_common_value = data_frame[outcome_name].mode()[0]
    data_frame[outcome_name] = data_frame[outcome_name].apply(
        lambda value: 0 if value == most_common_value else 1
    )
    return data_frame


def preprocess_data_frame_for_causal(data_frame: pd.DataFrame) -> pd.DataFrame:
    processed = data_frame.copy()

    true_tokens = {"true", "t", "yes", "y", "1", "on"}
    false_tokens = {"false", "f", "no", "n", "0", "off"}
    boolean_tokens = true_tokens | false_tokens

    for column in processed.columns:
        series = processed[column]

        if pd.api.types.is_bool_dtype(series):
            processed[column] = series.astype("Int64").astype("float")
            continue

        if pd.api.types.is_numeric_dtype(series):
            continue

        normalized_text = series.astype("string").str.strip()
        normalized_lower = normalized_text.str.lower()
        non_empty = normalized_lower[normalized_lower.notna() & (normalized_lower != "")]

        if not non_empty.empty and non_empty.isin(boolean_tokens).all():
            bool_numeric = normalized_lower.map(
                lambda value: 1.0 if value in true_tokens else 0.0 if value in false_tokens else pd.NA
            )
            processed[column] = bool_numeric.astype("float")
            continue

        numeric_series = pd.to_numeric(series, errors="coerce")
        numeric_ratio = float(numeric_series.notna().mean())
        if numeric_ratio >= 0.8:
            processed[column] = numeric_series.astype("float")
            continue

        datetime_series = pd.to_datetime(series, errors="coerce", utc=True, format="mixed")
        datetime_ratio = float(datetime_series.notna().mean())
        if datetime_ratio >= 0.8:
            epoch_seconds = (
                (datetime_series - pd.Timestamp("1970-01-01", tz="UTC")) / pd.Timedelta(seconds=1)
            )
            processed[column] = epoch_seconds.astype("float")
            continue

        cleaned = normalized_text.replace({"": pd.NA, "nan": pd.NA, "none": pd.NA, "null": pd.NA})
        categories = cleaned.astype("category")
        category_codes = categories.cat.codes.replace(-1, pd.NA).astype("float")
        processed[column] = category_codes

    processed = processed.replace([float("inf"), float("-inf")], pd.NA)

    for column in processed.columns:
        series = processed[column]
        if not pd.api.types.is_numeric_dtype(series):
            continue

        numeric_series = pd.to_numeric(series, errors="coerce")
        if numeric_series.notna().any():
            median_value = float(numeric_series.median())
            processed[column] = numeric_series.fillna(median_value)
        else:
            processed[column] = numeric_series.fillna(0.0)

    return processed


def _escape_gml_label(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def build_dot_graph(edges: list[tuple[str, str]]) -> tuple[str, nx.DiGraph, set[str]]:
    graph = nx.DiGraph()
    graph.add_edges_from(edges)
    nodes = sorted(set(graph.nodes()))

    node_index = {name: index for index, name in enumerate(nodes)}
    gml_lines = ["graph[", "  directed 1"]

    for name in nodes:
        gml_lines.append(f'  node[ id {node_index[name]} label "{_escape_gml_label(name)}" ]')

    for source, target in edges:
        if source in node_index and target in node_index:
            gml_lines.append(
                f"  edge[ source {node_index[source]} target {node_index[target]} ]"
            )

    gml_lines.append("]")
    gml_graph = "\n".join(gml_lines)
    return gml_graph, graph, set(nodes)


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


@suppress_numeric_estimation_warnings
def estimate_effect(
    data_frame: pd.DataFrame,
    treatment_name: str,
    outcome_name: str,
    dot_graph: str,
    requested_method: str | None,
) -> dict[str, Any]:
    def to_numeric_or_category_codes(series: pd.Series) -> tuple[pd.Series, str]:
        numeric_series = pd.to_numeric(series, errors="coerce")
        if numeric_series.notna().any():
            return numeric_series, "numeric"

        normalized = series.astype("string").str.strip()
        normalized = normalized.replace({"": pd.NA, "nan": pd.NA, "none": pd.NA, "null": pd.NA})
        categorical = normalized.astype("category")
        coded = categorical.cat.codes.replace(-1, pd.NA).astype("float")
        return coded, "categorical"

    def estimate_diff_in_means() -> float:
        treatment_series, treatment_kind = to_numeric_or_category_codes(data_frame[treatment_name])
        outcome_series, _outcome_kind = to_numeric_or_category_codes(data_frame[outcome_name])
        valid_rows = treatment_series.notna() & outcome_series.notna()
        treatment_series = treatment_series[valid_rows]
        outcome_series = outcome_series[valid_rows]

        if treatment_series.empty:
            raise ValueError(
                "Unable to estimate effect: treatment/outcome have no usable rows after preprocessing."
            )

        unique_treatments = list(pd.unique(treatment_series.dropna()))
        if len(unique_treatments) < 2:
            raise ValueError("Unable to estimate effect: treatment has no variation.")

        if treatment_kind == "categorical":
            most_common_groups = treatment_series.value_counts().index.tolist()
            low_group = most_common_groups[0]
            high_group = most_common_groups[1]
        else:
            low_group = min(unique_treatments)
            high_group = max(unique_treatments)

        high_mean = float(outcome_series[treatment_series == high_group].mean())
        low_mean = float(outcome_series[treatment_series == low_group].mean())

        if pd.isna(high_mean) or pd.isna(low_mean):
            raise ValueError("Unable to estimate effect: insufficient outcome values in treatment groups.")

        return high_mean - low_mean

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

    try:
        causal_estimate = model.estimate_effect(identified_estimand, method_name=method_name)
    except Exception as exc:
        error_text = str(exc).lower()
        is_unknown_category_error = "found unknown categories" in error_text and "during transform" in error_text
        if not is_unknown_category_error:
            raise

        if method_name != "backdoor.linear_regression":
            try:
                fallback_method = "backdoor.linear_regression"
                causal_estimate = model.estimate_effect(identified_estimand, method_name=fallback_method)
                method_name = fallback_method
            except Exception as fallback_exc:
                fallback_error_text = str(fallback_exc).lower()
                fallback_unknown_category = (
                    "found unknown categories" in fallback_error_text
                    and "during transform" in fallback_error_text
                )
                if not fallback_unknown_category:
                    raise

                manual_effect = estimate_diff_in_means()
                return {
                    "estimated_effect": manual_effect,
                    "method_name": "backdoor.diff_in_means_fallback",
                    "estimand_string": str(identified_estimand),
                }
        else:
            manual_effect = estimate_diff_in_means()
            return {
                "estimated_effect": manual_effect,
                "method_name": "backdoor.diff_in_means_fallback",
                "estimand_string": str(identified_estimand),
            }

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


def _layered_positions(graph: nx.DiGraph) -> tuple[dict[str, tuple[float, float]], int, int]:
    """Left-to-right layered layout: column = topological generation, rows ordered
    by the mean row of each node's parents (a one-pass barycenter heuristic that
    keeps most arrows short and reduces crossings)."""
    if nx.is_directed_acyclic_graph(graph):
        generations = [list(layer) for layer in nx.topological_generations(graph)]
    else:  # cyclic graphs cannot be layered; fall back to a single column per node
        generations = [[node] for node in graph.nodes()]

    positions: dict[str, tuple[float, float]] = {}
    x_gap, y_gap = 3.2, 1.25
    for column, layer in enumerate(generations):
        def sort_key(node: str) -> tuple[float, str]:
            parent_rows = [positions[p][1] for p in graph.predecessors(node) if p in positions]
            return (-float(np.mean(parent_rows)) if parent_rows else 0.0, node)

        ordered = sorted(layer, key=sort_key)
        for row, node in enumerate(ordered):
            positions[node] = (column * x_gap, ((len(ordered) - 1) / 2 - row) * y_gap)
    max_rows = max(len(layer) for layer in generations) if generations else 1
    return positions, len(generations), max_rows


def draw_dag_figure(
    graph: nx.DiGraph,
    image_path: str,
    treatment_name: str | None = None,
    outcome_name: str | None = None,
) -> None:
    """Render the causal graph as a proper DAG: layered left-to-right, full node
    labels in boxes, arrowheads that stop at the box border, treatment and outcome
    highlighted."""
    positions, n_columns, max_rows = _layered_positions(graph)
    font_size = 9
    fig_width = max(6.0, 2.6 * n_columns)
    fig_height = max(3.5, 0.75 * max_rows + 1.0)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=150)
    ax.set_xlim(-1.6, 3.2 * max(n_columns - 1, 0) + 1.6)
    ax.set_ylim(-(max_rows - 1) / 2 * 1.25 - 0.9, (max_rows - 1) / 2 * 1.25 + 0.9)
    ax.axis("off")

    def half_extent_points(label: str) -> tuple[float, float]:
        pad = 7.0
        return 0.5 * len(label) * font_size * 0.62 + pad, 0.5 * font_size * 1.35 + pad

    def shrink_for(source: str, target: str, node: str, radius: float, at_end: bool) -> float:
        """Distance (in points) from a node's centre to its box border along the
        arrow's direction, so arrowheads end exactly at the box. For curved
        (arc3) edges the direction is the arc's tangent at that end, taken from
        matplotlib's control point: midpoint + radius * (dy, -dx)."""
        a = ax.transData.transform(positions[source])
        b = ax.transData.transform(positions[target])
        dx, dy = b[0] - a[0], b[1] - a[1]
        control = ((a[0] + b[0]) / 2 + radius * dy, (a[1] + b[1]) / 2 - radius * dx)
        if at_end:
            tx, ty = b[0] - control[0], b[1] - control[1]
        else:
            tx, ty = control[0] - a[0], control[1] - a[1]
        norm = float(np.hypot(tx, ty)) or 1.0
        cos_x, cos_y = abs(tx) / norm, abs(ty) / norm
        half_w, half_h = half_extent_points(node)
        candidates = []
        if cos_x > 1e-6:
            candidates.append(half_w / cos_x)
        if cos_y > 1e-6:
            candidates.append(half_h / cos_y)
        return min(candidates) if candidates else half_h

    column_of = {node: round(x / 3.2) for node, (x, _) in positions.items()}
    for index, (source, target) in enumerate(graph.edges()):
        # Edges that skip layers would run straight through intermediate boxes;
        # bend them, alternating above/below, in proportion to the layers skipped.
        span = column_of[target] - column_of[source]
        same_row = abs(positions[source][1] - positions[target][1]) < 1e-9
        if span > 1 and same_row:
            radius = min(0.18 * span, 0.5) * (1 if index % 2 else -1)
        else:
            radius = 0.06
        ax.annotate(
            "",
            xy=positions[target],
            xytext=positions[source],
            arrowprops=dict(
                arrowstyle="-|>",
                color="#64748b",
                lw=1.3,
                mutation_scale=16,
                shrinkA=shrink_for(source, target, source, radius, at_end=False),
                shrinkB=shrink_for(source, target, target, radius, at_end=True),
                connectionstyle=f"arc3,rad={radius}",
            ),
            zorder=1,
        )

    for node, (x, y) in positions.items():
        if node == treatment_name:
            face, edge = "#fde68a", "#b45309"
        elif node == outcome_name:
            face, edge = "#bbf7d0", "#047857"
        else:
            face, edge = "#dbeafe", "#1e3a5f"
        ax.text(
            x, y, node, ha="center", va="center", fontsize=font_size, zorder=3,
            bbox=dict(boxstyle="round,pad=0.45", facecolor=face, edgecolor=edge, linewidth=1.2),
        )

    if treatment_name or outcome_name:
        legend = []
        if treatment_name:
            legend.append(f"treatment: {treatment_name}")
        if outcome_name:
            legend.append(f"outcome: {outcome_name}")
        ax.text(0.0, 1.0, " | ".join(legend), transform=ax.transAxes, fontsize=8,
                color="#475569", ha="left", va="bottom")

    fig.savefig(image_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def generate_graph_image(
    graph_id: int,
    graph: nx.DiGraph,
    treatment_name: str | None = None,
    outcome_name: str | None = None,
) -> str:
    graph_directory = os.path.join(settings.MEDIA_ROOT, "causal_graphs")
    os.makedirs(graph_directory, exist_ok=True)

    image_name = f"causal_graph_{graph_id}.png"
    image_path = os.path.join(graph_directory, image_name)
    draw_dag_figure(graph, image_path, treatment_name, outcome_name)
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


def _safe_pair_coverage(data_frame: pd.DataFrame, source: str, target: str) -> float | None:
    if source not in data_frame.columns or target not in data_frame.columns or data_frame.empty:
        return None

    try:
        pair = data_frame[[source, target]].apply(pd.to_numeric, errors="coerce")
    except Exception:
        return None

    return float(pair.notna().all(axis=1).mean())


def _safe_partial_correlation(data_frame: pd.DataFrame, source: str, target: str) -> float | None:
    if source not in data_frame.columns or target not in data_frame.columns:
        return None

    numeric = data_frame.apply(pd.to_numeric, errors="coerce")
    covariates = [column for column in numeric.columns if column not in {source, target}][:4]
    required_columns = [source, target, *covariates]
    subset = numeric[required_columns].dropna()
    if subset.shape[0] < 5:
        return None

    if not covariates:
        return _safe_numeric_correlation(subset, source, target)

    design_matrix = subset[covariates].to_numpy(dtype=float)
    design_matrix = np.column_stack([np.ones(len(design_matrix)), design_matrix])

    def residualize(series_name: str) -> np.ndarray | None:
        try:
            vector = subset[series_name].to_numpy(dtype=float)
            coefficients, *_ = np.linalg.lstsq(design_matrix, vector, rcond=None)
            return vector - design_matrix @ coefficients
        except Exception:
            return None

    source_residual = residualize(source)
    target_residual = residualize(target)
    if source_residual is None or target_residual is None:
        return None

    if np.std(source_residual) == 0 or np.std(target_residual) == 0:
        return None

    correlation = np.corrcoef(source_residual, target_residual)[0, 1]
    if pd.isna(correlation):
        return None
    return float(abs(correlation))


def _strength_to_status(strength: float | None, strong_threshold: float, weak_threshold: float) -> str:
    if strength is None:
        return "weak"
    if strength >= strong_threshold:
        return "supported"
    if strength >= weak_threshold:
        return "weak"
    return "rejected"


def _status_weight(status: str) -> float:
    normalized = str(status).lower()
    if normalized == "supported":
        return 1.0
    if normalized == "weak":
        return 0.55
    if normalized == "conflict":
        return 0.25
    return 0.0


def _clamp_unit(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


def verify_proposed_edges(
    data_frame: pd.DataFrame,
    proposed_edges: list[dict],
    temporal_hints: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> list[dict]:
    verified_edges: list[dict] = []
    temporal_hints = temporal_hints or {}

    for item in proposed_edges:
        source = str(item.get("source", "")).strip()
        target = str(item.get("target", "")).strip()
        directed = bool(item.get("directed", True))
        reason = str(item.get("reason", "")).strip()

        if not source or not target or source == target:
            continue

        verifier_breakdown = [
            {
                "name": "llm_prior",
                "status": "supported",
                "score": 1.0,
                "weight": 0.15,
                "details": reason or "LLM-proposed edge",
            }
        ]
        evidence = [
            {
                "evidence_type": "llm",
                "status": "supported",
                "details": {"reason": reason or "LLM-proposed edge"},
            }
        ]

        support_score = _safe_numeric_correlation(data_frame, source, target)
        support_status = _strength_to_status(support_score, strong_threshold=0.2, weak_threshold=0.1)
        verifier_breakdown.append(
            {
                "name": "marginal_correlation",
                "status": "conflict" if support_status == "rejected" else support_status,
                "score": support_score,
                "weight": 0.35,
                "details": "Absolute Pearson correlation between source and target.",
            }
        )
        evidence.append(
            {
                "evidence_type": "score_search",
                "status": "rejected" if support_status == "rejected" else support_status,
                "score": support_score,
                "details": {
                    "metric": "abs_pearson_corr",
                    "note": "Pairwise association check.",
                },
            }
        )

        partial_score = _safe_partial_correlation(data_frame, source, target)
        partial_status = _strength_to_status(partial_score, strong_threshold=0.12, weak_threshold=0.05)
        verifier_breakdown.append(
            {
                "name": "partial_correlation",
                "status": "conflict" if partial_status == "rejected" else partial_status,
                "score": partial_score,
                "weight": 0.25,
                "details": "Residual correlation after controlling for up to four other variables.",
            }
        )
        evidence.append(
            {
                "evidence_type": "ci_test",
                "status": "rejected" if partial_status == "rejected" else partial_status,
                "score": partial_score,
                "details": {
                    "metric": "abs_partial_corr",
                    "note": "Approximate conditional independence screen.",
                },
            }
        )

        coverage_score = _safe_pair_coverage(data_frame, source, target)
        coverage_status = _strength_to_status(coverage_score, strong_threshold=0.8, weak_threshold=0.5)
        verifier_breakdown.append(
            {
                "name": "pair_coverage",
                "status": coverage_status,
                "score": coverage_score,
                "weight": 0.15,
                "details": "Fraction of rows where both variables are observed.",
            }
        )
        evidence.append(
            {
                "evidence_type": "score_search",
                "status": coverage_status,
                "score": coverage_score,
                "details": {
                    "metric": "pair_coverage",
                },
            }
        )

        temporal_hint = temporal_hints.get((source, target))
        if temporal_hint is not None:
            temporal_status = _strength_to_status(
                float(temporal_hint.get("strength", 0.0) or 0.0),
                strong_threshold=0.2,
                weak_threshold=0.08,
            )
            verifier_breakdown.append(
                {
                    "name": "temporal_precedence",
                    "status": temporal_status,
                    "score": temporal_hint.get("strength"),
                    "weight": 0.25,
                    "details": temporal_hint.get("details") or "Lagged precedence check.",
                }
            )
            evidence.append(
                {
                    "evidence_type": "temporal_prior",
                    "status": temporal_status,
                    "score": temporal_hint.get("strength"),
                    "details": {
                        "lag": temporal_hint.get("best_lag"),
                        "note": temporal_hint.get("details") or "Temporal precedence evidence.",
                    },
                }
            )

        total_weight = 0.0
        weighted_score = 0.0
        has_rejection = False
        for item_breakdown in verifier_breakdown:
            weight = float(item_breakdown.get("weight", 0.0) or 0.0)
            total_weight += weight
            weighted_score += weight * _status_weight(item_breakdown.get("status", "weak"))
            if item_breakdown.get("status") in {"rejected", "conflict"}:
                has_rejection = True

        confidence = _clamp_unit(weighted_score / total_weight) if total_weight else 0.0
        if confidence >= 0.72 and not has_rejection:
            verification_status = "supported"
            recommended_action = "accept"
        elif confidence >= 0.48:
            verification_status = "weak" if not has_rejection else "conflict"
            recommended_action = "review"
        else:
            verification_status = "rejected" if not has_rejection else "conflict"
            recommended_action = "reject"

        verified_edges.append(
            {
                "source": source,
                "target": target,
                "directed": directed,
                "reason": reason,
                "verification_status": verification_status,
                "verification_score": support_score,
                "confidence": confidence,
                "recommended_action": recommended_action,
                "verifier_breakdown": verifier_breakdown,
                "evidence": evidence,
            }
        )

    return verified_edges


def summarize_graph_copilot(verified_edges: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = {"supported": 0, "weak": 0, "conflict": 0, "rejected": 0}
    accept_count = 0
    review_count = 0
    mean_confidence = 0.0
    for edge in verified_edges:
        status = str(edge.get("verification_status", "weak"))
        status_counts[status] = status_counts.get(status, 0) + 1
        if edge.get("recommended_action") == "accept":
            accept_count += 1
        elif edge.get("recommended_action") == "review":
            review_count += 1
        mean_confidence += float(edge.get("confidence", 0.0) or 0.0)

    edge_count = len(verified_edges)
    mean_confidence = mean_confidence / edge_count if edge_count else 0.0
    return {
        "edge_count": edge_count,
        "accept_count": accept_count,
        "review_count": review_count,
        "status_counts": status_counts,
        "mean_confidence": round(mean_confidence, 4),
    }


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


def _extract_estimate_value(result: Any) -> float | None:
    if result is None:
        return None

    for attribute in ("new_effect", "estimated_effect", "effect_estimate", "value"):
        value = getattr(result, attribute, None)
        if value is None:
            continue
        try:
            return float(value)
        except Exception:
            continue

    return None


def _format_refutation_result(result: Any, baseline_value: float | None = None) -> dict[str, Any]:
    # Some refuters (e.g. dummy_outcome) return a list of refutation objects;
    # unwrap it so the summary is readable text instead of a Python list repr.
    if isinstance(result, (list, tuple)):
        result = result[0] if result else None

    if result is None:
        return {"status": "unavailable", "summary": "No refutation output."}

    p_value = getattr(result, "p_value", None)
    if p_value is not None:
        try:
            p_value = float(p_value)
        except Exception:
            p_value = None

    estimated_effect = _extract_estimate_value(result)
    delta = None
    if estimated_effect is not None and baseline_value is not None:
        delta = float(abs(estimated_effect - baseline_value))

    return {
        "status": "ok",
        "summary": str(result),
        "p_value": p_value,
        "estimated_effect": estimated_effect,
        "delta": delta,
    }


@suppress_numeric_estimation_warnings
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


@suppress_numeric_estimation_warnings
def run_refutations_and_sensitivity(
    model: Any,
    identified_estimand: Any,
    baseline_estimate: Any,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    baseline_value = _extract_estimate_value(baseline_estimate)
    refutations: dict[str, dict[str, Any]] = {}
    refuter_map = {
        "placebo_treatment": ("placebo_treatment_refuter", {}),
        "dummy_outcome": ("dummy_outcome_refuter", {}),
        "random_common_cause": ("random_common_cause", {}),
        "data_subsample": (
            "data_subset_refuter",
            {
                "subset_fraction": 0.8,
                "num_simulations": 5,
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
            refutations[key] = _format_refutation_result(output, baseline_value)
        except Exception as exc:
            refutations[key] = {
                "status": "error",
                "summary": str(exc),
                "p_value": None,
                "estimated_effect": None,
                "delta": None,
            }

    # Partial-R2 (Cinelli-Hazlett) sensitivity needs an observed covariate to
    # benchmark the hypothetical unobserved confounder against; without one the
    # DoWhy call crashes on unset strength parameters. Use the strongest
    # available backdoor variable, and back off to weaker assumed fractions when
    # the benchmark implies an impossible partial R2 (>= 1).
    sensitivity: dict[str, dict[str, Any]] = {}
    try:
        backdoor_variables = list(identified_estimand.get_backdoor_variables() or [])
    except Exception:
        backdoor_variables = []

    if not backdoor_variables:
        sensitivity["partial_r2"] = {
            "status": "unavailable",
            "summary": (
                "Partial-R2 sensitivity needs at least one observed adjustment variable "
                "to benchmark against; this graph has none."
            ),
            "p_value": None,
            "estimated_effect": None,
            "delta": None,
        }
        return refutations, sensitivity

    last_error: Exception | None = None
    for fractions in ([0.1, 0.2, 0.3], [0.02, 0.05, 0.1], [0.002, 0.005, 0.01]):
        try:
            output = model.refute_estimate(
                identified_estimand,
                baseline_estimate,
                method_name="add_unobserved_common_cause",
                simulation_method="linear-partial-R2",
                benchmark_common_causes=backdoor_variables[:1],
                effect_fraction_on_treatment=fractions,
            )
            sensitivity["partial_r2"] = _format_refutation_result(output, baseline_value)
            last_error = None
            break
        except Exception as exc:
            last_error = exc

    if last_error is not None:
        sensitivity["partial_r2"] = {
            "status": "error",
            "summary": str(last_error),
            "p_value": None,
            "estimated_effect": None,
            "delta": None,
        }

    return refutations, sensitivity


@suppress_numeric_estimation_warnings
def compute_confounder_sensitivity_sweep(
    data_frame: pd.DataFrame,
    treatment_name: str,
    outcome_name: str,
    adjustment_set: list[str],
    baseline_estimate: float | None,
    strengths: tuple[float, ...] = (0.1, 0.2, 0.3, 0.4, 0.5),
) -> dict[str, Any]:
    """Omitted-variable-bias sensitivity sweep (Cinelli & Hazlett, 2020).

    For a hypothetical unobserved confounder that explains a share ``s`` of the
    residual variance of BOTH the treatment and the outcome (equal partial R2),
    the maximal bias of the adjusted estimate is

        |bias| = se(tau) * s * sqrt(df / (1 - s))

    which needs only the standard error and residual degrees of freedom of the
    adjusted regression of the outcome on the treatment and adjustment set.
    The robustness value ``rv`` is the confounder strength at which the bias
    equals the estimate itself (would bring it to zero). Unlike a fixed formula,
    this is a genuine analysis: it is scale-free and reproduces DoWhy's
    linear-partial-R2 robustness value when that runs.
    """
    result: dict[str, Any] = {"points": [], "robustness_value": None, "t_value": None, "note": ""}
    if baseline_estimate is None:
        result["note"] = "No baseline estimate; sensitivity sweep not computed."
        return result

    try:
        import statsmodels.api as sm

        columns = [treatment_name] + [name for name in adjustment_set if name in data_frame.columns]
        frame = data_frame[columns + [outcome_name]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(frame.index) <= len(columns) + 2:
            result["note"] = "Too few complete rows to fit the adjusted regression."
            return result
        design = sm.add_constant(frame[columns])
        fit = sm.OLS(frame[outcome_name], design).fit()
        standard_error = float(fit.bse[treatment_name])
        degrees_of_freedom = float(fit.df_resid)
        t_value = float(fit.tvalues[treatment_name])
    except Exception as exc:
        result["note"] = f"Sensitivity sweep unavailable: {exc}"
        return result

    if not np.isfinite(standard_error) or standard_error <= 0 or degrees_of_freedom <= 0:
        result["note"] = "Degenerate regression (zero standard error); sweep not computed."
        return result

    sign = 1.0 if baseline_estimate >= 0 else -1.0
    for strength in strengths:
        bias = standard_error * strength * float(np.sqrt(degrees_of_freedom / (1.0 - strength)))
        result["points"].append(
            {
                "confounder_strength": float(strength),
                "adjusted_effect": float(baseline_estimate - sign * bias),
                "bias": float(bias),
            }
        )

    f_squared = (t_value ** 2) / degrees_of_freedom
    result["robustness_value"] = float(0.5 * (np.sqrt(f_squared ** 2 + 4.0 * f_squared) - f_squared))
    result["t_value"] = t_value
    result["note"] = (
        "Bias bound for an unobserved confounder explaining the given share of residual "
        "variance of both treatment and outcome (Cinelli & Hazlett 2020)."
    )
    return result


def summarize_robustness(
    estimator_comparison: list[dict[str, Any]],
    refutations: dict[str, dict[str, Any]],
    sensitivity: dict[str, dict[str, Any]],
    baseline_estimate: float | None,
    sensitivity_points: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float]:
    valid_estimates = [
        float(item["estimated_effect"])
        for item in estimator_comparison
        if item.get("estimated_effect") is not None and not item.get("error")
    ]

    diagnostics: list[dict[str, Any]] = []
    estimator_spread = None
    if len(valid_estimates) >= 2:
        estimator_spread = float(max(valid_estimates) - min(valid_estimates))
        diagnostics.append(
            {
                "label": "Estimator spread",
                "value": round(estimator_spread, 4),
                "status": "good" if estimator_spread <= 0.2 else "watch",
                "details": "Difference between the largest and smallest successful estimator outputs.",
            }
        )

    successful_refuters = sum(1 for item in refutations.values() if item.get("status") == "ok")
    successful_sensitivity = sum(1 for item in sensitivity.values() if item.get("status") == "ok")
    diagnostics.append(
        {
            "label": "Refuter coverage",
            "value": successful_refuters,
            "status": "good" if successful_refuters >= 2 else "watch",
            "details": "Number of refuters that completed successfully.",
        }
    )
    diagnostics.append(
        {
            "label": "Sensitivity coverage",
            "value": successful_sensitivity,
            "status": "good" if successful_sensitivity >= 1 else "watch",
            "details": "Number of sensitivity analyses that completed successfully.",
        }
    )

    # The sweep is computed by compute_confounder_sensitivity_sweep from the
    # adjusted regression; it is never synthesized from a fixed formula here.
    sensitivity_points = list(sensitivity_points or [])

    score_parts = []
    if estimator_spread is not None:
        score_parts.append(_clamp_unit(1.0 - estimator_spread / max(abs(baseline_estimate or 1.0), 1.0)))
    if refutations:
        score_parts.append(successful_refuters / max(len(refutations), 1))
    if sensitivity:
        score_parts.append(successful_sensitivity / max(len(sensitivity), 1))
    robustness_score = round(sum(score_parts) / len(score_parts), 4) if score_parts else 0.0

    return diagnostics, sensitivity_points, robustness_score


def build_admissibility_summary(
    directed_graph: nx.DiGraph,
    identified_estimand: Any,
    treatment_name: str,
    outcome_name: str,
    data_frame: pd.DataFrame,
) -> dict[str, Any]:
    graph_issues: list[str] = []
    open_backdoor_paths: list[str] = []
    blocked_paths: list[str] = []

    dag_valid = nx.is_directed_acyclic_graph(directed_graph)
    if not dag_valid:
        graph_issues.append("Graph contains a directed cycle.")

    try:
        all_paths = list(nx.all_simple_paths(directed_graph.to_undirected(), treatment_name, outcome_name, cutoff=4))
    except Exception:
        all_paths = []

    adjustment_set = list((identified_estimand.get_backdoor_variables() or []))
    for path in all_paths[:8]:
        formatted_path = " -> ".join(path)
        internal_nodes = set(path[1:-1])
        if internal_nodes & set(adjustment_set):
            blocked_paths.append(formatted_path)
        else:
            open_backdoor_paths.append(formatted_path)

    treatment_series = pd.to_numeric(data_frame[treatment_name], errors="coerce")
    outcome_series = pd.to_numeric(data_frame[outcome_name], errors="coerce")
    treatment_variation = float(treatment_series.std()) if treatment_series.notna().any() else None
    outcome_variation = float(outcome_series.std()) if outcome_series.notna().any() else None

    minimal_adjustment_sets = [adjustment_set] if adjustment_set else []
    checklist = [
        {
            "label": "Graph is a DAG",
            "status": "pass" if dag_valid else "fail",
            "details": "Identification assumes an acyclic causal graph.",
        },
        {
            "label": "Treatment variation",
            "status": "pass" if (treatment_variation or 0.0) > 0 else "fail",
            "details": "Treatment must vary to support estimation.",
        },
        {
            "label": "Outcome variation",
            "status": "pass" if (outcome_variation or 0.0) > 0 else "warn",
            "details": "Low outcome variation weakens the analysis.",
        },
        {
            "label": "Backdoor path review",
            "status": "pass" if not open_backdoor_paths else "warn",
            "details": "Open undirected paths may indicate unresolved confounding.",
        },
    ]

    return {
        "dag_valid": dag_valid,
        "graph_issues": graph_issues,
        "open_backdoor_paths": open_backdoor_paths,
        "blocked_paths": blocked_paths,
        "sample_size": int(len(data_frame.index)),
        "treatment_variation": treatment_variation,
        "outcome_variation": outcome_variation,
        "minimal_adjustment_sets": minimal_adjustment_sets,
        "admissibility_checklist": checklist,
    }


def analyze_time_series_graph(
    raw_data_frame: pd.DataFrame,
    edges: list[tuple[str, str]],
    time_column: str,
    entity_column: str = "",
    window_count: int = 4,
    max_lag: int = 3,
) -> dict[str, Any]:
    if time_column not in raw_data_frame.columns:
        raise ValueError(f"Time column '{time_column}' was not found in the dataset.")

    working = raw_data_frame.copy()
    parsed_time = pd.to_datetime(working[time_column], errors="coerce", utc=True)
    if float(parsed_time.notna().mean()) < 0.8:
        raise ValueError("Time-series mode requires a parsable timestamp column for most rows.")

    entity_series = None
    if entity_column:
        if entity_column not in working.columns:
            raise ValueError(f"Entity column '{entity_column}' was not found in the dataset.")
        entity_series = working[entity_column].astype("string").fillna("unknown")
    else:
        entity_series = pd.Series(["global"] * len(working), index=working.index, dtype="string")

    numeric = preprocess_data_frame_for_causal(working)
    numeric["__time__"] = parsed_time
    numeric["__entity__"] = entity_series
    numeric = numeric.sort_values(["__entity__", "__time__"]).reset_index(drop=True)

    # Require enough rows for rolling windows without rejecting compact datasets.
    if len(numeric.index) < max(window_count * 2, 6):
        raise ValueError("Time-series mode requires more rows to compute stable rolling windows.")

    window_edges: list[dict[str, Any]] = []
    chunk_size = max(2, len(numeric.index) // window_count)
    for index in range(window_count):
        start_index = index * chunk_size
        end_index = len(numeric.index) if index == window_count - 1 else min(len(numeric.index), (index + 1) * chunk_size)
        chunk = numeric.iloc[start_index:end_index].copy()
        if chunk.empty:
            continue
        window_edges.append(
            {
                "label": f"Window {index + 1}",
                "start": chunk["__time__"].iloc[0].isoformat(),
                "end": chunk["__time__"].iloc[-1].isoformat(),
                "frame": chunk,
            }
        )

    edge_stability: list[dict[str, Any]] = []
    dynamic_graphs: list[dict[str, Any]] = []
    temporal_hints: dict[tuple[str, str], dict[str, Any]] = {}

    for window in window_edges:
        dynamic_graphs.append(
            {
                "label": window["label"],
                "start": window["start"],
                "end": window["end"],
                "edges": [],
            }
        )

    for source, target in edges:
        if source not in numeric.columns or target not in numeric.columns:
            continue

        lag_strengths: list[float] = []
        lag_choices: list[int | None] = []
        lag_signs: list[float] = []

        for window_index, window in enumerate(window_edges):
            frame = window["frame"]
            best_strength = 0.0
            best_lag = None
            best_sign = 0.0

            for lag in range(1, max_lag + 1):
                correlations: list[float] = []
                for _entity, entity_frame in frame.groupby("__entity__"):
                    aligned = pd.DataFrame(
                        {
                            "source": pd.to_numeric(entity_frame[source], errors="coerce").shift(lag),
                            "target": pd.to_numeric(entity_frame[target], errors="coerce"),
                        }
                    ).dropna()
                    if len(aligned.index) < 3:
                        continue
                    corr = aligned["source"].corr(aligned["target"])
                    if corr is None or pd.isna(corr):
                        continue
                    correlations.append(float(corr))

                if not correlations:
                    continue

                mean_corr = float(np.mean(correlations))
                strength = float(abs(mean_corr))
                if strength > best_strength:
                    best_strength = strength
                    best_lag = lag
                    best_sign = 1.0 if mean_corr >= 0 else -1.0

            lag_strengths.append(best_strength)
            lag_choices.append(best_lag)
            lag_signs.append(best_sign)
            dynamic_graphs[window_index]["edges"].append(
                {
                    "source": source,
                    "target": target,
                    "strength": round(best_strength, 4),
                    "best_lag": best_lag,
                    "status": "supported" if best_strength >= 0.2 else "weak" if best_strength >= 0.08 else "rejected",
                }
            )

        mean_strength = float(np.mean(lag_strengths)) if lag_strengths else 0.0
        std_strength = float(np.std(lag_strengths)) if lag_strengths else 0.0
        stability = _clamp_unit(1.0 - (std_strength / (mean_strength + 1e-6))) if lag_strengths else 0.0
        valid_lags = [lag for lag in lag_choices if lag is not None]
        best_lag = int(round(float(np.mean(valid_lags)))) if valid_lags else None
        non_zero_signs = [sign for sign in lag_signs if sign != 0.0]
        direction_consistency = (
            float(abs(np.mean(non_zero_signs))) if non_zero_signs else 0.0
        )
        status = "supported" if mean_strength >= 0.2 and stability >= 0.45 else "weak" if mean_strength >= 0.08 else "rejected"

        edge_stability.append(
            {
                "source": source,
                "target": target,
                "best_lag": best_lag,
                "mean_strength": round(mean_strength, 4),
                "stability": round(stability, 4),
                "direction_consistency": round(direction_consistency, 4),
                "window_strengths": [round(value, 4) for value in lag_strengths],
                "status": status,
            }
        )
        temporal_hints[(source, target)] = {
            "strength": round(mean_strength, 4),
            "best_lag": best_lag,
            "details": f"Average lagged association across {len(lag_strengths)} rolling windows.",
        }

    diagnostics = [
        {
            "label": "Rows analysed",
            "value": int(len(numeric.index)),
            "status": "good",
            "details": "Rows retained after timestamp parsing and ordering.",
        },
        {
            "label": "Entities",
            "value": int(numeric["__entity__"].nunique()),
            "status": "good",
            "details": "Distinct entity streams used in the lag analysis.",
        },
        {
            "label": "Time coverage",
            "value": f"{parsed_time.min().isoformat()} to {parsed_time.max().isoformat()}",
            "status": "good",
            "details": "Observed timestamp range across the dataset.",
        },
    ]

    return {
        "mode": "time-series",
        "time_column": time_column,
        "entity_column": entity_column,
        "window_count": window_count,
        "max_lag": max_lag,
        "edge_stability": edge_stability,
        "dynamic_graphs": dynamic_graphs,
        "diagnostics": diagnostics,
        "temporal_hints": temporal_hints,
    }


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
                "details": "Anomaly mean shift x |corr(var, outcome)|",
            }
        )
        dist_change_scores.append(
            {
                "variable": column,
                "score": dist_shift * corr,
                "details": "Temporal distribution shift x |corr(var, outcome)|",
            }
        )

    anomaly_scores.sort(key=lambda item: item["score"], reverse=True)
    dist_change_scores.sort(key=lambda item: item["score"], reverse=True)

    return {
        "anomaly_attribution": anomaly_scores[:top_k],
        "distribution_change_attribution": dist_change_scores[:top_k],
    }
