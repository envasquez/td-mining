from sqlite3 import Connection

import altair as alt
import pandas as pd
import streamlit as st

from constants import PLACES
from db import db_conn, get_trail_filter_sql


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
    rows = []
    for _, r in df.iterrows():
        y, lake = r["year"], r["lake"]
        p = {1: r.get(1, 0), 2: r.get(2, 0), 3: r.get(3, 0)}
        base = 0
        for place, emoji in zip([3, 2, 1], PLACES[::-1]):
            height = p[place]
            rows.append(
                {
                    "year": y,
                    "lake": lake,
                    "place": emoji,
                    "weight": height,
                    "label_y": base + height / 2,
                    "label": f"{height:.2f}",
                    "weight_lbs": f"{height:.2f} lbs",
                }
            )
            base += height

    df_label = pd.DataFrame(rows)
    df_label["place"] = pd.Categorical(
        df_label["place"], categories=PLACES, ordered=True
    )

    years = sorted(df_label["year"].unique(), reverse=True)
    tabs = st.tabs(years)
    for idx, year in enumerate(years):
        with tabs[idx]:
            df_year = df_label[df_label["year"] == year]
            bars = (
                alt.Chart(df_year)
                .mark_bar()
                .encode(
                    x=alt.X(
                        "lake:N",
                        title="Lake",
                        sort="-y",
                        axis=alt.Axis(
                            labelFontSize=10, labelLimit=0, labelFontStyle="bold"
                        ),
                    ),
                    y=alt.Y("weight:Q", title="Weight(lbs)", stack="zero"),
                    color=alt.Color(
                        "place:N",
                        sort=PLACES,
                        scale=alt.Scale(scheme="blues"),
                        title="Place",
                    ),
                    tooltip=[
                        alt.Tooltip("lake:N", title="Lake"),
                        alt.Tooltip("place:N", title="Place"),
                        alt.Tooltip("weight_lbs:N", title="Weight"),
                    ],
                ).properties(height=500)
            )
            labels = (
                alt.Chart(df_year)
                .mark_text(
                    align="center",
                    baseline="middle",
                    color="white",
                    fontSize=11,
                    fontStyle="bold",
                    tooltip=None,
                )
                .encode(x="lake:N", y="label_y:Q", text="label:N").properties(height=500)
            )
            st.altair_chart(
                (bars + labels).properties(height=500), use_container_width=True
            )
