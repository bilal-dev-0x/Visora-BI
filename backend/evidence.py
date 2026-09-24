"""
Evidence layer (Day 4).

build_evidence() turns the unified analytical context that
backend/analysis_context.py already computed into a flat list of
"evidence" items: small, self-contained facts that are each traceable
back to one deterministic analytical result (a trend, an anomaly, a
concentration, a data-quality finding, ...).

This module performs NO analytical calculation of its own -- every
number in an evidence item is read straight out of the analytical
context. It only decides which already-computed facts are notable
enough to surface, and packages each one with enough context (type,
title, value, period/column, source) to explain where it came from.

Evidence is the input to backend/prioritization.py (which assigns
Critical/High/Medium/Low) and to the structured AI layer in
backend/ai_service.py (which explains evidence, but must never invent
it). Nothing here ever fabricates a number, a trend, or a cause.
"""

# Minimum |growth percent| for a period-over-period change to be
# surfaced as evidence at all. Below this, a change is treated as
# normal period-to-period noise rather than a notable movement.
_GROWTH_EVIDENCE_THRESHOLD = 5.0

# Minimum share of total (percent) for a top contributor to be
# surfaced as a "concentration" evidence item.
_CONCENTRATION_EVIDENCE_THRESHOLD = 25.0

# Minimum |z_score| for an anomaly to be surfaced as evidence, on top
# of whatever threshold AnomalyDetector already applied internally.
_ANOMALY_EVIDENCE_Z_THRESHOLD = 2.0

# Minimum missing-value ratio (fraction of all cells) / duplicate-row
# ratio (fraction of all rows) to be surfaced as a data-quality
# evidence item.
_MISSINGNESS_EVIDENCE_RATIO = 0.05
_DUPLICATE_EVIDENCE_RATIO = 0.05


def _evidence(evidence_type, title, value, **extra):
    item = {
        "type": evidence_type,
        "title": title,
        "value": value,
        "source": "deterministic",
    }
    item.update(extra)
    return item


def _trend_evidence(trends_section):
    if not trends_section.get("available"):
        return []

    data = trends_section.get("data") or {}
    measure = data.get("measure_column")
    date_column = data.get("date_column")
    items = []

    for entry in data.get("growth") or []:
        growth_percent = entry.get("growth_percent")
        if growth_percent is None or abs(growth_percent) < _GROWTH_EVIDENCE_THRESHOLD:
            continue
        direction = "grew" if growth_percent >= 0 else "declined"
        items.append(_evidence(
            "trend",
            f"{measure} {direction} {abs(growth_percent):.1f}% in {entry.get('period')}",
            growth_percent,
            period=entry.get("period"),
            column=measure,
            date_column=date_column,
        ))

    comparison = data.get("period_comparison") or {}
    if comparison.get("available") and comparison.get("change_percent") is not None:
        change_percent = comparison["change_percent"]
        if abs(change_percent) >= _GROWTH_EVIDENCE_THRESHOLD:
            direction = "up" if change_percent >= 0 else "down"
            items.append(_evidence(
                "trend",
                f"{measure} is {direction} {abs(change_percent):.1f}% vs. the previous period",
                change_percent,
                period=comparison.get("current_period"),
                column=measure,
                date_column=date_column,
            ))

    return items


def _contribution_evidence(contribution_section):
    if not contribution_section.get("available"):
        return []

    data = contribution_section.get("data") or {}
    breakdown = data.get("breakdown") or []
    if not breakdown:
        return []

    top = breakdown[0]
    percent = top.get("percent")
    if percent is None or percent < _CONCENTRATION_EVIDENCE_THRESHOLD:
        return []

    dimension = data.get("dimension")
    measure = data.get("measure")
    return [_evidence(
        "concentration",
        f"{top.get('category')} accounts for {percent:.1f}% of total {measure} by {dimension}",
        percent,
        dimension=dimension,
        measure=measure,
        category=top.get("category"),
    )]


def _anomaly_evidence(anomalies_section):
    if not anomalies_section.get("available"):
        return []

    items = []
    for column, anomalies in (anomalies_section.get("data") or {}).items():
        if isinstance(anomalies, dict):  # {"error": ...} -- skip, not a crash
            continue
        if not anomalies:
            continue
        # Surface the single most extreme anomaly per column -- enough
        # to flag the column as worth attention without flooding
        # evidence with every row over the base z-score threshold.
        strongest = max(anomalies, key=lambda item: abs(item.get("z_score") or 0))
        z_score = strongest.get("z_score")
        if z_score is None or abs(z_score) < _ANOMALY_EVIDENCE_Z_THRESHOLD:
            continue
        items.append(_evidence(
            "anomaly",
            f"Anomalous value in {column} (z-score {z_score})",
            z_score,
            column=column,
            row_id=strongest.get("row_id"),
            observed_value=strongest.get("value"),
            baseline=strongest.get("baseline"),
            anomaly_count=len(anomalies),
        ))
    return items


def _quality_evidence(data_quality_section, dataset_section):
    items = []
    row_count = (dataset_section or {}).get("row_count") or 0
    column_count = (dataset_section or {}).get("column_count") or 0
    total_cells = max(row_count * column_count, 1)

    missing = data_quality_section.get("total_missing_values") or 0
    missing_ratio = missing / total_cells
    if missing_ratio >= _MISSINGNESS_EVIDENCE_RATIO:
        items.append(_evidence(
            "quality",
            f"{missing:,} missing values across the dataset ({missing_ratio * 100:.1f}% of all cells)",
            round(missing_ratio * 100, 2),
            issue="missing_values",
        ))

    duplicates = data_quality_section.get("duplicate_rows") or 0
    duplicate_ratio = duplicates / max(row_count, 1)
    if duplicate_ratio >= _DUPLICATE_EVIDENCE_RATIO:
        items.append(_evidence(
            "quality",
            f"{duplicates:,} duplicate rows detected ({duplicate_ratio * 100:.1f}% of all rows)",
            round(duplicate_ratio * 100, 2),
            issue="duplicate_rows",
        ))

    empty_rows = data_quality_section.get("completely_empty_rows") or 0
    if empty_rows > 0:
        items.append(_evidence(
            "quality",
            f"{empty_rows:,} completely empty rows detected",
            empty_rows,
            issue="empty_rows",
        ))

    return items


def build_evidence(analysis_context):
    """Return a flat list of evidence items derived only from facts
    already present in analysis_context. Never raises: a missing or
    malformed section is simply skipped rather than crashing the
    overall pipeline, since evidence is a bonus layer on top of the
    deterministic analytics, not a replacement for them."""
    if not isinstance(analysis_context, dict):
        return []

    evidence = []
    try:
        evidence.extend(_trend_evidence(analysis_context.get("trends") or {}))
    except Exception:
        pass
    try:
        evidence.extend(_contribution_evidence(analysis_context.get("contribution") or {}))
    except Exception:
        pass
    try:
        evidence.extend(_anomaly_evidence(analysis_context.get("anomalies") or {}))
    except Exception:
        pass
    try:
        evidence.extend(_quality_evidence(
            analysis_context.get("data_quality") or {},
            analysis_context.get("dataset") or {},
        ))
    except Exception:
        pass

    # Stable, deterministic ids -- used by the structured AI layer and
    # the UI to reference a specific evidence item without depending
    # on list position remaining constant across re-renders.
    for index, item in enumerate(evidence):
        item["id"] = f"ev_{index + 1}_{item['type']}"

    return evidence
