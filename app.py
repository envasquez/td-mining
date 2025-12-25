import streamlit as st

from ui import (
    angler_perf,
    avg_winning_wt,
    avg_winning_wt_lake,
    top_twenty,
    winning_wt_lake,
)


def render_trail_sections(trail: str) -> None:
    """Render all data sections for a given trail."""
    avg_winning_wt.show(trail=trail)
    avg_winning_wt_lake.show(trail=trail)
    winning_wt_lake.show(trail=trail)
    top_twenty.show(trail=trail)
    angler_perf.show(trail=trail)


def main():
    st.set_page_config(layout="wide")
    st.title("Tournament Data Dashboard")

    tabs = st.tabs([
        "Bass Champs",
        "TTZ Team Trail",
        "TTO Team Trail",
        "MediaBass Teams",
        "MediaBass Individuals",
    ])

    with tabs[0]:
        st.header("Bass Champs Tournament Trail")
        render_trail_sections("Bass Champs")

    with tabs[1]:
        st.header("TTZ Team Trail")
        render_trail_sections("TTZ Team Trail")

    with tabs[2]:
        st.header("TTO Team Trail")
        render_trail_sections("TTO Team Trail")

    with tabs[3]:
        st.header("MediaBass Teams")
        render_trail_sections("MediaBass Teams")

    with tabs[4]:
        st.header("MediaBass Individuals")
        render_trail_sections("MediaBass")


if __name__ == "__main__":
    main()
