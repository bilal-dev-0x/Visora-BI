"""
Chart type selection support.

The dashboard exposes a Chart Type dropdown (Bar/Line/Pie/Scatter).
This module holds the small, pure, data-aware logic for which chart
types make sense for a given selection of columns, and what a
sensible default choice is -- so the dashboard can show a clear
message instead of crashing when a chosen chart type doesn't fit the
selected columns, and never has to duplicate this reasoning inline.

No charting/rendering happens here -- backend/charting concerns stay
exactly where they already are (frontend/dashboard.py using Plotly);
this module only answers "is (chart_type, x, y) a valid combination
for this schema?" and "what would a good default be?".
"""

CHART_TYPES = ("Bar", "Line", "Pie", "Scatter")


def suggest_default_chart_type(date_columns, categorical_columns, numeric_columns):
    """A reasonable default, in the same spirit as this module's
    examples: a date+measure pair suggests Line, a category+measure
    pair suggests Bar, otherwise fall back to whatever is possible."""
    if date_columns and numeric_columns:
        return "Line"
    if categorical_columns and numeric_columns:
        return "Bar"
    if len(numeric_columns) >= 2:
        return "Scatter"
    return "Bar"


def is_chart_type_supported(chart_type, date_columns, categorical_columns, numeric_columns):
    """Whether `chart_type` has ANY valid column combination for this
    schema at all (used to decide whether to even offer/enable it)."""
    date_columns = date_columns or []
    categorical_columns = categorical_columns or []
    numeric_columns = numeric_columns or []

    if chart_type == "Line":
        return bool(date_columns) and bool(numeric_columns)
    if chart_type == "Bar":
        return bool(categorical_columns) and bool(numeric_columns)
    if chart_type == "Pie":
        return bool(categorical_columns) and bool(numeric_columns)
    if chart_type == "Scatter":
        return len(numeric_columns) >= 2
    return False


def validate_chart_selection(chart_type, numeric_columns_selected=0, has_category=False, has_date=False):
    """Return (supported, reason) for one concrete selection the user
    made in the dropdown (already-chosen columns), so the dashboard
    can show a clear message instead of forcing an invalid chart type
    onto incompatible data. Never raises."""
    if chart_type not in CHART_TYPES:
        return False, f"Unknown chart type '{chart_type}'."

    if chart_type == "Line":
        if not has_date:
            return False, "Line charts need a date/time column, which this dataset doesn't have."
        if numeric_columns_selected < 1:
            return False, "Line charts need at least one numeric measure to plot over time."
        return True, None

    if chart_type == "Bar":
        if not has_category:
            return False, "Bar charts need a categorical column, which this dataset doesn't have."
        if numeric_columns_selected < 1:
            return False, "Bar charts need at least one numeric measure to aggregate per category."
        return True, None

    if chart_type == "Pie":
        if not has_category:
            return False, "Pie charts need a categorical column to break the whole into parts."
        if numeric_columns_selected < 1:
            return False, "Pie charts need a numeric measure to size each slice."
        return True, None

    if chart_type == "Scatter":
        if numeric_columns_selected < 2:
            return False, "Scatter charts need two numeric columns (X and Y)."
        return True, None

    return False, "Unsupported chart type."
