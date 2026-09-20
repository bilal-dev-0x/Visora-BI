import math


def _format_number(value):
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.2f}"


def generate_insights(analyzer):
    insights = []
    row_count = len(analyzer.df)
    column_count = len(analyzer.columns)

    insights.append({
        "title": "Dataset size",
        "message": (
            f"The dataset contains {_format_number(row_count)} rows "
            f"across {_format_number(column_count)} columns."
        ),
        "type": "info"
    })

    if analyzer.total_missing_values == 0:
        insights.append({
            "title": "Missing values",
            "message": "No missing values were detected.",
            "type": "success"
        })
    else:
        insights.append({
            "title": "Missing values",
            "message": (
                f"{_format_number(analyzer.total_missing_values)} missing "
                "values were detected."
            ),
            "type": "warning"
        })

    if analyzer.duplicate_rows == 0:
        insights.append({
            "title": "Duplicate rows",
            "message": "No duplicate rows were detected.",
            "type": "success"
        })
    else:
        insights.append({
            "title": "Duplicate rows",
            "message": (
                f"{_format_number(analyzer.duplicate_rows)} duplicate rows "
                "were detected."
            ),
            "type": "warning"
        })

    categorical_distributions = analyzer.get_categorical_distributions()
    for column in analyzer.categorical_columns:
        distribution = categorical_distributions.get(column, [])
        if distribution:
            highest_frequency = distribution[0]
            insights.append({
                "title": "Category highlight",
                "message": (
                    f"{highest_frequency['Category']} is the most frequent "
                    f"value in {column} ({_format_number(highest_frequency['Frequency'])} rows)."
                ),
                "type": "info"
            })
            break

    numeric_statistics = analyzer.get_numeric_statistics()
    for statistics in numeric_statistics:
        mean = statistics["Mean"]
        median = statistics["Median"]
        if math.isfinite(mean) and math.isfinite(median):
            insights.append({
                "title": "Numeric highlight",
                "message": (
                    f"{statistics['Column']} has a mean of {_format_number(mean)} "
                    f"and a median of {_format_number(median)}."
                ),
                "type": "info"
            })
            break

    return insights