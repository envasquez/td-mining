from sqlite3 import Connection

import pandas as pd
import streamlit as st

from db import db_conn, get_trail_filter_sql, load_query


@db_conn
def show(c: Connection, trail: str = "Bass Champs") -> None:
    st.subheader("Top 20 Teams by Tournament")

    trail_clause, trail_params = get_trail_filter_sql(trail)
    query = f"""
        SELECT id, tournament, date
        FROM tournaments
        WHERE 1=1 {trail_clause}
        ORDER BY date DESC
    """
    tournaments_df = pd.read_sql(
        query, c, params=trail_params if trail_params else None
    )
    if tournaments_df.empty:
        st.info("No tournaments available for this trail.")
        return
    tournaments_df["year"] = pd.to_datetime(tournaments_df["date"]).dt.year
    years = sorted(tournaments_df["year"].unique(), reverse=True)
    tab_objs = st.tabs([str(year) for year in years])
    for idx, year in enumerate(years):
        with tab_objs[idx]:
            tournaments_in_year = tournaments_df[tournaments_df["year"] == year].copy()
            tournaments_in_year["label"] = (
                tournaments_in_year["tournament"]
                + " ("
                + tournaments_in_year["date"]
                + ")"
            )
            tournament_map = dict(
                zip(tournaments_in_year["label"], tournaments_in_year["id"])
            )
            selected_label = st.selectbox(
                "Select a Tournament",
                list(tournament_map.keys()),
                key=f"select_{trail}_{year}",
            )
            selected_id = tournament_map[selected_label]
            results_df = pd.read_sql(
                load_query(filename="queries/top_twenty.sql"), c, params=(selected_id,)
            )
            st.subheader("Top 20 Results")
            column_config = {
                "place": st.column_config.NumberColumn("Place", width="small"),
                "angler": st.column_config.TextColumn("Angler", width="medium"),
                "weight": st.column_config.NumberColumn("Weight(lbs)", width="small"),
                "big_bass": st.column_config.NumberColumn(
                    "BigBass (lbs)", width="small"
                ),
                "prize": st.column_config.TextColumn("Prize", width="large"),
            }
            st.data_editor(
                results_df,
                column_config=column_config,
                width="stretch",
                hide_index=True,
                disabled=True,
                key=f"top20_{trail}_{year}_{selected_id}",
            )
