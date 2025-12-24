from sqlite3 import Connection

import pandas as pd
import streamlit as st

from db import db_conn, get_trail_filter_sql
from ui.charts import create_stacked_bar_chart, prepare_stacked_bar_data


@db_conn
def show(c: Connection, trail: str = "Bass Champs") -> None:
    st.subheader("Winning Weights by Lake per Year")

    trail_clause, trail_params = get_trail_filter_sql(trail)
    query = f"""
        SELECT
            strftime('%Y', t.date) AS year,
            t.lake,
            r.place,
            r.weight
        FROM tournaments t
        JOIN results r ON t.id = r.tournament_id
        WHERE r.place IN (1, 2, 3)
          AND r.weight IS NOT NULL
          AND t.lake IS NOT NULL
          {trail_clause}
        GROUP BY year, t.lake, r.place
        ORDER BY year DESC, t.lake, r.place
    """
    df = pd.read_sql(query, c, params=trail_params if trail_params else None)
    if df.empty:
        st.info("No data available for this trail.")
        return

    df = (
        df.pivot(index=["year", "lake"], columns="place", values="weight")
        .fillna(0)
        .reset_index()
    )

    df_chart = prepare_stacked_bar_data(
        df, group_cols=["year", "lake"], weight_col="weight", weight_label="weight_lbs"
    )

    years = sorted(df_chart["year"].unique(), reverse=True)
    tabs = st.tabs(years)
    for idx, year in enumerate(years):
        with tabs[idx]:
            df_year = df_chart[df_chart["year"] == year]
            chart = create_stacked_bar_chart(
                df_year,
                x_field="lake:N",
                y_field="weight:Q",
                y_title="Weight (lbs)",
                tooltip_fields=[
                    ("lake:N", "Lake"),
                    ("place:N", "Place"),
                    ("weight_lbs:N", "Weight"),
                ],
                x_title="Lake",
                x_sort="-y",
                height=500,
            )
            st.altair_chart(chart, use_container_width=True)
