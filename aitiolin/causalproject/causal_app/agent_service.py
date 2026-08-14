"""Causality Agent: data profiling, cleaning-plan suggestion/execution, and
causal model suggestion.

The agent is a staged pipeline with user approval between stages:
profile -> cleaning plan -> causal model suggestion. LLM assistance is used
only for the model-suggestion stage and degrades to deterministic heuristics
when no API key is configured.
"""

import logging
import re
from typing import Any

import networkx as nx
import pandas as pd

from .services import (
    build_dot_graph,
    derive_graph_hypotheses,
    get_causal_model_class,
    preprocess_data_frame_for_causal,
    summarize_graph_copilot,
    suppress_numeric_estimation_warnings,
    verify_proposed_edges,
)

logger = logging.getLogger("causal")

ID_NAME_PATTERN = re.compile(r"(^id$|_id$|^id_|id$|uuid|guid|^key$|_key$)", re.IGNORECASE)
OUTCOME_NAME_PATTERN = re.compile(
    r"(churn|outcome|target|label|result|converted|default|response|^y$)", re.IGNORECASE
)
TREATMENT_NAME_PATTERN = re.compile(
    r"(treatment|treated|intervention|campaign|promo|discount|contract|plan|exposure)",
    re.IGNORECASE,
)

TRUE_TOKENS = {"true", "t", "yes", "y", "1", "on"}
FALSE_TOKENS = {"false", "f", "no", "n", "0", "off"}
BOOLEAN_TOKENS = TRUE_TOKENS | FALSE_TOKENS

MISSING_TEXT_TOKENS = {"", "nan", "none", "null", "na", "n/a"}


def _normalized_text_series(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip()
    lowered = text.str.lower()
    return text.mask(lowered.isin(MISSING_TEXT_TOKENS))


def _infer_column_type(series: pd.Series) -> tuple[str, dict[str, float]]:
    """Return (inferred_type, extra ratios) for a raw column."""
    extras: dict[str, float] = {}

    if pd.api.types.is_bool_dtype(series):
        return "boolean", extras

    if pd.api.types.is_numeric_dtype(series):
        return "numeric", extras

    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime", extras

    text = _normalized_text_series(series)
    non_missing = text.dropna()
    if non_missing.empty:
        return "empty", extras

    lowered = non_missing.str.lower()
    if lowered.isin(BOOLEAN_TOKENS).all():
        return "boolean", extras

    numeric_ratio = float(pd.to_numeric(non_missing, errors="coerce").notna().mean())
    extras["numeric_like_ratio"] = round(numeric_ratio, 4)
    if numeric_ratio >= 0.999:
        return "numeric", extras

    datetime_ratio = float(
        pd.to_datetime(non_missing, errors="coerce", utc=True, format="mixed").notna().mean()
    )
    extras["datetime_like_ratio"] = round(datetime_ratio, 4)
    if datetime_ratio >= 0.8:
        return "datetime", extras

    if numeric_ratio >= 0.5:
        return "mixed", extras

    unique_ratio = float(non_missing.nunique() / len(non_missing)) if len(non_missing) else 0.0
    if unique_ratio > 0.5 and non_missing.str.len().mean() > 20:
        return "text", extras

    return "categorical", extras


def profile_data_frame(data_frame: pd.DataFrame) -> dict[str, Any]:
    row_count = int(len(data_frame.index))
    duplicate_row_count = int(data_frame.duplicated().sum()) if row_count else 0

    columns: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []

    for column in data_frame.columns:
        series = data_frame[column]
        inferred_type, extras = _infer_column_type(series)

        if inferred_type in {"numeric", "boolean", "datetime"} and not pd.api.types.is_object_dtype(series):
            missing_mask = series.isna()
        else:
            missing_mask = _normalized_text_series(series).isna()

        missing_count = int(missing_mask.sum())
        missing_ratio = round(missing_count / row_count, 4) if row_count else 0.0
        non_missing = series[~missing_mask]
        unique_count = int(non_missing.nunique())
        unique_ratio = round(unique_count / len(non_missing), 4) if len(non_missing) else 0.0

        column_profile: dict[str, Any] = {
            "name": str(column),
            "inferred_type": inferred_type,
            "missing_count": missing_count,
            "missing_ratio": missing_ratio,
            "unique_count": unique_count,
            "unique_ratio": unique_ratio,
        }
        column_profile.update(extras)

        outlier_count = 0
        if inferred_type == "numeric":
            numeric = pd.to_numeric(non_missing, errors="coerce").dropna()
            if not numeric.empty:
                column_profile["min"] = float(numeric.min())
                column_profile["max"] = float(numeric.max())
                column_profile["mean"] = round(float(numeric.mean()), 6)
                column_profile["std"] = round(float(numeric.std()), 6) if len(numeric) > 1 else 0.0
                q1 = float(numeric.quantile(0.25))
                q3 = float(numeric.quantile(0.75))
                iqr = q3 - q1
                if iqr > 0:
                    lower = q1 - 3.0 * iqr
                    upper = q3 + 3.0 * iqr
                    outlier_count = int(((numeric < lower) | (numeric > upper)).sum())
                column_profile["outlier_count"] = outlier_count
        elif inferred_type in {"categorical", "boolean"}:
            top_values = non_missing.astype("string").value_counts().head(5)
            column_profile["top_values"] = [
                {"value": str(value), "count": int(count)} for value, count in top_values.items()
            ]

        columns.append(column_profile)

        is_id_like = unique_ratio >= 0.95 and row_count >= 10 and (
            bool(ID_NAME_PATTERN.search(str(column))) or inferred_type in {"categorical", "text", "mixed"}
        )
        if is_id_like:
            issues.append(
                {
                    "issue_type": "id_like_column",
                    "column": str(column),
                    "severity": "warning",
                    "description": (
                        f"'{column}' looks like an identifier ({unique_count} unique values in "
                        f"{row_count} rows). Identifiers carry no causal signal and should be dropped."
                    ),
                }
            )
        elif unique_count <= 1:
            issues.append(
                {
                    "issue_type": "constant_column",
                    "column": str(column),
                    "severity": "warning",
                    "description": f"'{column}' is constant (or empty) and cannot carry causal signal.",
                }
            )

        if missing_ratio >= 0.4:
            issues.append(
                {
                    "issue_type": "high_missing",
                    "column": str(column),
                    "severity": "warning",
                    "description": f"'{column}' is missing in {missing_ratio:.0%} of rows.",
                }
            )
        elif missing_count > 0:
            issues.append(
                {
                    "issue_type": "some_missing",
                    "column": str(column),
                    "severity": "info",
                    "description": f"'{column}' has {missing_count} missing value(s) ({missing_ratio:.1%}).",
                }
            )

        if inferred_type == "mixed":
            numeric_ratio = extras.get("numeric_like_ratio", 0.0)
            issues.append(
                {
                    "issue_type": "mixed_numeric_text",
                    "column": str(column),
                    "severity": "warning",
                    "description": (
                        f"'{column}' is mostly numeric ({numeric_ratio:.0%}) but stored as text; "
                        "non-numeric entries will become missing after coercion."
                    ),
                }
            )

        if inferred_type == "datetime":
            issues.append(
                {
                    "issue_type": "datetime_column",
                    "column": str(column),
                    "severity": "info",
                    "description": f"'{column}' looks like a datetime column - a candidate for time-series mode.",
                }
            )

        if inferred_type == "categorical" and unique_count > 50 and not is_id_like:
            issues.append(
                {
                    "issue_type": "high_cardinality_categorical",
                    "column": str(column),
                    "severity": "info",
                    "description": f"'{column}' has {unique_count} categories; encoding may add noise.",
                }
            )

        if row_count and outlier_count / row_count > 0.01:
            issues.append(
                {
                    "issue_type": "outlier_heavy",
                    "column": str(column),
                    "severity": "info",
                    "description": (
                        f"'{column}' has {outlier_count} extreme values (beyond 3x IQR); "
                        "consider capping before estimation."
                    ),
                }
            )

    if duplicate_row_count:
        issues.append(
            {
                "issue_type": "duplicate_rows",
                "column": None,
                "severity": "info",
                "description": f"Dataset contains {duplicate_row_count} fully duplicated row(s).",
            }
        )

    numeric_names = [item["name"] for item in columns if item["inferred_type"] == "numeric"]
    if 2 <= len(numeric_names) <= 40 and row_count >= 10:
        try:
            numeric_frame = data_frame[numeric_names].apply(pd.to_numeric, errors="coerce")
            corr = numeric_frame.corr().abs()
            for i, left in enumerate(numeric_names):
                for right in numeric_names[i + 1:]:
                    value = corr.at[left, right]
                    if pd.notna(value) and float(value) >= 0.98:
                        issues.append(
                            {
                                "issue_type": "collinear_pair",
                                "column": f"{left} ~ {right}",
                                "severity": "warning",
                                "description": (
                                    f"'{left}' and '{right}' are almost perfectly correlated "
                                    f"(|r| = {float(value):.3f}); keep only one to avoid unstable estimates."
                                ),
                            }
                        )
        except Exception:
            logger.debug("Collinearity scan failed", exc_info=True)

    return {
        "row_count": row_count,
        "column_count": int(len(data_frame.columns)),
        "duplicate_row_count": duplicate_row_count,
        "columns": columns,
        "issues": issues,
    }


def suggest_cleaning_plan(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Translate profile issues into an ordered, reviewable list of cleaning steps."""
    steps: list[dict[str, Any]] = []
    columns_by_name = {item["name"]: item for item in profile.get("columns", [])}
    dropped: set[str] = set()

    def add_step(step_type: str, column: str | None, params: dict, rationale: str,
                 severity: str, default_action: str) -> None:
        step_id = f"{step_type}:{column or '__dataset__'}"
        if any(step["step_id"] == step_id for step in steps):
            return
        steps.append(
            {
                "step_id": step_id,
                "step_type": step_type,
                "column": column,
                "params": params,
                "rationale": rationale,
                "severity": severity,
                "default_action": default_action,
            }
        )

    for issue in profile.get("issues", []):
        issue_type = issue.get("issue_type")
        column = issue.get("column")

        if issue_type in {"id_like_column", "constant_column"}:
            add_step(
                "drop_column", column, {},
                issue.get("description", ""), "warning", "accept",
            )
            dropped.add(column)
        elif issue_type == "high_missing":
            column_profile = columns_by_name.get(column, {})
            ratio = float(column_profile.get("missing_ratio", 0.0))
            if ratio >= 0.6:
                add_step(
                    "drop_column", column, {},
                    issue.get("description", "") + " Too sparse to impute reliably.",
                    "warning", "review",
                )
                dropped.add(column)
        elif issue_type == "mixed_numeric_text":
            add_step(
                "coerce_numeric", column, {"errors": "coerce"},
                issue.get("description", ""), "warning", "accept",
            )
        elif issue_type == "collinear_pair":
            pair = [part.strip() for part in str(column or "").split("~")]
            if len(pair) == 2 and pair[1] and pair[1] not in dropped:
                add_step(
                    "drop_column", pair[1], {},
                    issue.get("description", "")
                    + " Redundant covariates make regression estimates unstable "
                    "(singular design matrix).",
                    "warning", "review",
                )
        elif issue_type == "duplicate_rows":
            add_step(
                "drop_duplicate_rows", None, {},
                issue.get("description", ""), "info", "review",
            )
        elif issue_type == "outlier_heavy":
            add_step(
                "cap_outliers", column, {"method": "iqr", "factor": 3.0},
                issue.get("description", ""), "info", "review",
            )
        elif issue_type == "datetime_column":
            add_step(
                "normalize_datetime", column, {"format": "iso"},
                f"Normalize '{column}' to ISO timestamps so both causal and time-series analyses parse it.",
                "info", "review",
            )

    # Imputation steps for whatever survives the drops.
    for column_profile in profile.get("columns", []):
        name = column_profile["name"]
        if name in dropped or not column_profile.get("missing_count"):
            continue
        inferred = column_profile.get("inferred_type")
        if inferred in {"numeric", "boolean", "mixed", "datetime"}:
            add_step(
                "impute_missing", name, {"strategy": "median"},
                f"Fill {column_profile['missing_count']} missing value(s) in '{name}' with the median.",
                "info", "accept",
            )
        else:
            add_step(
                "impute_missing", name, {"strategy": "mode"},
                f"Fill {column_profile['missing_count']} missing value(s) in '{name}' with the most frequent value.",
                "info", "review",
            )

    return steps


def apply_cleaning_plan(
    data_frame: pd.DataFrame, steps: list[dict[str, Any]]
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Execute accepted cleaning steps and report what each one changed."""
    cleaned = data_frame.copy()
    applied: list[dict[str, Any]] = []

    order = {
        "drop_column": 0,
        "drop_duplicate_rows": 1,
        "coerce_numeric": 2,
        "normalize_datetime": 3,
        "cap_outliers": 4,
        "impute_missing": 5,
    }
    known_steps = [step for step in steps if step.get("step_type") in order]
    known_steps.sort(key=lambda step: order[step["step_type"]])

    for step in known_steps:
        step_type = step["step_type"]
        column = step.get("column")
        params = step.get("params") or {}
        detail = ""

        try:
            if step_type == "drop_column":
                if column in cleaned.columns:
                    cleaned = cleaned.drop(columns=[column])
                    detail = f"Dropped column '{column}'."
                else:
                    detail = f"Column '{column}' was already absent."
            elif step_type == "drop_duplicate_rows":
                before = len(cleaned.index)
                cleaned = cleaned.drop_duplicates().reset_index(drop=True)
                detail = f"Removed {before - len(cleaned.index)} duplicate row(s)."
            elif step_type == "coerce_numeric":
                if column not in cleaned.columns:
                    detail = f"Column '{column}' not found; skipped."
                else:
                    text = _normalized_text_series(cleaned[column])
                    numeric = pd.to_numeric(text.str.replace(",", "", regex=False), errors="coerce")
                    new_missing = int(numeric.isna().sum() - text.isna().sum())
                    cleaned[column] = numeric.astype("float")
                    detail = (
                        f"Coerced '{column}' to numeric; {max(new_missing, 0)} "
                        "non-numeric value(s) became missing."
                    )
            elif step_type == "normalize_datetime":
                if column not in cleaned.columns:
                    detail = f"Column '{column}' not found; skipped."
                else:
                    parsed = pd.to_datetime(cleaned[column], errors="coerce", utc=True, format="mixed")
                    cleaned[column] = parsed.dt.strftime("%Y-%m-%dT%H:%M:%S")
                    detail = f"Normalized '{column}' to ISO-8601 timestamps."
            elif step_type == "cap_outliers":
                if column not in cleaned.columns:
                    detail = f"Column '{column}' not found; skipped."
                else:
                    numeric = pd.to_numeric(cleaned[column], errors="coerce")
                    q1 = float(numeric.quantile(0.25))
                    q3 = float(numeric.quantile(0.75))
                    iqr = q3 - q1
                    factor = float(params.get("factor", 3.0))
                    if iqr > 0:
                        lower = q1 - factor * iqr
                        upper = q3 + factor * iqr
                        capped_count = int(((numeric < lower) | (numeric > upper)).sum())
                        cleaned[column] = numeric.clip(lower=lower, upper=upper)
                        detail = f"Capped {capped_count} value(s) in '{column}' to [{lower:.4g}, {upper:.4g}]."
                    else:
                        detail = f"'{column}' has zero IQR; nothing capped."
            elif step_type == "impute_missing":
                if column not in cleaned.columns:
                    detail = f"Column '{column}' not found; skipped."
                else:
                    series = cleaned[column]
                    strategy = str(params.get("strategy", "median"))
                    if strategy == "median" or pd.api.types.is_numeric_dtype(series):
                        numeric = pd.to_numeric(series, errors="coerce")
                        if numeric.notna().any():
                            fill_value = float(numeric.median())
                            filled = int(numeric.isna().sum())
                            cleaned[column] = numeric.fillna(fill_value)
                            detail = f"Imputed {filled} value(s) in '{column}' with median {fill_value:.4g}."
                        else:
                            detail = f"'{column}' has no numeric values; skipped."
                    else:
                        text = _normalized_text_series(series)
                        if text.notna().any():
                            fill_value = text.mode().iloc[0]
                            filled = int(text.isna().sum())
                            cleaned[column] = text.fillna(fill_value)
                            detail = f"Imputed {filled} value(s) in '{column}' with mode '{fill_value}'."
                        else:
                            detail = f"'{column}' is entirely missing; skipped."
        except Exception as exc:
            logger.exception("Cleaning step failed: %s", step.get("step_id"))
            detail = f"Step failed and was skipped: {exc}"

        applied.append(
            {
                "step_id": step.get("step_id", f"{step_type}:{column or '__dataset__'}"),
                "step_type": step_type,
                "column": column,
                "detail": detail,
            }
        )

    return cleaned, applied


def build_profile_summary_for_prompt(profile: dict[str, Any]) -> str:
    lines = [
        f"Rows: {profile.get('row_count')}, columns: {profile.get('column_count')}.",
        "Columns:",
    ]
    for item in profile.get("columns", []):
        parts = [f"- {item['name']}: {item['inferred_type']}"]
        if item.get("missing_ratio"):
            parts.append(f"{item['missing_ratio']:.0%} missing")
        if item.get("inferred_type") == "numeric" and "min" in item:
            parts.append(f"range [{item['min']:.4g}, {item['max']:.4g}]")
        if item.get("unique_count") is not None:
            parts.append(f"{item['unique_count']} unique")
        lines.append(", ".join(parts))

    warnings = [issue["description"] for issue in profile.get("issues", []) if issue.get("severity") == "warning"]
    if warnings:
        lines.append("Data quality warnings:")
        lines.extend(f"- {text}" for text in warnings[:10])
    return "\n".join(lines)


def _is_binary_column(series: pd.Series) -> bool:
    values = pd.to_numeric(series, errors="coerce").dropna().unique()
    return len(values) == 2


def heuristic_role_candidates(
    data_frame: pd.DataFrame, profile: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Deterministic treatment/outcome candidates from names and distributions."""
    columns = profile.get("columns", [])
    excluded = {
        item["name"]
        for item in columns
        if item["inferred_type"] in {"empty", "text", "datetime"} or item.get("unique_count", 0) <= 1
    }
    id_like = {
        issue["column"]
        for issue in profile.get("issues", [])
        if issue.get("issue_type") == "id_like_column"
    }
    excluded |= id_like

    outcome_candidates: list[dict[str, Any]] = []
    treatment_candidates: list[dict[str, Any]] = []

    for item in columns:
        name = item["name"]
        if name in excluded or name not in data_frame.columns:
            continue

        name_hits_outcome = bool(OUTCOME_NAME_PATTERN.search(name))
        name_hits_treatment = bool(TREATMENT_NAME_PATTERN.search(name))
        binary = item["inferred_type"] == "boolean" or item.get("unique_count") == 2

        if name_hits_outcome:
            outcome_candidates.append(
                {"name": name, "reason": "Column name suggests it is the outcome of interest."}
            )
        if name_hits_treatment and binary:
            treatment_candidates.append(
                {"name": name, "reason": "Binary column whose name suggests an intervention."}
            )
        elif binary and not name_hits_outcome:
            treatment_candidates.append(
                {"name": name, "reason": "Binary column - usable as a treatment indicator."}
            )

    if not outcome_candidates:
        for item in reversed(columns):
            name = item["name"]
            if name in excluded:
                continue
            outcome_candidates.append(
                {"name": name, "reason": "Fallback: last informative column in the dataset."}
            )
            break

    outcome_names = {item["name"] for item in outcome_candidates}
    treatment_candidates = [item for item in treatment_candidates if item["name"] not in outcome_names]
    return treatment_candidates[:5], outcome_candidates[:3]


def heuristic_edge_proposals(
    data_frame: pd.DataFrame,
    profile: dict[str, Any],
    outcome_candidates: list[dict[str, Any]],
    max_edges: int,
) -> list[dict[str, Any]]:
    """LLM-free fallback: propose edges from strongest pairwise associations."""
    excluded = {
        issue["column"]
        for issue in profile.get("issues", [])
        if issue.get("issue_type") in {"id_like_column", "constant_column"}
    }
    usable = [name for name in data_frame.columns if name not in excluded]
    if len(usable) < 2:
        return []

    processed = preprocess_data_frame_for_causal(data_frame[usable])
    corr = processed.corr().abs()
    outcome_names = {item["name"] for item in outcome_candidates}
    column_order = {name: index for index, name in enumerate(usable)}

    scored_pairs = []
    for i, left in enumerate(usable):
        for right in usable[i + 1:]:
            try:
                value = float(corr.at[left, right])
            except (KeyError, TypeError):
                continue
            if pd.notna(value) and value >= 0.15:
                scored_pairs.append((value, left, right))

    scored_pairs.sort(reverse=True)
    proposals = []
    for value, left, right in scored_pairs[:max_edges]:
        if right in outcome_names and left not in outcome_names:
            source, target = left, right
        elif left in outcome_names and right not in outcome_names:
            source, target = right, left
        else:
            source, target = (left, right) if column_order[left] < column_order[right] else (right, left)
        proposals.append(
            {
                "source": source,
                "target": target,
                "directed": True,
                "reason": (
                    f"Strong association (|r| = {value:.2f}); direction is a heuristic "
                    "(toward the outcome, else column order) - review before accepting."
                ),
            }
        )
    return proposals


def _acyclic_edge_subset(verified_edges: list[dict[str, Any]]) -> tuple[list[tuple[str, str]], list[str]]:
    """Keep non-rejected edges, dropping the lowest-confidence ones that would create cycles."""
    kept: list[tuple[str, str]] = []
    dropped: list[str] = []
    graph = nx.DiGraph()

    candidates = [
        edge for edge in verified_edges if edge.get("recommended_action") != "reject"
    ]
    candidates.sort(key=lambda edge: float(edge.get("confidence", 0.0) or 0.0), reverse=True)

    for edge in candidates:
        source, target = edge["source"], edge["target"]
        graph.add_edge(source, target)
        if nx.is_directed_acyclic_graph(graph):
            kept.append((source, target))
        else:
            graph.remove_edge(source, target)
            dropped.append(f"{source} -> {target}")

    return kept, dropped


def recommend_estimator(
    data_frame: pd.DataFrame,
    treatment_name: str,
    adjustment_set: list[str],
) -> dict[str, Any]:
    row_count = int(len(data_frame.index))
    treatment_is_binary = (
        treatment_name in data_frame.columns and _is_binary_column(data_frame[treatment_name])
    )

    adjustment_text = (
        f"the graph requires adjusting for {', '.join(adjustment_set)}"
        if adjustment_set
        else "the graph requires no adjustment set"
    )

    if treatment_is_binary and adjustment_set:
        if row_count > 20000:
            method_name = "backdoor.propensity_score_weighting"
            rationale = (
                f"The treatment '{treatment_name}' is binary and {adjustment_text}, so a propensity-score "
                "method is appropriate to balance treated and untreated groups on those confounders. "
                f"Weighting was chosen over matching because with {row_count} rows, pairwise matching "
                "becomes memory-intensive while inverse-probability weighting scales linearly. "
                "If the estimated propensities are extreme (near 0 or 1), consider trimming or "
                "falling back to linear regression."
            )
        else:
            method_name = "backdoor.propensity_score_matching"
            rationale = (
                f"The treatment '{treatment_name}' is binary and {adjustment_text}, so propensity-score "
                "matching is a natural fit: it pairs each treated unit with a statistically similar "
                "untreated unit, making the comparison groups directly interpretable. "
                f"With {row_count} rows the matching step is computationally comfortable. "
                "Compare against linear regression in the Robustness Dashboard - agreement between the "
                "two strengthens the conclusion."
            )
    elif treatment_is_binary:
        method_name = "backdoor.linear_regression"
        rationale = (
            f"The treatment '{treatment_name}' is binary, but {adjustment_text}, so there are no "
            "confounders to balance and a simple regression of the outcome on the treatment already "
            "yields a consistent estimate. "
            "Propensity-score methods would add complexity without adding validity here. "
            "If you believe unmeasured confounders exist, add them to the graph and the recommendation "
            "will update."
        )
    else:
        method_name = "backdoor.linear_regression"
        rationale = (
            f"The treatment '{treatment_name}' takes more than two values (continuous or multi-valued), "
            "which rules out propensity-score methods since they require a binary treatment. "
            f"Linear regression handles graded treatments naturally and {adjustment_text}. "
            "The estimate then reads as the expected change in the outcome per one-unit increase in "
            "the treatment, holding the adjustment variables fixed."
        )

    return {
        "method_name": method_name,
        "rationale": rationale,
        "treatment_is_binary": treatment_is_binary,
        "sample_size": row_count,
    }


@suppress_numeric_estimation_warnings
def check_identifiability(
    data_frame: pd.DataFrame,
    edge_list: list[tuple[str, str]],
    treatment_name: str,
    outcome_name: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "checked": False,
        "identifiable": False,
        "adjustment_set": [],
        "iv_candidates": [],
        "note": "",
    }

    if not edge_list:
        result["note"] = "No usable edges to build a graph from."
        return result

    dot_graph, directed_graph, node_names = build_dot_graph(edge_list)
    if treatment_name not in node_names or outcome_name not in node_names:
        result["note"] = "Suggested treatment/outcome are not connected by the proposed edges."
        return result

    try:
        model = get_causal_model_class()(
            data=data_frame,
            treatment=treatment_name,
            outcome=outcome_name,
            graph=dot_graph,
        )
        identified = model.identify_effect()
    except ImportError:
        result["note"] = "DoWhy is not installed; identifiability was not verified."
        return result
    except Exception as exc:
        result["note"] = f"Identification check failed: {exc}"
        return result

    result["checked"] = True
    if identified is None:
        result["note"] = "Effect is not identifiable from the proposed graph."
        return result

    result["identifiable"] = True
    try:
        result["adjustment_set"] = list(identified.get_backdoor_variables() or [])
        result["iv_candidates"] = list(identified.get_instrumental_variables() or [])
    except Exception:
        pass
    result["note"] = "Effect is identifiable from the proposed graph."
    return result


def suggest_causal_model(
    data_frame: pd.DataFrame,
    context: str = "",
    max_edges: int = 12,
    llm_suggestion: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Combine LLM output (optional), statistical verification, and deterministic
    heuristics into a reviewable model suggestion."""
    profile = profile_data_frame(data_frame)
    notes: list[str] = []

    heuristic_treatments, heuristic_outcomes = heuristic_role_candidates(data_frame, profile)

    llm_used = llm_suggestion is not None
    reasoning = ""
    if llm_used:
        reasoning = str(llm_suggestion.get("reasoning", "")).strip()
        proposed_edges = llm_suggestion.get("edges", [])
        valid_names = set(str(name) for name in data_frame.columns)
        treatment_candidates = [
            {"name": name, "reason": "Suggested by the language model from variable semantics."}
            for name in llm_suggestion.get("treatment_candidates", [])
            if name in valid_names
        ]
        outcome_candidates = [
            {"name": name, "reason": "Suggested by the language model from variable semantics."}
            for name in llm_suggestion.get("outcome_candidates", [])
            if name in valid_names
        ]
        for hypothesis in llm_suggestion.get("unobserved_confounders", []):
            notes.append(f"Possible unobserved confounder: {hypothesis}")
        if llm_suggestion.get("notes"):
            notes.append(str(llm_suggestion["notes"]))

        known = {item["name"] for item in treatment_candidates}
        treatment_candidates += [item for item in heuristic_treatments if item["name"] not in known]
        known = {item["name"] for item in outcome_candidates}
        outcome_candidates += [item for item in heuristic_outcomes if item["name"] not in known]
    else:
        treatment_candidates = heuristic_treatments
        outcome_candidates = heuristic_outcomes
        proposed_edges = heuristic_edge_proposals(data_frame, profile, outcome_candidates, max_edges)
        notes.append(
            "No LLM available: edges come from pairwise associations and edge directions are heuristic."
        )
        reasoning_sentences = []
        if outcome_candidates:
            reasoning_sentences.append(
                f"'{outcome_candidates[0]['name']}' was selected as the outcome because "
                f"{outcome_candidates[0]['reason'].rstrip('.').lower()}."
            )
        if treatment_candidates:
            reasoning_sentences.append(
                f"'{treatment_candidates[0]['name']}' leads the treatment candidates because "
                f"{treatment_candidates[0]['reason'].rstrip('.').lower()}, which makes it a lever "
                "one could realistically intervene on."
            )
        reasoning_sentences.append(
            "The proposed edges connect the variable pairs with the strongest statistical "
            "associations in this dataset; because correlation alone cannot determine direction, "
            "each arrow points toward the outcome where possible and otherwise follows column "
            "order, so every direction should be reviewed against domain knowledge."
        )
        reasoning_sentences.append(
            "No language model was available for this draft, so the structure reflects the data "
            "alone and encodes no domain understanding of the underlying mechanisms."
        )
        reasoning = " ".join(reasoning_sentences)

    processed = preprocess_data_frame_for_causal(data_frame)
    verified_edges = verify_proposed_edges(processed, proposed_edges)
    variable_names = [str(name) for name in data_frame.columns]
    hypotheses = derive_graph_hypotheses(variable_names, verified_edges)

    edge_list, dropped_for_cycles = _acyclic_edge_subset(verified_edges)
    if dropped_for_cycles:
        notes.append(
            "Dropped low-confidence edge(s) to keep the suggested graph acyclic: "
            + "; ".join(dropped_for_cycles)
        )

    treatment_name = treatment_candidates[0]["name"] if treatment_candidates else ""
    outcome_name = outcome_candidates[0]["name"] if outcome_candidates else ""

    identification: dict[str, Any] = {
        "checked": False,
        "identifiable": False,
        "adjustment_set": [],
        "iv_candidates": [],
        "note": "Select treatment and outcome candidates to check identifiability.",
    }
    recommended_estimator: dict[str, Any] = {}
    if treatment_name and outcome_name and treatment_name != outcome_name:
        identification = check_identifiability(processed, edge_list, treatment_name, outcome_name)
        recommended_estimator = recommend_estimator(
            processed, treatment_name, identification.get("adjustment_set", [])
        )

    return {
        "edges": verified_edges,
        "treatment_candidates": treatment_candidates,
        "outcome_candidates": outcome_candidates,
        "recommended_estimator": recommended_estimator,
        "identification": identification,
        "confounder_candidates": hypotheses["confounder_candidates"],
        "iv_candidates": hypotheses["iv_candidates"],
        "missing_confounder_hypotheses": hypotheses["missing_confounder_hypotheses"],
        "summary": summarize_graph_copilot(verified_edges),
        "llm_used": llm_used,
        "reasoning": reasoning,
        "notes": notes,
    }


def build_model_variants(
    edge_list: list[tuple[str, str]], treatment_name: str, outcome_name: str
) -> list[dict[str, Any]]:
    """Derive 2-3 plausible DAG variants from the canvas graph for a stability check."""
    canvas_edges = list(dict.fromkeys(edge_list))
    variants: list[dict[str, Any]] = [
        {
            "key": "canvas",
            "name": "Canvas model",
            "description": "The graph exactly as drawn on the canvas - your working hypothesis.",
            "edges": canvas_edges,
        }
    ]

    minimal_edges = [(source, target) for source, target in canvas_edges if target == outcome_name]
    if (treatment_name, outcome_name) not in minimal_edges:
        minimal_edges.append((treatment_name, outcome_name))
    variants.append(
        {
            "key": "minimal",
            "name": "Minimal direct-effects model",
            "description": (
                "Keeps only direct influences on the outcome and drops all upstream structure. "
                "If the estimate barely changes, the upstream part of your graph does not drive the result."
            ),
            "edges": list(dict.fromkeys(minimal_edges)),
        }
    )

    confounded_edges = list(canvas_edges)
    for source, target in canvas_edges:
        if target == outcome_name and source not in (treatment_name, outcome_name):
            candidate = (source, treatment_name)
            reverse = (treatment_name, source)
            if candidate not in confounded_edges and reverse not in confounded_edges:
                confounded_edges.append(candidate)
    variants.append(
        {
            "key": "confounded",
            "name": "Confounder-stressed model",
            "description": (
                "Assumes every direct cause of the outcome also influences the treatment - a "
                "worst-case confounding scenario that forces maximal adjustment. A stable estimate "
                "here is strong evidence the effect is not an artifact of the chosen structure."
            ),
            "edges": list(dict.fromkeys(confounded_edges)),
        }
    )

    seen_signatures: set[tuple] = set()
    unique_variants = []
    for variant in variants:
        _, directed_graph, _ = build_dot_graph(variant["edges"])
        if not nx.is_directed_acyclic_graph(directed_graph):
            continue
        signature = tuple(sorted(variant["edges"]))
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        unique_variants.append(variant)

    return unique_variants


@suppress_numeric_estimation_warnings
def compare_model_variants(
    data_frame: pd.DataFrame,
    edge_list: list[tuple[str, str]],
    treatment_name: str,
    outcome_name: str,
    requested_method: str | None = None,
) -> dict[str, Any]:
    """Estimate the effect under competing DAG variants and judge stability."""
    from .services import estimate_effect

    variants = build_model_variants(edge_list, treatment_name, outcome_name)
    models: list[dict[str, Any]] = []

    for variant in variants:
        dot_graph, _, node_names = build_dot_graph(variant["edges"])
        entry: dict[str, Any] = {
            "key": variant["key"],
            "name": variant["name"],
            "description": variant["description"],
            "edges": [f"{source} -> {target}" for source, target in variant["edges"]],
            "estimated_effect": None,
            "method_name": "",
            "error": "",
        }
        if treatment_name not in node_names or outcome_name not in node_names:
            entry["error"] = "Treatment or outcome is not connected in this variant."
            models.append(entry)
            continue
        try:
            result = estimate_effect(
                data_frame, treatment_name, outcome_name, dot_graph, requested_method
            )
            entry["estimated_effect"] = float(result["estimated_effect"])
            entry["method_name"] = result["method_name"]
        except Exception as exc:
            entry["error"] = str(exc)
        models.append(entry)

    effects = [
        entry["estimated_effect"] for entry in models if entry["estimated_effect"] is not None
    ]
    stability: dict[str, Any] = {
        "verdict": "unknown",
        "spread": None,
        "relative_spread": None,
        "same_sign": None,
        "summary": "",
    }

    if len(effects) == 0:
        stability["summary"] = (
            "No model variant produced an estimate, so stability could not be assessed. "
            "Check the per-model errors above."
        )
    elif len(effects) == 1:
        stability["verdict"] = "insufficient"
        stability["summary"] = (
            "Only one variant produced an estimate, so the effect's sensitivity to model choice "
            "could not be assessed. Treat the single number with corresponding caution."
        )
    else:
        spread = max(effects) - min(effects)
        max_abs = max(abs(value) for value in effects)
        relative_spread = spread / max_abs if max_abs > 0 else 0.0
        same_sign = all(value >= 0 for value in effects) or all(value <= 0 for value in effects)
        stability["spread"] = round(spread, 6)
        stability["relative_spread"] = round(relative_spread, 4)
        stability["same_sign"] = same_sign

        effects_text = ", ".join(f"{value:.4f}" for value in effects)
        if same_sign and relative_spread <= 0.35:
            stability["verdict"] = "stable"
            stability["summary"] = (
                f"The estimated effect is stable across {len(effects)} competing model structures "
                f"({effects_text}): every variant agrees on the direction and the estimates differ by "
                f"at most {relative_spread:.0%} of the largest magnitude. This is meaningful evidence "
                "that the conclusion does not hinge on the exact graph you drew."
            )
        elif same_sign:
            stability["verdict"] = "moderate"
            stability["summary"] = (
                f"All {len(effects)} model variants agree on the direction of the effect "
                f"({effects_text}), but the magnitude varies by {relative_spread:.0%}. The sign of the "
                "conclusion is trustworthy; quote the size of the effect with a caveat about model "
                "dependence."
            )
        else:
            stability["verdict"] = "unstable"
            stability["summary"] = (
                f"The estimated effect changes sign across model structures ({effects_text}), meaning "
                "the conclusion depends critically on which causal graph is assumed. Do not act on "
                "this estimate before resolving the structural uncertainty - review the disputed "
                "edges and consider collecting data on the suspected confounders."
            )

    return {"models": models, "stability": stability}
