from sqlite3 import Connection

import pandas as pd
import streamlit as st

from db import db_conn, get_trail_filter_sql
from ui.charts import create_stacked_bar_chart, prepare_stacked_bar_data


@db_conn
def show(c: Connection, trail: str = "Bass Champs") -> None:
    st.subheader("Average Winning Weight Per Year")

    trail_clause, trail_params = get_trail_filter_sql(trail)
    query = f"""
        SELECT strftime('%Y', t.date) AS year, r.place, ROUND(AVG(r.weight), 2) AS avg_weight
        FROM results r
        JOIN tournaments t ON r.tournament_id = t.id
        WHERE r.place IN (1, 2, 3) AND r.weight IS NOT NULL
        {trail_clause}
        GROUP BY year, place
    """
    df = pd.read_sql(query, c, params=trail_params if trail_params else None)
    if df.empty:
        st.info("No data available for this trail.")
        return

    df = (
        df.pivot(index="year", columns="place", values="avg_weight")
        .fillna(0)
        .reset_index()
    )

    df_chart = prepare_stacked_bar_data(
        df, group_cols=["year"], weight_col="avg_weight", weight_label="avg_weight_lbs"
    )

    chart = create_stacked_bar_chart(
        df_chart,
        x_field="year:N",
        y_field="avg_weight:Q",
        y_title="Avg Weight (lbs)",
        tooltip_fields=[
            ("year:N", "Year"),
            ("place:N", "Place"),
            ("avg_weight_lbs:N", "Avg Weight"),
        ],
    )
    st.altair_chart(chart, use_container_width=True)
