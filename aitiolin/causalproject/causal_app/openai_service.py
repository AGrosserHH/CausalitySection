import json
from collections.abc import Sequence

from django.conf import settings


SYSTEM_PROMPT = (
    "You are a causal discovery assistant. Suggest plausible directed causal edges among the "
    "provided variables. Return only valid JSON with key 'edges' where each edge is an object "
    "with: source, target, directed (boolean), reason (short string). Use only provided variable "
    "names. Do not invent variables."
)

MODEL_SYSTEM_PROMPT = (
    "You are a causal analysis agent. You receive variable names plus a statistical profile of the "
    "dataset (types, missingness, ranges, quality warnings). Propose a causal model for analysis. "
    "Return only valid JSON with keys: 'edges' (list of {source, target, directed, reason} where each "
    "reason is one full sentence), "
    "'treatment_candidates' (list of variable names most plausible as interventions, best first), "
    "'outcome_candidates' (list of variable names most plausible as the outcome of interest, best first), "
    "'unobserved_confounders' (list of short strings naming likely unmeasured common causes), "
    "'reasoning' (a paragraph of 3-5 full sentences explaining WHY this causal structure is plausible "
    "for this dataset: what the outcome represents, why the chosen treatments are actionable levers, "
    "which mechanisms the main edges encode, and what the biggest structural uncertainty is), and "
    "'notes' (one short paragraph of caveats). Use only provided variable names in edges and "
    "candidate lists. Do not invent variables."
)


def _normalize_variables(variables: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()

    for value in variables:
        clean_value = str(value).strip()
        if not clean_value or clean_value in seen:
            continue
        normalized.append(clean_value)
        seen.add(clean_value)

    return normalized


def _parse_edges(content: str, valid_variables: set[str], max_edges: int) -> list[dict]:
    payload = json.loads(content)
    raw_edges = payload.get("edges", [])
    if not isinstance(raw_edges, list):
        raise ValueError("OpenAI response did not contain an 'edges' list.")

    suggestions: list[dict] = []
    dedupe: set[tuple[str, str, bool]] = set()

    for item in raw_edges:
        if not isinstance(item, dict):
            continue

        source = str(item.get("source", "")).strip()
        target = str(item.get("target", "")).strip()
        directed = bool(item.get("directed", True))
        reason = str(item.get("reason", "")).strip()

        if source not in valid_variables or target not in valid_variables:
            continue
        if source == target:
            continue

        key = (source, target, directed)
        if key in dedupe:
            continue
        dedupe.add(key)

        suggestions.append(
            {
                "source": source,
                "target": target,
                "directed": directed,
                "reason": reason,
            }
        )

        if len(suggestions) >= max_edges:
            break

    return suggestions


def suggest_edges_with_openai(variables: Sequence[str], context: str = "", max_edges: int = 10) -> list[dict]:
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured.")

    clean_variables = _normalize_variables(variables)
    if len(clean_variables) < 2:
        raise ValueError("At least two variables are required.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImportError("OpenAI package is not installed.") from exc

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    user_prompt = (
        "Variables:\n"
        + "\n".join(f"- {name}" for name in clean_variables)
        + "\n\nContext:\n"
        + (context.strip() or "No extra context provided.")
        + f"\n\nReturn at most {max_edges} suggested edges in JSON."
    )

    completion = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    content = completion.choices[0].message.content or "{}"
    return _parse_edges(content, set(clean_variables), max_edges)


def suggest_model_with_openai(
    variables: Sequence[str],
    profile_summary: str,
    context: str = "",
    max_edges: int = 12,
) -> dict:
    """Ask the LLM for a full model suggestion: edges plus treatment/outcome roles."""
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured.")

    clean_variables = _normalize_variables(variables)
    if len(clean_variables) < 2:
        raise ValueError("At least two variables are required.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImportError("OpenAI package is not installed.") from exc

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    user_prompt = (
        "Variables:\n"
        + "\n".join(f"- {name}" for name in clean_variables)
        + "\n\nDataset profile:\n"
        + (profile_summary.strip() or "No profile available.")
        + "\n\nContext:\n"
        + (context.strip() or "No extra context provided.")
        + f"\n\nReturn at most {max_edges} suggested edges in JSON."
    )

    completion = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": MODEL_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    content = completion.choices[0].message.content or "{}"
    valid_variables = set(clean_variables)
    edges = _parse_edges(content, valid_variables, max_edges)

    payload = json.loads(content)

    def _clean_name_list(key: str) -> list[str]:
        raw = payload.get(key, [])
        if not isinstance(raw, list):
            return []
        cleaned = []
        for item in raw:
            name = str(item).strip()
            if name in valid_variables and name not in cleaned:
                cleaned.append(name)
        return cleaned

    raw_confounders = payload.get("unobserved_confounders", [])
    unobserved = (
        [str(item).strip() for item in raw_confounders if str(item).strip()]
        if isinstance(raw_confounders, list)
        else []
    )

    return {
        "edges": edges,
        "treatment_candidates": _clean_name_list("treatment_candidates"),
        "outcome_candidates": _clean_name_list("outcome_candidates"),
        "unobserved_confounders": unobserved[:8],
        "reasoning": str(payload.get("reasoning", "")).strip(),
        "notes": str(payload.get("notes", "")).strip(),
    }
