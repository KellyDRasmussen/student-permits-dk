import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from pathlib import Path
from countries import DIMENSIONS, get_group

ANNUAL_PATH  = Path(__file__).parent / "data" / "van66_raw.csv"
MONTHLY_PATH = Path(__file__).parent / "data" / "van77m_raw.csv"

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

def _month_label(code):
    year, m = code.split("M")
    return f"{MONTH_NAMES[int(m)-1]} '{year[2:]}"

ANNUAL_PERIODS = ["2021", "2022", "2023"]

def _monthly_codes_from_csv():
    try:
        tids = pd.read_csv(MONTHLY_PATH, usecols=["TID"])["TID"].dropna().unique()
        return sorted(t for t in tids if isinstance(t, str) and "M" in t)
    except Exception:
        return [f"2024M{m:02d}" for m in range(1, 13)]

MONTHLY_CODES  = _monthly_codes_from_csv()
MONTHLY_LABELS = {c: _month_label(c) for c in MONTHLY_CODES}
PERIOD_ORDER   = ANNUAL_PERIODS + [MONTHLY_LABELS[c] for c in MONTHLY_CODES]
BREAK_AT       = len(ANNUAL_PERIODS) - 0.5
_years_present = sorted({c[:4] for c in MONTHLY_CODES})
JAN_TICKS      = [MONTHLY_LABELS[f"{y}M01"] for y in _years_present if f"{y}M01" in MONTHLY_LABELS]
LABELED_TICKS  = ANNUAL_PERIODS + JAN_TICKS

EDUCATION_ONLY = "Study etc., education"
OKABE_ITO      = ["#E69F00", "#56B4E9", "#009E73", "#0072B2", "#D55E00", "#CC79A7", "#F0E442", "#000000"]
AGG_COLORS     = ["#0072B2", "#D55E00"]

st.set_page_config(layout="wide", page_title="Student permits — Denmark")


# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data
def load_raw():
    return pd.read_csv(ANNUAL_PATH), pd.read_csv(MONTHLY_PATH)


@st.cache_data
def build_dataset(_annual_raw, _monthly_raw, education_only):
    annual_raw  = _annual_raw.copy()
    monthly_raw = _monthly_raw.copy()
    if education_only:
        annual_raw  = annual_raw[annual_raw["OPHOLD"]  == EDUCATION_ONLY]
        monthly_raw = monthly_raw[monthly_raw["OPHOLD"] == EDUCATION_ONLY]

    annual = (
        annual_raw.groupby(["STATSB", "TID"])["INDHOLD"].sum()
        .reset_index()
        .rename(columns={"STATSB": "country", "TID": "year", "INDHOLD": "permits"})
    )
    annual["period"]      = annual["year"].astype(str)
    annual["period_type"] = "annual"

    monthly = (
        monthly_raw.groupby(["STATSB", "TID"])["INDHOLD"].sum()
        .reset_index()
        .rename(columns={"STATSB": "country", "TID": "month_code", "INDHOLD": "permits"})
    )
    monthly["period"]      = monthly["month_code"].map(MONTHLY_LABELS)
    monthly["period_type"] = "monthly"

    combined = pd.concat(
        [annual[["country", "period", "period_type", "permits"]],
         monthly[["country", "period", "period_type", "permits"]]],
        ignore_index=True,
    )
    combined["period"] = pd.Categorical(
        combined["period"], categories=PERIOD_ORDER, ordered=True
    )
    for dim in DIMENSIONS:
        col = dim.split(" / ")[0].lower().replace(" ", "_")
        combined[col] = combined["country"].apply(lambda c: get_group(c, dim))
    return combined


def compute_y_max(df):
    individual_max = df["permits"].max()
    agg_max = max(
        df.groupby([dim.split(" / ")[0].lower().replace(" ", "_"), "period"],
                   observed=True)["permits"].sum().max()
        for dim in DIMENSIONS
    )
    return float(max(individual_max, agg_max)) * 1.08


def build_selection_table(df):
    """Jan–May comparison table derived from the already-built dataset."""
    monthly = df[df["period_type"] == "monthly"].copy()
    monthly["month_num"] = monthly["period"].astype(str).apply(
        lambda p: MONTH_NAMES.index(p.split(" ")[0]) + 1
    )
    monthly["yr"] = monthly["period"].astype(str).apply(
        lambda p: "'24" if "'24" in p else ("'25" if "'25" in p else "'26")
    )
    ytd = (
        monthly[monthly["month_num"] <= 5]
        .groupby(["country", "yr"], observed=True)["permits"].sum()
        .unstack("yr").fillna(0).astype(int)
        .reindex(columns=["'24", "'25", "'26"], fill_value=0)
        .rename(columns={"'24": "Jan–May '24", "'25": "Jan–May '25", "'26": "Jan–May '26"})
    )
    with_data = ytd[ytd[["Jan–May '24", "Jan–May '25", "Jan–May '26"]].sum(axis=1) > 0].copy()
    prev = with_data["Jan–May '25"].astype(float)
    change = (with_data["Jan–May '26"] - with_data["Jan–May '25"]).astype(float)
    pct = (change / prev.where(prev > 0, 1.0) * 100).where(prev > 0, 0.0)
    with_data["Δ '25→'26"] = pct.round(0).astype(int).astype(str) + "%"
    sorted_data = with_data.sort_values("Jan–May '25", ascending=False)

    t24 = int(sorted_data["Jan–May '24"].sum())
    t25 = int(sorted_data["Jan–May '25"].sum())
    t26 = int(sorted_data["Jan–May '26"].sum())
    t_pct = round((t26 - t25) / t25 * 100) if t25 > 0 else 0
    total = pd.DataFrame(
        [{"Jan–May '24": t24, "Jan–May '25": t25, "Jan–May '26": t26, "Δ '25→'26": f"{t_pct}%"}],
        index=["Total"],
    )
    return pd.concat([sorted_data, total])


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("Student permits")
    _monthly_range = f"{MONTHLY_LABELS[MONTHLY_CODES[0]]} – {MONTHLY_LABELS[MONTHLY_CODES[-1]]}" if MONTHLY_CODES else "—"
    st.caption(f"VAN66 annual 2021–2023  ·  VAN77M monthly {_monthly_range}")

    if not all(p.exists() for p in (ANNUAL_PATH, MONTHLY_PATH)):
        st.error("Run `python fetch_data.py` first.")
        st.stop()

    if st.button("↻ Reload data"):
        st.cache_data.clear()
        st.rerun()

    st.divider()

    permit_type = st.radio(
        "Permit type",
        options=["All study types", "Education only"],
        index=0,
        horizontal=True,
        help=(
            "**Education only** matches the ministry's 'ca. 50' in the June 2026 press release."
        ),
    )
    education_only = permit_type == "Education only"

    st.divider()

    dim_options = ["Show all"] + list(DIMENSIONS.keys())
    dimension = st.selectbox(
        "Group countries by",
        options=dim_options,
        index=dim_options.index("Western / Non-Western"),
    )

    if dimension != "Show all":
        label_in, label_out, _ = DIMENSIONS[dimension]
        side = st.radio(
            "Show",
            options=[label_in, label_out, "Both"],
            index=2,
            horizontal=True,
        )
    else:
        side = "Both"

    aggregate_mode = dimension != "Show all" and side == "Both"

    st.divider()

    if not aggregate_mode:
        min_permits = st.slider(
            "Min permits in best annual year",
            min_value=0, max_value=500, value=50, step=10,
        )
    else:
        min_permits = 0
        st.caption("Showing group totals — individual threshold not applied.")


# ── Load data ─────────────────────────────────────────────────────────────────

try:
    annual_raw, monthly_raw = load_raw()
except FileNotFoundError:
    st.error("Run `python fetch_data.py` first.")
    st.stop()

df_all = build_dataset(annual_raw, monthly_raw, education_only)
y_max  = compute_y_max(df_all)

if "selected_countries" not in st.session_state:
    st.session_state.selected_countries = []
selected_countries = [c for c in st.session_state.selected_countries
                      if c in df_all["country"].values]

# Apply group / threshold filters for the group view
df = df_all.copy()
if dimension != "Show all" and not aggregate_mode:
    col = dimension.split(" / ")[0].lower().replace(" ", "_")
    if side == label_in:
        df = df[df[col] == label_in]
    elif side == label_out:
        df = df[df[col] == label_out]

if not aggregate_mode and min_permits > 0:
    peak = df[df["period_type"] == "annual"].groupby("country")["permits"].max()
    df = df[df["country"].isin(peak[peak >= min_permits].index)]

df_table = df_all.copy()
if dimension != "Show all" and not aggregate_mode:
    _tcol = dimension.split(" / ")[0].lower().replace(" ", "_")
    df_table = df_table[df_table[_tcol] == side]
if not aggregate_mode and min_permits > 0:
    _peak = df_table[df_table["period_type"] == "annual"].groupby("country")["permits"].max()
    df_table = df_table[df_table["country"].isin(_peak[_peak >= min_permits].index)]
sel_table = build_selection_table(df_table)

# Drop any prior selections that are no longer visible in the current table view.
selected_countries = [c for c in selected_countries if c in sel_table.index]
compare_mode = len(selected_countries) > 0


# ── Metrics ───────────────────────────────────────────────────────────────────

def _range_metric(col_widget, label, df_periods):
    def _val(p):
        row = df_periods[df_periods["period"].astype(str) == p]["permits"]
        return int(row.sum()) if len(row) else 0
    jan24, may26 = _val("Jan '24"), _val("May '26")
    col_widget.metric(
        f"{label}: Jan '24 → May '26",
        f"{jan24:,} → {may26:,}",
        delta=f"{may26 - jan24:+,}",
        delta_color="inverse",
    )

dynamic_metrics = []
if compare_mode:
    for country in selected_countries[:3]:
        dynamic_metrics.append((country, df_all[df_all["country"] == country]))
elif dimension != "Show all":
    dim_col = dimension.split(" / ")[0].lower().replace(" ", "_")
    group_totals = (
        df_all.groupby([dim_col, "period"], observed=True)["permits"].sum()
        .reset_index().rename(columns={dim_col: "grp"})
    )
    if aggregate_mode:
        for grp in [label_in, label_out]:
            dynamic_metrics.append((grp, group_totals[group_totals["grp"] == grp]))
    else:
        dynamic_metrics.append((side, group_totals[group_totals["grp"] == side]))

metric_cols = st.columns(max(2, 1 + len(dynamic_metrics)))
metric_cols[0].metric("Permit type", "Education only" if education_only else "All study types")
for i, (label, df_m) in enumerate(dynamic_metrics):
    _range_metric(metric_cols[i + 1], label, df_m)

st.divider()


# ── Chart (full width) ────────────────────────────────────────────────────────

fig = go.Figure()

# Background shading + break line
fig.add_shape(
    type="rect", x0=BREAK_AT, x1=len(PERIOD_ORDER) - 0.5, y0=0, y1=1,
    xref="x", yref="paper", fillcolor="rgba(210,225,255,0.2)",
    line=dict(width=0), layer="below",
)
fig.add_shape(
    type="line", x0=BREAK_AT, x1=BREAK_AT, y0=0, y1=1,
    xref="x", yref="paper",
    line=dict(color="rgba(80,80,80,0.35)", width=1.5, dash="dash"),
)
_may25_label = MONTHLY_LABELS.get("2025M05")
_may25_idx   = PERIOD_ORDER.index(_may25_label) if _may25_label and _may25_label in PERIOD_ORDER else None
if _may25_idx is not None:
    fig.add_shape(
        type="line", x0=_may25_idx, x1=_may25_idx, y0=0, y1=1,
        xref="x", yref="paper",
        line=dict(color="rgba(120,40,40,0.18)", width=1, dash="dot"),
        layer="below",
    )
    fig.add_annotation(
        x=_may25_idx + 0.3, y=0.97, xref="x", yref="paper",
        text="policy tightening", showarrow=False,
        font=dict(size=8, color="rgba(120,40,40,0.35)"),
        xanchor="left", yanchor="top", textangle=-90,
    )

fig.add_annotation(
    x=1, y=1.06, xref="x", yref="paper",
    text="← Annual", showarrow=False, font=dict(size=11, color="#888"), xanchor="center",
)
fig.add_annotation(
    x=BREAK_AT + 14, y=1.06, xref="x", yref="paper",
    text="Monthly →", showarrow=False, font=dict(size=11, color="#888"), xanchor="center",
)
for jan_label in JAN_TICKS:
    idx = PERIOD_ORDER.index(jan_label)
    fig.add_shape(
        type="line", x0=idx, x1=idx, y0=0, y1=1, xref="x", yref="paper",
        line=dict(color="rgba(150,150,150,0.2)", width=1), layer="below",
    )

if compare_mode:
    # ── Up to 5 selected countries, individually labelled ─────────────────
    for i, country in enumerate(selected_countries):
        cdf = df_all[df_all["country"] == country].sort_values("period")
        if cdf.empty:
            continue
        color = OKABE_ITO[i % len(OKABE_ITO)]
        texts = [""] * len(cdf)
        texts[-1] = country
        fig.add_trace(go.Scatter(
            x=cdf["period"].astype(str),
            y=cdf["permits"],
            mode="lines+markers+text",
            name=country,
            text=texts,
            textposition="middle right",
            textfont=dict(size=11, color=color),
            line=dict(color=color, width=2.5),
            marker=dict(size=5),
            showlegend=False,
            hovertemplate=f"<b>{country}</b><br>%{{x}}: %{{y:,}}<extra></extra>",
        ))

elif aggregate_mode:
    # ── Two group-total lines ─────────────────────────────────────────────
    dim_col = dimension.split(" / ")[0].lower().replace(" ", "_")
    group_agg = (
        df_all.groupby([dim_col, "period"], observed=True)["permits"].sum()
        .reset_index().rename(columns={dim_col: "grp"})
    )
    group_agg["period"] = pd.Categorical(
        group_agg["period"], categories=PERIOD_ORDER, ordered=True
    )
    for i, grp_label in enumerate([label_in, label_out]):
        gdf = group_agg[group_agg["grp"] == grp_label].sort_values("period")
        if gdf.empty:
            continue
        color = AGG_COLORS[i]
        texts = [""] * len(gdf)
        texts[-1] = grp_label
        fig.add_trace(go.Scatter(
            x=gdf["period"].astype(str),
            y=gdf["permits"],
            mode="lines+text",
            name=grp_label,
            text=texts,
            textposition="middle right",
            textfont=dict(size=12, color=color),
            line=dict(color=color, width=2.5),
            showlegend=False,
            hovertemplate=f"<b>{grp_label}</b><br>%{{x}}: %{{y:,}}<extra></extra>",
        ))

else:
    # ── Individual country lines (group/threshold view) ───────────────────
    palette = px.colors.qualitative.Safe
    for i, country in enumerate(sorted(df["country"].unique())):
        cdf = df[df["country"] == country].sort_values("period")
        fig.add_trace(go.Scatter(
            x=cdf["period"].astype(str),
            y=cdf["permits"],
            mode="lines",
            name=country,
            line=dict(color=palette[i % len(palette)], width=1.5),
            opacity=0.7,
            showlegend=False,
            hovertemplate=f"<b>{country}</b><br>%{{x}}: %{{y:,}}<extra></extra>",
        ))

fig.update_layout(
    height=560,
    xaxis=dict(
        title=None,
        categoryorder="array",
        categoryarray=PERIOD_ORDER,
        tickmode="array",
        tickvals=LABELED_TICKS,
        ticktext=LABELED_TICKS,
        tickangle=45,
        tickfont=dict(color="#444"),
        automargin=True,
    ),
    yaxis=dict(
        title=dict(text="Study permits issued", font=dict(color="#444")),
        tickfont=dict(color="#444"),
        range=[0, y_max] if not compare_mode else None,
    ),
    hovermode="closest",
    showlegend=False,
    margin=dict(l=0, r=110, t=45, b=55),
    plot_bgcolor="white",
    paper_bgcolor="white",
)
fig.update_xaxes(showgrid=False)
fig.update_yaxes(gridcolor="#eeeeee")

st.plotly_chart(fig, use_container_width=True)

# ── Country selector (below chart) ───────────────────────────────────────────

st.caption("Select up to 5 countries to compare — overrides the group view. Deselect all to go back.")

if compare_mode:
    swatches = "&emsp;".join(
        f'<span style="color:{OKABE_ITO[i % len(OKABE_ITO)]};font-size:1.2em">■</span> {c}'
        for i, c in enumerate(selected_countries)
    )
    st.markdown(swatches, unsafe_allow_html=True)
elif aggregate_mode:
    swatches = "&emsp;".join(
        f'<span style="color:{AGG_COLORS[j]};font-size:1.2em">■</span> {lbl}'
        for j, lbl in enumerate([label_in, label_out])
    )
    st.markdown(swatches, unsafe_allow_html=True)

event = st.dataframe(
    sel_table,
    use_container_width=True,
    height=320,
    on_select="rerun",
    selection_mode="multi-row",
)
raw_rows   = event.selection.rows
valid_rows = [i for i in raw_rows if i < len(sel_table)]
new_selection = [sel_table.index[i] for i in valid_rows if sel_table.index[i] != "Total"][:5]
if len(raw_rows) > 5:
    st.caption("⚠️ Only the first 5 plotted.")

if new_selection != st.session_state.selected_countries:
    st.session_state.selected_countries = new_selection
    st.rerun()
