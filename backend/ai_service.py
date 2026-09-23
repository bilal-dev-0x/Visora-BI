"""
AI insight layer (Day 3).

generate_ai_insights() is the single entry point the dashboard calls.
It never performs its own business-metric calculations -- every number
it can talk about already exists in the unified analytical context
produced by backend/analysis_context.py (Day 1). This module's job is
only to:

    1. decide whether the dataset is small enough to send that context
       to an AI provider at all (backend/config.py's AI_CONTEXT_LIMIT),
    2. if so, walk the configured provider chain
       (backend/ai_providers.py) until one succeeds or all fail,
    3. otherwise -- or if every provider fails -- fall back to a
       cleaned, human-readable summary built directly from the same
       analytical context, with no AI involved.

AI explains VISORA's numbers; it never replaces them. The system
prompt below instructs the model accordingly, and the local fallback
never invents anything not already present in analysis_context.
"""

import json
from dataclasses import dataclass, field
from typing import List, Optional

from backend.ai_providers import AIProviderError, build_provider
from backend.config import AI_CONTEXT_LIMIT_BYTES, load_provider_chain

_SYSTEM_PROMPT = (
    "You are the insight-explanation layer for VISORA BI, a business "
    "intelligence tool. You will be given a JSON analytical context "
    "that VISORA's own deterministic analytics engine already "
    "computed -- metrics, trends, contribution breakdowns, anomalies, "
    "and data-quality findings. Your job is to explain and summarize "
    "these existing results in plain, decision-useful language for a "
    "business user. Do NOT invent, recalculate, or contradict any "
    "number. Only reference figures that appear in the provided JSON. "
    "If a section is unavailable, do not speculate about it. Write a "
    "short set of clear findings (prefer concise bullet points), "
    "highlighting what matters most: notable trends, top/bottom "
    "contributors, anomalies worth attention, and any data-quality "
    "caveats that affect trust in the numbers."
)

@dataclass
class ProviderAttempt:
    provider_name: str
    category: str
    message: str


@dataclass
class AIInsightResult:
    text: str
    source: str  # "ai" or "local_fallback"
    provider_used: Optional[str] = None
    ai_attempted: bool = False
    ai_skipped_reason: Optional[str] = None  # "size_threshold_exceeded" | "not_configured" | None
    attempts: List[ProviderAttempt] = field(default_factory=list)


def _serialize_context_for_prompt(analysis_context):
    """Serialize the full analytical context for the prompt, exactly as
    analysis_context.py produced it. No truncation, compression, or
    size-based trimming here -- the only gate on what reaches an AI
    provider is the upstream <=100MB / >100MB file-size check in
    generate_ai_insights(). Below that threshold, the complete context
    goes to the provider, full stop; above it, this function is never
    called at all (the caller goes straight to the local fallback)."""
    return json.dumps(analysis_context, indent=2)


def _build_prompt(analysis_context):
    dataset_name = analysis_context.get("dataset", {}).get("original_filename") or "the uploaded dataset"
    context_json = _serialize_context_for_prompt(analysis_context)
    return (
        f"Dataset: {dataset_name}\n\n"
        "Analytical context (JSON, already computed by VISORA's engine):\n"
        f"{context_json}\n\n"
        "Summarize the key findings for a business user, grounded only "
        "in the numbers above."
    )



def _run_provider_chain(analysis_context):
    """Try each configured provider in order. Returns
    (text, provider_name, attempts) on success, or (None, None,
    attempts) if every configured provider failed (or none were
    configured)."""
    system = _SYSTEM_PROMPT
    prompt = _build_prompt(analysis_context)
    attempts = []

    for provider_config in load_provider_chain():
        if not provider_config.is_configured:
            continue

        provider = build_provider(provider_config)
        if provider is None:
            attempts.append(ProviderAttempt(
                provider_config.display_name, "not_configured", f"Unknown provider type '{provider_config.kind}'.",
            ))
            continue

        try:
            text = provider.complete(system, prompt)
            return text, provider.name, attempts
        except AIProviderError as exc:
            attempts.append(ProviderAttempt(exc.provider_name, exc.category, exc.message))
            continue
        except Exception as exc:  # a provider must never take the dashboard down with it
            attempts.append(ProviderAttempt(provider_config.display_name, "unavailable", str(exc)))
            continue

    return None, None, attempts


def _format_metrics_fallback(metrics_section):
    if not metrics_section.get("available"):
        return []
    lines = []
    for column, values in (metrics_section.get("data") or {}).items():
        if "error" in values:
            continue
        total = values.get("sum")
        average = values.get("average")
        if total is None:
            continue
        lines.append(f"- **{column}**: total {total:,.2f}, average {average:,.2f}" if average is not None
                     else f"- **{column}**: total {total:,.2f}")
    return lines


def _format_trends_fallback(trends_section):
    if not trends_section.get("available"):
        return []
    data = trends_section.get("data") or {}
    measure = data.get("measure_column", "the tracked measure")
    lines = []

    # TrendEngine.calculate_growth_generic() returns a list of
    # {"period", "value", "growth_percent", "growth_reason", ...}
    # entries, one per period -- the most recent one with a usable
    # growth_percent is what a "latest change" headline means here.
    growth_entries = data.get("growth") or []
    latest_growth = next(
        (entry for entry in reversed(growth_entries) if entry.get("growth_percent") is not None), None,
    )
    if latest_growth is not None:
        latest_change = latest_growth["growth_percent"]
        direction = "up" if latest_change >= 0 else "down"
        lines.append(
            f"- {measure} is {direction} {abs(latest_change):.1f}% as of {latest_growth.get('period')}."
        )

    # TrendEngine.compare_last_two_periods_generic() returns a single
    # dict with an explicit "available" flag rather than always
    # carrying change_percent.
    period_comparison = data.get("period_comparison") or {}
    if period_comparison.get("available") and period_comparison.get("change_percent") is not None:
        lines.append(
            f"- Comparing the last two periods ({period_comparison.get('previous_period')} -> "
            f"{period_comparison.get('current_period')}), {measure} changed by "
            f"{period_comparison['change_percent']:.1f}%."
        )
    return lines


def _format_contribution_fallback(contribution_section):
    if not contribution_section.get("available"):
        return []
    data = contribution_section.get("data") or {}
    breakdown = data.get("breakdown") or []
    if not breakdown:
        return []
    top = breakdown[0]
    dimension = data.get("dimension", "category")
    measure = data.get("measure", "value")
    lines = [
        f"- Top {dimension} by {measure}: **{top.get('category')}** "
        f"({top.get('percent', 0):.1f}% of total)."
    ]
    return lines


def _format_anomalies_fallback(anomalies_section):
    if not anomalies_section.get("available"):
        return []
    data = anomalies_section.get("data") or {}
    lines = []
    for column, anomalies in data.items():
        if isinstance(anomalies, dict) and "error" in anomalies:
            continue
        if anomalies:
            lines.append(f"- {len(anomalies)} anomaly(ies) detected in **{column}**.")
    return lines


def _format_data_quality_fallback(data_quality_section):
    lines = []
    missing = data_quality_section.get("total_missing_values", 0) or 0
    duplicates = data_quality_section.get("duplicate_rows", 0) or 0
    if missing:
        lines.append(f"- {missing:,} missing value(s) were detected across the dataset.")
    if duplicates:
        lines.append(f"- {duplicates:,} duplicate row(s) were detected.")
    return lines


def _local_fallback_text(analysis_context):
    """Build a human-readable summary using ONLY facts already present
    in analysis_context -- no invented insight, no independent
    calculation. Mirrors backend/insights.py's philosophy but works
    from the unified analytical context instead of a live DataAnalyzer,
    so it stays consistent with whatever the AI prompt would have seen."""
    sections = []
    sections.extend(_format_trends_fallback(analysis_context.get("trends", {})))
    sections.extend(_format_contribution_fallback(analysis_context.get("contribution", {})))
    sections.extend(_format_anomalies_fallback(analysis_context.get("anomalies", {})))
    sections.extend(_format_metrics_fallback(analysis_context.get("metrics", {})))
    sections.extend(_format_data_quality_fallback(analysis_context.get("data_quality", {})))

    if not sections:
        return "VISORA's analytical engine did not find enough structured signal in this dataset to summarize."
    return "\n".join(sections)


def generate_ai_insights(analysis_context, file_size_bytes=None):
    """Return an AIInsightResult for the given analytical context.

    file_size_bytes: the size of the originally uploaded file (not the
    serialized JSON). When it exceeds AI_CONTEXT_LIMIT_BYTES, the full
    analytical context is never sent to any AI provider -- this
    function goes straight to the local fallback, per VISORA's AI
    context size policy. Pass None to always allow AI (e.g. contexts
    built for validation/testing outside the upload flow).
    """
    within_ai_limit = file_size_bytes is None or file_size_bytes <= AI_CONTEXT_LIMIT_BYTES

    if not within_ai_limit:
        return AIInsightResult(
            text=_local_fallback_text(analysis_context),
            source="local_fallback",
            ai_attempted=False,
            ai_skipped_reason="size_threshold_exceeded",
        )

    text, provider_name, attempts = _run_provider_chain(analysis_context)

    if text is not None:
        return AIInsightResult(
            text=text,
            source="ai",
            provider_used=provider_name,
            ai_attempted=True,
            attempts=attempts,
        )

    skipped_reason = None
    if not attempts:
        skipped_reason = "not_configured"

    return AIInsightResult(
        text=_local_fallback_text(analysis_context),
        source="local_fallback",
        ai_attempted=bool(attempts),
        ai_skipped_reason=skipped_reason,
        attempts=attempts,
    )
