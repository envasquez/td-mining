from sqlite3 import Connection

import altair as alt
import pandas as pd
import streamlit as st

from constants import TEXT_COLOR
from db import db_conn, get_trail_filter_sql


@db_conn
def show(c: Connection, trail: str = "Bass Champs"):
    st.subheader("Average Winning Weight & Frequency per Lake")

    trail_clause, trail_params = get_trail_filter_sql(trail)
    query = f"""
        SELECT
            t.lake,
            COUNT(DISTINCT t.id) AS tournament_count,
            ROUND(AVG(r.weight), 2) AS avg_winning_weight
        FROM tournaments t
        JOIN results r ON t.id = r.tournament_id
        WHERE r.place = 1 AND t.lake IS NOT NULL AND r.weight IS NOT NULL
        {trail_clause}
        GROUP BY t.lake
    """
    df = pd.read_sql(query, c, params=trail_params if trail_params else None)
    if df.empty:
        st.info("No data available for this trail.")
        return
    df = df.sort_values("avg_winning_weight", ascending=False).reset_index(drop=True)
    df["lake"] = pd.Categorical(df["lake"], categories=df["lake"], ordered=True)
    max_count = df["tournament_count"].max()
    base = alt.Chart(df).encode(
        x=alt.X(
            "lake:N",
            title="Lake",
            sort=None,
            axis=alt.Axis(labelFontSize=10, labelLimit=0, labelFontStyle="bold"),
        )
    )
    bars = base.mark_bar(color="steelblue").encode(
        y=alt.Y(
            "avg_winning_weight:Q", axis=alt.Axis(title="Avg Winning Weight (lbs)")
        ),
        tooltip=["lake", "avg_winning_weight", "tournament_count"],
    )
    line = base.mark_line(interpolate="monotone", color="orange", strokeWidth=2).encode(
        y=alt.Y(
            "tournament_count:Q",
            axis=alt.Axis(title="Tournament Count", orient="right"),
            scale=alt.Scale(domain=(1, max_count + 1)),
        ),
        tooltip=["lake", "avg_winning_weight", "tournament_count"],
    )
    text = base.mark_text(
        align="center",
        baseline="bottom",
        dy=-5,
        color=TEXT_COLOR,
        fontSize=12,
        fontStyle="bold",
    ).encode(
        y=alt.Y("avg_winning_weight:Q", axis=alt.Axis(title=None)),
        text=alt.Text("avg_winning_weight:Q", format=".2f"),
    )
    chart = (
        alt.layer(bars, line, text)
        .resolve_scale(y="independent")
        .properties(height=500)
    )
    st.altair_chart(chart, width="stretch")
