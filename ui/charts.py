"""Shared chart utilities for tournament data visualization."""

import altair as alt
import pandas as pd

from constants import PLACES


def prepare_stacked_bar_data(
    df: pd.DataFrame,
    group_cols: list[str],
    weight_col: str = "weight",
    weight_label: str = "weight_lbs",
) -> pd.DataFrame:
    """
    Prepare data for a stacked bar chart showing 1st/2nd/3rd place weights.

    Args:
        df: DataFrame with columns for place (1, 2, 3) after pivoting
        group_cols: Columns to use as grouping keys (e.g., ["year"] or ["year", "lake"])
        weight_col: Name for the weight column in output
        weight_label: Name for the formatted weight label column

    Returns:
        DataFrame ready for stacked bar chart with place emojis and label positions
    """
    rows = []
    for _, r in df.iterrows():
        group_values = {col: r[col] for col in group_cols}
        p = {1: r.get(1, 0), 2: r.get(2, 0), 3: r.get(3, 0)}
        base = 0
        for place, emoji in zip([3, 2, 1], PLACES[::-1]):
            height = p[place]
            row = {
                **group_values,
                "place": emoji,
                weight_col: height,
                "label_y": base + height / 2,
                "label": f"{height:.2f}",
                weight_label: f"{height:.2f} lbs",
            }
            rows.append(row)
            base += height

    df_label = pd.DataFrame(rows)
    df_label["place"] = pd.Categorical(
        df_label["place"], categories=PLACES, ordered=True
    )
    return df_label


def create_stacked_bar_chart(
    df: pd.DataFrame,
    x_field: str,
    y_field: str,
    y_title: str,
    tooltip_fields: list[tuple[str, str]],
    x_title: str | None = None,
    height: int | None = None,
    x_sort: str | None = None,
) -> alt.LayerChart:
    """
    Create a stacked bar chart with embedded labels for 1st/2nd/3rd place.

    Args:
        df: DataFrame prepared by prepare_stacked_bar_data()
        x_field: Field name for x-axis (e.g., "year:N" or "lake:N")
        y_field: Field name for y-axis weight (e.g., "weight:Q" or "avg_weight:Q")
        y_title: Title for y-axis
        tooltip_fields: List of (field, title) tuples for tooltips
        x_title: Optional title for x-axis
        height: Optional chart height
        x_sort: Optional sort order for x-axis (e.g., "-y" for descending by y)

    Returns:
        Altair LayerChart with bars and labels
    """
    x_encoding = alt.X(
        x_field,
        title=x_title,
        sort=x_sort,
        axis=alt.Axis(labelFontSize=10, labelLimit=0, labelFontStyle="bold"),
    )

    bars = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=x_encoding,
            y=alt.Y(y_field, title=y_title, stack="zero"),
            color=alt.Color(
                "place:N",
                sort=PLACES,
                scale=alt.Scale(scheme="blues"),
                title="Place",
            ),
            tooltip=[
                alt.Tooltip(field, title=title) for field, title in tooltip_fields
            ],
        )
    )

    labels = (
        alt.Chart(df)
        .mark_text(
            align="center",
            baseline="middle",
            color="white",
            fontSize=11,
            fontStyle="bold",
            tooltip=None,
        )
        .encode(
            x=alt.X(x_field, sort=x_sort),
            y="label_y:Q",
            text="label:N",
        )
    )

    chart = bars + labels
    if height:
        chart = chart.properties(height=height)
    return chart
