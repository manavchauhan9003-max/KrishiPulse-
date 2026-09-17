"""
KrishiPulse — Agri-Mandi Price Anomaly Radar (Gujarat)
Phase 4: Streamlit Dashboard

Tabs:
  1. Overview        - headline metrics + per-crop summary
  2. Price Trends     - wholesale vs retail line chart over time
  3. District Heat-Map - Gujarat choropleth of avg wedge_pct
  4. Anomaly Table    - flagged wholesale/retail anomalies
"""

import re
import warnings
from datetime import date, timedelta

import pandas as pd
import psycopg2
import requests
import streamlit as st

try:
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

# pandas complains that psycopg2 connections aren't SQLAlchemy connectables — harmless here.
warnings.filterwarnings("ignore", message=".*pandas only supports SQLAlchemy.*")

st.set_page_config(page_title="KrishiPulse", page_icon="🌾", layout="wide")

CROPS = ["Onion", "Potato", "Tomato", "Garlic", "Green Chilli"]

# NOTE: the GeoJSON URL originally specified for this project
# (datameet/maps/master/Districts/gujarat.geojson) returns 404 — that path doesn't exist in the
# repo. Using a verified, working Gujarat district-boundary GeoJSON with equivalent coverage.
# If the original source comes back online, just swap this URL back in.
GEOJSON_URL = "https://raw.githubusercontent.com/udit-001/india-maps-data/main/geojson/states/gujarat.geojson"
GEOJSON_DISTRICT_KEY = "district"  # property in the GeoJSON holding the district name

# Agmarknet district strings that don't exactly match the GeoJSON's official district names
DISTRICT_NAME_FIXES = {
    "Banaskanth": "Banaskantha",
    "Junagarh": "Junagadh",
    "Chhota Udepur": "Chhota Udaipur",
    "Devbhoomi Dwarka": "Devbhumi Dwarka",
    "Kachchh": "Kutch",
    "Vadodara(Baroda)": "Vadodara",
}


def normalize_district(name):
    """Align Agmarknet district strings with the GeoJSON's official district names."""
    if not name:
        return name
    name = re.sub(r"\s*\(.*?\)", "", name).strip()  # "Vadodara(Baroda)" -> "Vadodara"
    return DISTRICT_NAME_FIXES.get(name, name)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_connection():
    return psycopg2.connect(st.secrets["DATABASE_URL"])


@st.cache_data(ttl=3600)
def run_query(query, params=None):
    """Run a SQL query against Neon and return a DataFrame. Cached for 1 hour."""
    try:
        conn = get_connection()
        try:
            df = pd.read_sql_query(query, conn, params=params)
        finally:
            conn.close()
        return df
    except Exception as e:
        st.error(f"Database error: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def get_date_bounds():
    """min = earliest price_date in wholesale_price, max = today."""
    df = run_query("SELECT MIN(price_date) AS min_date FROM wholesale_price")
    today = date.today()
    if df.empty or pd.isna(df.loc[0, "min_date"]):
        return today - timedelta(days=1), today
    min_date = pd.to_datetime(df.loc[0, "min_date"]).date()
    if min_date >= today:
        min_date = today - timedelta(days=1)
    return min_date, today


@st.cache_data(ttl=3600)
def get_overview_metrics(crops, start_date, end_date):
    records_df = run_query(
        """
        SELECT COUNT(*) AS n
        FROM wholesale_price w
        JOIN crop_master c ON w.crop_id = c.crop_id
        WHERE w.is_provisional = false
          AND c.crop_name IN %(crops)s
          AND w.price_date BETWEEN %(start)s AND %(end)s
        """,
        params={"crops": crops, "start": start_date, "end": end_date},
    )
    anomalies_df = run_query(
        """
        SELECT COUNT(*) AS n
        FROM price_anomaly a
        JOIN crop_master c ON a.crop_id = c.crop_id
        WHERE a.anomaly_flag = true
          AND c.crop_name IN %(crops)s
          AND a.price_date BETWEEN %(start)s AND %(end)s
        """,
        params={"crops": crops, "start": start_date, "end": end_date},
    )
    # Pipeline-level stats — not scoped to the sidebar filters
    districts_df = run_query(
        "SELECT COUNT(DISTINCT district) AS n FROM mandi_master WHERE district IS NOT NULL"
    )
    days_df = run_query(
        "SELECT (MAX(price_date) - MIN(price_date)) AS n FROM wholesale_price"
    )

    def first_int(df):
        if df.empty or pd.isna(df.loc[0, "n"]):
            return 0
        return int(df.loc[0, "n"])

    return {
        "wholesale_records": first_int(records_df),
        "districts": first_int(districts_df),
        "anomalies": first_int(anomalies_df),
        "days": first_int(days_df),
    }


@st.cache_data(ttl=3600)
def get_crop_summary(crops, start_date, end_date):
    return run_query(
        """
        SELECT c.crop_name AS "Crop",
               COUNT(*) AS "Records",
               MIN(w.modal_price) AS "Min Price",
               MAX(w.modal_price) AS "Max Price",
               AVG(w.modal_price) AS "Avg Price"
        FROM wholesale_price w
        JOIN crop_master c ON w.crop_id = c.crop_id
        WHERE w.is_provisional = false
          AND c.crop_name IN %(crops)s
          AND w.price_date BETWEEN %(start)s AND %(end)s
        GROUP BY c.crop_name
        ORDER BY c.crop_name
        """,
        params={"crops": crops, "start": start_date, "end": end_date},
    )


@st.cache_data(ttl=3600)
def get_wholesale_trend(crops, start_date, end_date):
    return run_query(
        """
        SELECT c.crop_name AS crop, w.price_date AS price_date,
               AVG(w.modal_price) AS modal_price
        FROM wholesale_price w
        JOIN crop_master c ON w.crop_id = c.crop_id
        WHERE w.is_provisional = false
          AND c.crop_name IN %(crops)s
          AND w.price_date BETWEEN %(start)s AND %(end)s
        GROUP BY c.crop_name, w.price_date
        ORDER BY w.price_date
        """,
        params={"crops": crops, "start": start_date, "end": end_date},
    )


@st.cache_data(ttl=3600)
def get_retail_trend(crops, start_date, end_date):
    return run_query(
        """
        SELECT c.crop_name AS crop, r.price_date AS price_date, r.price AS price
        FROM retail_price r
        JOIN crop_master c ON r.crop_id = c.crop_id
        WHERE r.city = 'Ahmedabad'
          AND r.data_type = 'scraped'
          AND c.crop_name IN %(crops)s
          AND r.price_date BETWEEN %(start)s AND %(end)s
        ORDER BY r.price_date
        """,
        params={"crops": crops, "start": start_date, "end": end_date},
    )


@st.cache_data(ttl=3600)
def get_district_wedge(crops, start_date, end_date):
    return run_query(
        """
        SELECT a.district AS district,
               AVG(a.wedge_pct) AS avg_wedge_pct,
               COUNT(*) AS n_rows
        FROM price_anomaly a
        JOIN crop_master c ON a.crop_id = c.crop_id
        WHERE a.district IS NOT NULL
          AND c.crop_name IN %(crops)s
          AND a.price_date BETWEEN %(start)s AND %(end)s
        GROUP BY a.district
        ORDER BY avg_wedge_pct DESC
        """,
        params={"crops": crops, "start": start_date, "end": end_date},
    )


@st.cache_data(ttl=3600)
def load_geojson():
    try:
        resp = requests.get(GEOJSON_URL, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


@st.cache_data(ttl=3600)
def get_anomalies(crops, start_date, end_date):
    return run_query(
        """
        SELECT c.crop_name AS "Crop",
               a.price_date AS "Date",
               a.district AS "District",
               a.wholesale_price AS "Wholesale Price",
               a.wholesale_baseline AS "30-Day Baseline",
               a.wholesale_zscore AS "Wholesale Z-Score",
               a.retail_price AS "Retail Price",
               a.retail_zscore AS "Retail Z-Score",
               a.wedge_pct AS "Retail Premium %%",
               a.anomaly_flag AS "anomaly_flag"
        FROM price_anomaly a
        JOIN crop_master c ON a.crop_id = c.crop_id
        WHERE a.anomaly_flag = true
          AND c.crop_name IN %(crops)s
          AND a.price_date BETWEEN %(start)s AND %(end)s
        ORDER BY ABS(a.wholesale_zscore) DESC NULLS LAST
        """,
        params={"crops": crops, "start": start_date, "end": end_date},
    )


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def currency_fmt(v):
    return f"₹{v:,.2f}" if pd.notna(v) else "—"


def number_fmt(v):
    return f"{v:.2f}" if pd.notna(v) else "—"


def pct_fmt(v):
    return f"{v:.2f}%" if pd.notna(v) else "—"


# ---------------------------------------------------------------------------
# Sidebar (global filters)
# ---------------------------------------------------------------------------

st.title("🌾 KrishiPulse")
st.caption("Agri-Mandi Price Anomaly Radar — Gujarat")

min_date, max_date = get_date_bounds()

with st.sidebar:
    st.header("Filters")
    selected_crops = st.multiselect("Crops", options=CROPS, default=CROPS)
    date_range = st.slider(
        "Date range",
        min_value=min_date,
        max_value=max_date,
        value=(min_date, max_date),
        format="DD MMM YYYY",
    )

start_date, end_date = date_range
crops_for_query = tuple(selected_crops) if selected_crops else ("__none__",)

if not selected_crops:
    st.sidebar.warning("Select at least one crop to see data.")

tab1, tab2, tab3, tab4 = st.tabs(
    ["📊 Overview", "📈 Price Trends", "🗺️ District Heat-Map", "🚨 Anomaly Table"]
)

# ---------------------------------------------------------------------------
# Tab 1 — Overview
# ---------------------------------------------------------------------------

with tab1:
    metrics = get_overview_metrics(crops_for_query, start_date, end_date)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Wholesale Records (non-provisional)", f"{metrics['wholesale_records']:,}")
    c2.metric("Districts Covered", metrics["districts"])
    c3.metric("Anomalies Flagged", metrics["anomalies"])
    c4.metric("Days of Data Accumulated", metrics["days"])

    st.divider()
    st.subheader("Crop Summary")

    summary_df = get_crop_summary(crops_for_query, start_date, end_date)
    if summary_df.empty:
        st.info("No wholesale data for the selected filters.")
    else:
        display_df = summary_df.copy()
        for col in ["Min Price", "Max Price", "Avg Price"]:
            display_df[col] = display_df[col].apply(currency_fmt)
        st.dataframe(display_df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Tab 2 — Price Trends
# ---------------------------------------------------------------------------

with tab2:
    st.subheader("Wholesale vs Retail Price Trends")

    wholesale_df = get_wholesale_trend(crops_for_query, start_date, end_date)
    retail_df = get_retail_trend(crops_for_query, start_date, end_date)

    if wholesale_df.empty:
        st.info("No wholesale data for the selected filters.")
    elif PLOTLY_AVAILABLE:
        fig = px.line(
            wholesale_df,
            x="price_date",
            y="modal_price",
            color="crop",
            labels={"price_date": "Date", "modal_price": "Modal Price (₹/kg)", "crop": "Crop"},
            title="Wholesale Modal Price Over Time (avg across Gujarat mandis)",
        )
        fig.update_traces(mode="lines")

        if not retail_df.empty:
            for crop_name, group in retail_df.groupby("crop"):
                fig.add_scatter(
                    x=group["price_date"],
                    y=group["price"],
                    mode="lines",
                    name=f"{crop_name} (Retail, Ahmedabad)",
                    line=dict(dash="dash"),
                )

        fig.update_layout(legend_title_text="", hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)
    else:
        chart_df = wholesale_df.pivot(index="price_date", columns="crop", values="modal_price")
        st.line_chart(chart_df)

    st.caption(
        "Wholesale prices averaged across all Gujarat mandis for selected date range. "
        "Retail prices from Blinkit Ahmedabad."
    )

# ---------------------------------------------------------------------------
# Tab 3 — District Heat-Map
# ---------------------------------------------------------------------------

with tab3:
    st.subheader("District Wedge Heat-Map")

    wedge_df = get_district_wedge(crops_for_query, start_date, end_date)
    geojson = load_geojson()

    if geojson is None:
        st.warning("Map unavailable — GeoJSON could not be loaded")
    elif wedge_df.empty:
        st.info("No anomaly data for the selected filters.")
    elif not PLOTLY_AVAILABLE:
        st.warning("Plotly not installed — cannot render choropleth map.")
    else:
        map_df = wedge_df.copy()
        map_df["district_norm"] = map_df["district"].apply(normalize_district)
        map_df = map_df.groupby("district_norm", as_index=False)["avg_wedge_pct"].mean()

        fig = px.choropleth_mapbox(
            map_df,
            geojson=geojson,
            locations="district_norm",
            featureidkey=f"properties.{GEOJSON_DISTRICT_KEY}",
            color="avg_wedge_pct",
            color_continuous_scale=["green", "yellow", "red"],
            mapbox_style="carto-positron",
            zoom=6.1,
            center={"lat": 22.65, "lon": 71.8},
            opacity=0.75,
            labels={"avg_wedge_pct": "Avg Wedge %"},
        )
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Top 5 Districts by Avg Retail Premium (Wedge %)")
    if wedge_df.empty:
        st.info("No data to show.")
    else:
        top5 = wedge_df.sort_values("avg_wedge_pct", ascending=False).head(5).copy()
        top5["avg_wedge_pct"] = top5["avg_wedge_pct"].apply(pct_fmt)
        top5 = top5.rename(
            columns={"district": "District", "avg_wedge_pct": "Avg Wedge %", "n_rows": "Records"}
        )
        st.dataframe(top5[["District", "Avg Wedge %", "Records"]], use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Tab 4 — Anomaly Table
# ---------------------------------------------------------------------------

with tab4:
    st.subheader("Flagged Anomalies")

    anomalies_df = get_anomalies(crops_for_query, start_date, end_date)

    if anomalies_df.empty:
        st.info("No flagged anomalies for the selected filters.")
    else:
        df = anomalies_df.copy()
        df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
        df["Status"] = df["anomaly_flag"].apply(lambda v: "🚨 Flagged" if v else "")
        df = df.drop(columns=["anomaly_flag"])
        df = df.rename(
            columns={
                "Wholesale Price": "Wholesale Price (₹/kg)",
                "Retail Price": "Retail Price (₹/kg)",
            }
        )

        def color_zscore(v):
            if pd.isna(v):
                return ""
            return "color: red; font-weight: 600;" if v < 0 else "color: orange; font-weight: 600;"

        format_map = {
            "Wholesale Price (₹/kg)": currency_fmt,
            "30-Day Baseline": currency_fmt,
            "Retail Price (₹/kg)": currency_fmt,
            "Wholesale Z-Score": number_fmt,
            "Retail Z-Score": number_fmt,
            "Retail Premium %": pct_fmt,
        }

        styled = df.style.map(color_zscore, subset=["Wholesale Z-Score"]).format(format_map)
        st.dataframe(styled, use_container_width=True, hide_index=True)

    st.caption(
        "Showing anomalies where wholesale z-score > 2 stddev from 30-day rolling baseline. "
        "Retail prices from Blinkit Ahmedabad (scraped) or calibrated model."
    )