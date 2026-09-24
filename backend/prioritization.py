"""
Deterministic prioritization (Day 4).

prioritize_evidence() assigns a Critical/High/Medium/Low priority to
each evidence item produced by backend/evidence.py, using only the
measurable analytical signal already carried on that item (a z-score,
a growth percent, a concentration percent, a missingness ratio, ...).

AI explains evidence; it never decides priority. This module is the
single place that maps a raw signal strength to an importance level,
so priority stays consistent, explainable, and reproducible for the
same input every time -- no dataset/column name (e.g. "Sales") is
ever treated as inherently important.
"""

_PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _priority_for_anomaly(item):
    z_score = abs(item.get("value") or 0)
    if z_score >= 4:
        return "critical"
    if z_score >= 3:
        return "high"
    if z_score >= 2:
        return "medium"
    return "low"


def _priority_for_trend(item):
    magnitude = abs(item.get("value") or 0)
    if magnitude >= 50:
        return "critical"
    if magnitude >= 25:
        return "high"
    if magnitude >= 10:
        return "medium"
    return "low"


def _priority_for_concentration(item):
    percent = item.get("value") or 0
    if percent >= 80:
        return "critical"
    if percent >= 60:
        return "high"
    if percent >= 40:
        return "medium"
    return "low"


def _priority_for_quality(item):
    issue = item.get("issue")
    magnitude = item.get("value") or 0
    if issue == "missing_values":
        if magnitude >= 50:
            return "critical"
        if magnitude >= 30:
            return "high"
        if magnitude >= 10:
            return "medium"
        return "low"
    if issue == "duplicate_rows":
        if magnitude >= 50:
            return "critical"
        if magnitude >= 30:
            return "high"
        if magnitude >= 10:
            return "medium"
        return "low"
    # empty_rows and any future issue kinds carry a raw count, not a
    # ratio -- treat any nonzero count as at least worth medium
    # attention, without a magnitude-based escalation that would
    # require guessing a "large" dataset size.
    return "medium" if magnitude else "low"


_PRIORITY_FUNCS = {
    "anomaly": _priority_for_anomaly,
    "trend": _priority_for_trend,
    "concentration": _priority_for_concentration,
    "quality": _priority_for_quality,
}


def _base_priority(item):
    func = _PRIORITY_FUNCS.get(item.get("type"))
    if func is None:
        return "low"
    try:
        priority = func(item)
    except Exception:
        return "low"
    return priority if priority in _PRIORITY_ORDER else "low"


def _bump(priority):
    """One level more severe, capped at 'critical'."""
    order = ["critical", "high", "medium", "low"]
    index = order.index(priority)
    return order[max(index - 1, 0)]


def prioritize_evidence(evidence):
    """Return a new list of evidence items, each carrying a
    "priority" field, sorted from Critical to Low (stable within a
    tier, preserving the relative order evidence.py produced them
    in). Never raises: an item whose type/value can't be scored
    safely just falls back to "low" rather than crashing the
    pipeline."""
    if not evidence:
        return []

    scored = []
    for item in evidence:
        prioritized = dict(item)
        prioritized["priority"] = _base_priority(item)
        scored.append(prioritized)

    # "Multiple strong signals" escalation: when two or more High-or-
    # above items share the same subject (column/dimension/category),
    # that combination is itself a stronger signal than any one item
    # alone -- bump the strongest of them one level, capped at
    # Critical. This never turns a Low/Medium item Critical on its
    # own; it only escalates when corroborating strong evidence
    # exists for the same subject.
    def _subject(item):
        return item.get("column") or item.get("dimension") or item.get("category")

    strong_by_subject = {}
    for item in scored:
        subject = _subject(item)
        if subject is None or item["priority"] not in ("critical", "high"):
            continue
        strong_by_subject.setdefault(subject, []).append(item)

    for subject, items in strong_by_subject.items():
        if len(items) < 2:
            continue
        strongest = min(items, key=lambda item: _PRIORITY_ORDER[item["priority"]])
        strongest["priority"] = _bump(strongest["priority"])

    scored.sort(key=lambda item: _PRIORITY_ORDER.get(item["priority"], 3))
    return scored
