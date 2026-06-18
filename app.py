import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np

from sankey_function import build_animated_sankey, build_sankey, get_sector

@st.cache_resource
def load_data():
    df = pd.read_parquet("data.parquet")
    get_sector(df)

    for stat in ["Min", "Median", "Max"]:
        df[f"elem_mass_{stat}"] = np.where(
            df["Unit"].str.contains("%"),
            df["technology amounts"] * df[stat] / 100 * 1e6,
            df["technology amounts"] * df[stat]
        )
    return df


df=load_data()

@st.cache_data
def get_filtered(_df, element, country, scenario):
    return _df[
        (_df["Element"]  == element) &
        (_df["country"]  == country) &
        (_df["scenario"] == scenario)
    ].copy()
    

st.title("🔁 Elemental Flow in MSW Sankey Dashboard")
st.caption("Trace chemical elements within MSW fractions from generation through treatment technologies.")



with st.sidebar:
    country     = st.selectbox("Country",  sorted(df["country"].unique()))
    scenario    = st.selectbox("Scenario", sorted(df["scenario"].unique()))
    element     = st.selectbox("Element",  sorted(df["Element"].dropna().unique()))
    year        = st.select_slider("Year", options=sorted(df["year"].unique()))
    stat        = st.radio("Composition",  ["Min", "Median", "Max"], index=1)
    value_mode  = st.radio("Flow values",  ["mass", "pct"],
                           format_func=lambda x: "Element mass (t)" if x == "mass" else "Percentage (%)")
    sector_mode = st.radio("Sector layout", ["within", "separate"],
                           format_func=lambda x: "Within fractions" if x == "within" else "Separate nodes")

sub = get_filtered(df, element, country, scenario)

fig = build_sankey(sub, element=element, year=int(year),
                   country=country, scenario=scenario,
                   stat=stat, value_mode=value_mode, sector_mode=sector_mode)

st.plotly_chart(fig, use_container_width=True)