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


# ---------------------------------------------------------------------------
# Structured AI result (Day 4)
#
# generate_structured_ai_insights() is the entry point Day 4's unified
# pipeline (backend/pipeline.py) uses. Unlike generate_ai_insights()
# above (which returns free-form markdown for the existing "Business
# Insights (AI)" dashboard section and is left untouched), this
# returns a normalized {summary, insights[], risks[], opportunities[]}
# structure that the unified final report can embed directly.
#
# The model is given the same analytical context PLUS the already-
# computed evidence/prioritized-findings lists (backend/evidence.py,
# backend/prioritization.py) and is instructed to explain that
# evidence, never invent new numbers or priorities. If the model's
# response isn't valid/usable JSON, or no provider is configured/
# reachable, this falls back to a structured result built entirely
# from evidence -- deterministic, AI-free, and always available.
# ---------------------------------------------------------------------------

_STRUCTURED_SYSTEM_PROMPT = (
    "You are the insight-explanation layer for VISORA BI. You will be "
    "given a JSON analytical context, a list of deterministic 'evidence' "
    "items, and those same items with a deterministic 'priority' "
    "(critical/high/medium/low) already assigned -- all already computed "
    "by VISORA's own analytics engine. Your only job is to explain this "
    "evidence in plain, decision-useful language.\n\n"
    "Respond with ONLY a single JSON object (no markdown fences, no "
    "commentary before or after) matching exactly this shape:\n"
    "{\n"
    '  "summary": "2-4 sentence plain-language summary",\n'
    '  "insights": [\n'
    "    {\n"
    '      "id": "the evidence id this insight explains, or null",\n'
    '      "title": "short title",\n'
    '      "type": "trend|anomaly|contribution|quality|metric",\n'
    '      "priority": "critical|high|medium|low",\n'
    '      "explanation": "1-3 sentences grounded only in the evidence",\n'
    '      "evidence": ["evidence id(s) this insight is based on"]\n'
    "    }\n"
    "  ],\n"
    '  "risks": ["short plain-language risk statements"],\n'
    '  "opportunities": ["short plain-language opportunity statements"]\n'
    "}\n\n"
    "Rules: only reference numbers, percentages, dates, categories, "
    "trends, and anomalies that literally appear in the provided JSON. "
    "Never invent a figure, never recalculate one, never assign a "
    "priority different from the one already given for an evidence "
    "item you reference. If there is no evidence, return empty lists "
    "and a summary saying so. Do not speculate about business causes "
    "not supported by the data."
)


def _build_structured_prompt(analysis_context, evidence, prioritized_findings):
    dataset_name = analysis_context.get("dataset", {}).get("original_filename") or "the uploaded dataset"
    return (
        f"Dataset: {dataset_name}\n\n"
        "Analytical context (JSON, already computed):\n"
        f"{json.dumps(analysis_context, indent=2)}\n\n"
        "Evidence (JSON list):\n"
        f"{json.dumps(evidence, indent=2)}\n\n"
        "Prioritized findings (same evidence, each with a 'priority' "
        "already assigned -- JSON list):\n"
        f"{json.dumps(prioritized_findings, indent=2)}\n\n"
        "Return the JSON object described in the system prompt, "
        "explaining this evidence for a business user."
    )


def _strip_code_fence(text):
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


_VALID_PRIORITIES = {"critical", "high", "medium", "low"}
_VALID_INSIGHT_TYPES = {"trend", "anomaly", "contribution", "quality", "metric"}


def _normalize_structured_payload(payload, evidence_by_id):
    """Coerce a parsed JSON payload into the exact structured shape,
    dropping/fixing anything malformed rather than raising. Returns
    None if the payload isn't even a usable dict (caller treats that
    as a failed AI attempt and falls back)."""
    if not isinstance(payload, dict):
        return None

    summary = payload.get("summary")
    summary = summary.strip() if isinstance(summary, str) and summary.strip() else "No summary was provided."

    insights = []
    for raw_insight in payload.get("insights") or []:
        if not isinstance(raw_insight, dict):
            continue
        evidence_ids = raw_insight.get("evidence")
        if isinstance(evidence_ids, str):
            evidence_ids = [evidence_ids]
        elif not isinstance(evidence_ids, list):
            evidence_ids = []
        # Only keep references to evidence that actually exists --
        # never trust an AI-supplied id blindly, and never let a
        # dangling reference imply a number that isn't there.
        evidence_ids = [eid for eid in evidence_ids if eid in evidence_by_id]

        priority = raw_insight.get("priority")
        # Priority is deterministic (backend/prioritization.py) -- if
        # this insight references evidence, its priority is pinned to
        # that evidence's already-assigned priority, never whatever
        # the model said.
        if evidence_ids:
            priority = evidence_by_id[evidence_ids[0]].get("priority", priority)
        if priority not in _VALID_PRIORITIES:
            priority = "low"

        insight_type = raw_insight.get("type")
        if insight_type not in _VALID_INSIGHT_TYPES:
            insight_type = (evidence_by_id.get(evidence_ids[0], {}).get("type") if evidence_ids else None) or "metric"

        title = raw_insight.get("title")
        title = title.strip() if isinstance(title, str) and title.strip() else "Untitled finding"
        explanation = raw_insight.get("explanation")
        explanation = explanation.strip() if isinstance(explanation, str) else ""

        insights.append({
            "id": raw_insight.get("id") if isinstance(raw_insight.get("id"), str) else (evidence_ids[0] if evidence_ids else None),
            "title": title,
            "type": insight_type,
            "priority": priority,
            "explanation": explanation,
            "evidence": [evidence_by_id[eid] for eid in evidence_ids],
        })

    risks = [str(item).strip() for item in (payload.get("risks") or []) if str(item).strip()]
    opportunities = [str(item).strip() for item in (payload.get("opportunities") or []) if str(item).strip()]

    return {
        "available": True,
        "summary": summary,
        "insights": insights,
        "risks": risks,
        "opportunities": opportunities,
    }


def _parse_structured_response(text, evidence_by_id):
    cleaned = _strip_code_fence(text)
    try:
        payload = json.loads(cleaned)
    except (ValueError, json.JSONDecodeError):
        return None
    return _normalize_structured_payload(payload, evidence_by_id)


def _local_structured_fallback(analysis_context, evidence, prioritized_findings):
    """Build the structured shape entirely from already-computed
    evidence -- no AI, no invented text beyond simple templating
    around numbers that are already present. Always available, used
    whenever no AI provider produced usable structured output."""
    insights = [
        {
            "id": item.get("id"),
            "title": item.get("title"),
            "type": item.get("type"),
            "priority": item.get("priority", "low"),
            "explanation": item.get("title"),
            "evidence": [item],
        }
        for item in prioritized_findings
    ]

    risks = [
        item["title"] for item in prioritized_findings
        if item.get("priority") in ("critical", "high") and item.get("type") in ("anomaly", "quality")
    ]
    opportunities = [
        item["title"] for item in prioritized_findings
        if item.get("type") in ("trend", "concentration") and item.get("priority") != "low"
    ]

    if prioritized_findings:
        top = prioritized_findings[0]
        summary = (
            f"{len(prioritized_findings)} notable finding(s) detected, generated directly from "
            f"VISORA's analytical engine. Most significant: {top.get('title')} ({top.get('priority')})."
        )
    else:
        summary = _local_fallback_text(analysis_context)

    return {
        "available": True,
        "summary": summary,
        "insights": insights,
        "risks": risks,
        "opportunities": opportunities,
    }


@dataclass
class AIStructuredResult:
    result: dict
    source: str  # "ai" or "local_fallback"
    provider_used: Optional[str] = None
    ai_attempted: bool = False
    ai_skipped_reason: Optional[str] = None
    attempts: List[ProviderAttempt] = field(default_factory=list)


def generate_structured_ai_insights(analysis_context, evidence, prioritized_findings, file_size_bytes=None):
    """Return an AIStructuredResult: a normalized {summary, insights[],
    risks[], opportunities[]} dict, either produced by an AI provider
    (grounded in `evidence`/`prioritized_findings`) or, on any failure
    mode at all (no provider configured, provider error, malformed
    response, oversized context), built locally from the same
    evidence with no AI involvement. Never raises."""
    evidence_by_id = {item["id"]: item for item in (evidence or []) if item.get("id")}

    within_ai_limit = file_size_bytes is None or file_size_bytes <= AI_CONTEXT_LIMIT_BYTES
    if not within_ai_limit:
        return AIStructuredResult(
            result=_local_structured_fallback(analysis_context, evidence, prioritized_findings),
            source="local_fallback",
            ai_attempted=False,
            ai_skipped_reason="size_threshold_exceeded",
        )

    system = _STRUCTURED_SYSTEM_PROMPT
    prompt = _build_structured_prompt(analysis_context, evidence, prioritized_findings)
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
            raw_text = provider.complete(system, prompt)
        except AIProviderError as exc:
            attempts.append(ProviderAttempt(exc.provider_name, exc.category, exc.message))
            continue
        except Exception as exc:  # a provider must never take the pipeline down with it
            attempts.append(ProviderAttempt(provider_config.display_name, "unavailable", str(exc)))
            continue

        normalized = _parse_structured_response(raw_text, evidence_by_id)
        if normalized is None:
            attempts.append(ProviderAttempt(provider.name, "invalid_response", "Response was not valid structured JSON."))
            continue

        return AIStructuredResult(
            result=normalized,
            source="ai",
            provider_used=provider.name,
            ai_attempted=True,
            attempts=attempts,
        )

    skipped_reason = "not_configured" if not attempts else None
    return AIStructuredResult(
        result=_local_structured_fallback(analysis_context, evidence, prioritized_findings),
        source="local_fallback",
        ai_attempted=bool(attempts),
        ai_skipped_reason=skipped_reason,
        attempts=attempts,
    )
