from sqlite3 import Connection

import altair as alt
import pandas as pd
import streamlit as st

from constants import PLACES, TEXT_COLOR
from db import db_conn, get_trail_filter_sql


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
    rows = []
    for _, r in df.iterrows():
        y, p = r["year"], {1: r.get(1, 0), 2: r.get(2, 0), 3: r.get(3, 0)}
        base = 0
        for place, emoji in zip([3, 2, 1], PLACES[::-1]):
            height = p[place]
            rows.append(
                {
                    "year": y,
                    "place": emoji,
                    "avg_weight": height,
                    "label_y": base + height / 2,
                    "label": f"{height:.2f}",
                    "avg_weight_lbs": f"{height:.2f} lbs",
                }
            )
            base += height

    df_label = pd.DataFrame(rows)
    bars = (
        alt.Chart(df_label)
        .mark_bar()
        .encode(
            x="year:N",
            y=alt.Y("avg_weight:Q", title="Avg Weight (lbs)", stack="zero"),
            color=alt.Color(
                "place:N",
                sort=PLACES,
                scale=alt.Scale(scheme="blues"),
                title="Placement",
            ),
            tooltip=[
                alt.Tooltip("year:N", title="Year"),
                alt.Tooltip("place:N", title="Place"),
                alt.Tooltip("avg_weight_lbs:N", title="Avg Weight"),
            ],
        )
    )
    labels = (
        alt.Chart(df_label)
        .mark_text(
            align="center",
            baseline="middle",
            color="white",
            fontSize=11,
            fontStyle="bold",
            tooltip=None,
        )
        .encode(x="year:N", y="label_y:Q", text="label:N")
    )
    st.altair_chart(bars + labels, use_container_width=True)
