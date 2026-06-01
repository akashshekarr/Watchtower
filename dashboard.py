"""
dashboard.py  —  run with:  streamlit run dashboard.py

Reads per-key usage pulled by fetch_usage.py (table: daily_usage).
Dark "observability console" theme.
"""

import sqlite3
import json
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from collections import defaultdict
from key_names import label_for

DB_PATH = "usage.db"
CONFIG_PATH = "config.json"


def load_config():
    import os
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def detect_spikes(cfg=None):
    """Return keys whose latest-day cost >> their prior average."""
    cfg = cfg or load_config()
    sd = cfg.get("spike_detection", {})
    if not sd.get("enabled", True):
        return []
    lookback = int(sd.get("lookback_days", 7))
    mult = float(sd.get("multiplier", 3.0))

    con = sqlite3.connect(DB_PATH)
    try:
        rows = con.execute("""
            SELECT provider, key_id, day, SUM(cost_usd) c
            FROM daily_usage GROUP BY provider, key_id, day
            ORDER BY provider, key_id, day
        """).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()

    series = defaultdict(list)
    for prov, key, day, c in rows:
        series[(prov, key)].append((day, float(c)))

    spikes = []
    for (prov, key), pts in series.items():
        if len(pts) < 3:
            continue
        pts.sort()
        _, latest_cost = pts[-1]
        prior = [c for _, c in pts[-(lookback + 1):-1]]
        if not prior:
            continue
        avg = sum(prior) / len(prior)
        if avg > 0 and latest_cost > mult * avg and latest_cost > 1.0:
            spikes.append({
                "provider": prov, "key_id": key, "day": pts[-1][0],
                "latest_cost": latest_cost, "avg_cost": avg,
                "ratio": latest_cost / avg,
            })
    spikes.sort(key=lambda x: x["ratio"], reverse=True)
    return spikes

st.set_page_config(page_title="LLM API Usage", layout="wide",
                   initial_sidebar_state="collapsed", page_icon="◆")

# --------------------------------------------------------------------------
# Theme / palette
# --------------------------------------------------------------------------
BG      = "#0d1117"
PANEL   = "#161b22"
PANEL2  = "#1c2330"
BORDER  = "#283041"
TEXT    = "#e6edf3"
MUTED   = "#8b949e"
ACCENT  = "#5eead4"   # teal
ACCENT2 = "#a78bfa"   # violet
GOOD    = "#56d364"
WARN    = "#e3b341"
PROVIDER_COLORS = {"openai": "#5eead4", "anthropic": "#f0883e"}

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap');

.stApp {{ background:
    radial-gradient(1200px 600px at 15% -10%, #14202e 0%, transparent 55%),
    radial-gradient(1000px 500px at 100% 0%, #1a1530 0%, transparent 50%),
    {BG}; color:{TEXT}; }}
.block-container {{ padding-top:2.2rem; max-width:1400px; }}

html, body, [class*="css"] {{ font-family:'Sora',sans-serif; }}

/* ---- Header ---- */
.hero {{ display:flex; align-items:baseline; gap:.7rem; margin-bottom:.1rem; }}
.hero h1 {{ font-size:2.1rem; font-weight:800; letter-spacing:-.02em; margin:0;
    background:linear-gradient(92deg,{TEXT} 30%,{ACCENT} 120%);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent; }}
.hero .dot {{ width:11px; height:11px; border-radius:50%;
    background:{ACCENT}; box-shadow:0 0 14px 2px {ACCENT}; align-self:center; }}
.sub {{ color:{MUTED}; font-size:.9rem; margin:.1rem 0 1.4rem; }}
.sub code {{ font-family:'JetBrains Mono',monospace; color:{ACCENT};
    background:{PANEL2}; padding:.05rem .4rem; border-radius:5px; font-size:.82rem; }}

/* ---- Metric cards ---- */
.metric-row {{ display:grid; grid-template-columns:repeat(4,1fr); gap:1rem; margin:.4rem 0 1.6rem; }}
.metric {{ position:relative; background:linear-gradient(160deg,{PANEL} 0%,{PANEL2} 100%);
    border:1px solid {BORDER}; border-radius:16px; padding:1.15rem 1.25rem; overflow:hidden; }}
.metric::before {{ content:""; position:absolute; inset:0 auto auto 0; width:100%; height:3px;
    background:linear-gradient(90deg,{ACCENT},{ACCENT2}); opacity:.9; }}
.metric .label {{ color:{MUTED}; font-size:.72rem; text-transform:uppercase;
    letter-spacing:.12em; font-weight:600; }}
.metric .value {{ font-family:'JetBrains Mono',monospace; font-size:1.85rem; font-weight:700;
    color:{TEXT}; margin-top:.35rem; line-height:1; }}
.metric .value.accent {{ color:{ACCENT}; }}
.metric .foot {{ color:{MUTED}; font-size:.74rem; margin-top:.45rem; }}

/* ---- Section titles ---- */
.sect {{ font-size:.82rem; text-transform:uppercase; letter-spacing:.14em;
    color:{ACCENT}; font-weight:700; margin:1.6rem 0 .7rem;
    display:flex; align-items:center; gap:.5rem; }}
.sect::after {{ content:""; flex:1; height:1px;
    background:linear-gradient(90deg,{BORDER},transparent); }}

/* ---- Filter labels ---- */
.stMultiSelect label, .stDateInput label {{ color:{MUTED}!important;
    font-size:.72rem!important; text-transform:uppercase; letter-spacing:.1em; font-weight:600; }}
[data-baseweb="tag"] {{ background:{ACCENT}!important; color:#06231f!important;
    border-radius:6px!important; font-weight:600!important; }}
[data-baseweb="select"]>div, .stDateInput input {{ background:{PANEL}!important;
    border-color:{BORDER}!important; border-radius:10px!important; color:{TEXT}!important; }}

/* ---- Dataframe ---- */
[data-testid="stDataFrame"] {{ border:1px solid {BORDER}; border-radius:14px; overflow:hidden; }}
[data-testid="stDataFrame"] * {{ font-family:'JetBrains Mono',monospace!important; }}
[data-testid="stDataFrame"] thead tr th {{
    background:{PANEL2}!important; color:{ACCENT}!important;
    text-transform:uppercase; font-size:.68rem!important; letter-spacing:.08em;
    font-family:'Sora',sans-serif!important; border-bottom:1px solid {BORDER}!important; }}
[data-testid="stDataFrame"] tbody tr:hover {{ background:{PANEL2}!important; }}

#MainMenu, header, footer {{ visibility:hidden; }}
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------
@st.cache_data(ttl=60)
def load():
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS daily_usage (
        day TEXT, provider TEXT, key_id TEXT, key_label TEXT, model TEXT,
        input_tokens INTEGER, output_tokens INTEGER, cost_usd REAL)""")
    con.commit()
    df = pd.read_sql_query("SELECT * FROM daily_usage", con, parse_dates=["day"])
    con.close()
    if not df.empty:
        df["name"] = df["key_id"].map(label_for)
        df["total_tokens"] = df["input_tokens"] + df["output_tokens"]
    return df


def fmt_money(v):
    return f"${v:,.2f}"

def fmt_compact(n):
    n = float(n)
    for unit, div in [("B", 1e9), ("M", 1e6), ("K", 1e3)]:
        if abs(n) >= div:
            return f"{n/div:.2f}{unit}"
    return f"{int(n)}"


df = load()

st.markdown('<div class="hero"><span class="dot"></span>'
            '<h1>LLM API Usage</h1></div>', unsafe_allow_html=True)
st.markdown('<div class="sub">Per-key cost &amp; tokens across OpenAI and Anthropic. '
            'Refresh with <code>python fetch_usage.py</code></div>', unsafe_allow_html=True)

if df.empty:
    st.info("No data yet. Run:  python fetch_usage.py")
    st.stop()

# --------------------------------------------------------------------------
# Filters
# --------------------------------------------------------------------------
c1, c2, c3 = st.columns([1.1, 1.1, 2])
providers = c1.multiselect("Provider", sorted(df.provider.unique()),
                           default=sorted(df.provider.unique()))
dmin, dmax = df.day.min().date(), df.day.max().date()
dr = c2.date_input("Date range", (dmin, dmax))
names = c3.multiselect("API key (blank = all)", sorted(df.name.unique()), default=[])

mask = df.provider.isin(providers)
if names:
    mask &= df.name.isin(names)
if isinstance(dr, tuple) and len(dr) == 2:
    mask &= (df.day.dt.date >= dr[0]) & (df.day.dt.date <= dr[1])
f = df[mask]

if f.empty:
    st.warning("No rows match these filters.")
    st.stop()

# --------------------------------------------------------------------------
# Metric cards
# --------------------------------------------------------------------------
total_cost = f.cost_usd.sum()
total_tok = f.total_tokens.sum()
n_keys = f[f.total_tokens > 0].name.nunique()
n_models = f[f.model != "_cost_only"].model.nunique()
days_span = max((f.day.max() - f.day.min()).days, 1)
avg_day = total_cost / days_span

st.markdown(f"""
<div class="metric-row">
  <div class="metric"><div class="label">Total Cost</div>
    <div class="value accent">{fmt_money(total_cost)}</div>
    <div class="foot">≈ {fmt_money(avg_day)} / day</div></div>
  <div class="metric"><div class="label">Total Tokens</div>
    <div class="value">{fmt_compact(total_tok)}</div>
    <div class="foot">{int(total_tok):,} exact</div></div>
  <div class="metric"><div class="label">Active Keys</div>
    <div class="value">{n_keys}</div>
    <div class="foot">with usage in range</div></div>
  <div class="metric"><div class="label">Models</div>
    <div class="value">{n_models}</div>
    <div class="foot">distinct models called</div></div>
</div>
""", unsafe_allow_html=True)

# --------------------------------------------------------------------------
# Plotly theming helper
# --------------------------------------------------------------------------
def style_fig(fig, h=320):
    fig.update_layout(
        height=h, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Sora, sans-serif", color=TEXT, size=12),
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=MUTED)),
        xaxis=dict(gridcolor=BORDER, zerolinecolor=BORDER),
        yaxis=dict(gridcolor=BORDER, zerolinecolor=BORDER),
        hoverlabel=dict(bgcolor=PANEL2, font_size=12,
                        font_family="JetBrains Mono, monospace"))
    return fig

# --------------------------------------------------------------------------
# Daily trend (area, stacked by provider)
# --------------------------------------------------------------------------
st.markdown('<div class="sect">Daily Spend</div>', unsafe_allow_html=True)
ftrend = f.copy()
ftrend["d"] = ftrend["day"].dt.date
trend = ftrend.groupby(["d", "provider"], as_index=False).cost_usd.sum()

def _rgba(hex_color, a):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{a})"

fig = go.Figure()
for prov in sorted(trend.provider.unique()):
    sub = trend[trend.provider == prov]
    col = PROVIDER_COLORS.get(prov, ACCENT)
    fig.add_trace(go.Scatter(
        x=sub["d"], y=sub["cost_usd"], name=prov, mode="lines",
        stackgroup="one", line=dict(width=2, color=col),
        fillcolor=_rgba(col, 0.18)))
fig.update_traces(hovertemplate="%{y:$,.2f}<extra>%{fullData.name}</extra>")
style_fig(fig, 300)
st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# --------------------------------------------------------------------------
# Two columns: provider donut + top keys bar
# --------------------------------------------------------------------------
left, right = st.columns([1, 1.4])

with left:
    st.markdown('<div class="sect">Cost by Provider</div>', unsafe_allow_html=True)
    pv = f.groupby("provider").cost_usd.sum().reset_index()
    fig = go.Figure(go.Pie(
        labels=pv.provider, values=pv.cost_usd, hole=.62,
        marker=dict(colors=[PROVIDER_COLORS.get(p, ACCENT) for p in pv.provider],
                    line=dict(color=BG, width=3)),
        textinfo="percent", textfont=dict(color=BG, size=13, family="Sora")))
    fig.update_traces(hovertemplate="%{label}: %{value:$,.2f}<extra></extra>")
    fig.add_annotation(text=f"<b>{fmt_money(total_cost)}</b>", showarrow=False,
                       font=dict(size=18, color=TEXT, family="JetBrains Mono"))
    style_fig(fig, 300)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

with right:
    st.markdown('<div class="sect">Top 12 Keys by Cost</div>', unsafe_allow_html=True)
    top = (f.groupby(["name", "provider"]).cost_usd.sum()
           .reset_index().sort_values("cost_usd", ascending=True).tail(12))
    fig = go.Figure(go.Bar(
        x=top.cost_usd, y=top.name, orientation="h",
        marker=dict(color=[PROVIDER_COLORS.get(p, ACCENT) for p in top.provider],
                    line=dict(width=0)),
        hovertemplate="%{y}: %{x:$,.2f}<extra></extra>"))
    fig.update_layout(yaxis=dict(tickfont=dict(size=10, family="JetBrains Mono")))
    style_fig(fig, 320)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# --------------------------------------------------------------------------
# Per-key table
# --------------------------------------------------------------------------
st.markdown('<div class="sect">Per-Key Detail</div>', unsafe_allow_html=True)
per_key = (f.groupby(["provider", "name"])
           .agg(cost_usd=("cost_usd", "sum"),
                input_tokens=("input_tokens", "sum"),
                output_tokens=("output_tokens", "sum"))
           .reset_index().sort_values("cost_usd", ascending=False))
st.dataframe(
    per_key, use_container_width=True, hide_index=True, height=380,
    column_config={
        "provider": st.column_config.TextColumn("Provider"),
        "name": st.column_config.TextColumn("API Key", width="large"),
        "cost_usd": st.column_config.NumberColumn("Cost", format="$%.2f"),
        "input_tokens": st.column_config.NumberColumn("Input", format="%d"),
        "output_tokens": st.column_config.NumberColumn("Output", format="%d"),
    })

# --------------------------------------------------------------------------
# Per-model table
# --------------------------------------------------------------------------
st.markdown('<div class="sect">By Model</div>', unsafe_allow_html=True)
per_model = (f[f.model != "_cost_only"].groupby(["provider", "model"])
             .agg(cost_usd=("cost_usd", "sum"),
                  total_tokens=("total_tokens", "sum"))
             .reset_index().sort_values("cost_usd", ascending=False))
st.dataframe(
    per_model, use_container_width=True, hide_index=True,
    column_config={
        "provider": st.column_config.TextColumn("Provider"),
        "model": st.column_config.TextColumn("Model", width="large"),
        "cost_usd": st.column_config.NumberColumn("Cost", format="$%.2f"),
        "total_tokens": st.column_config.NumberColumn("Tokens", format="%d"),
    })

# --------------------------------------------------------------------------
# Cost spikes
# --------------------------------------------------------------------------
spikes = detect_spikes()
if spikes:
    st.markdown('<div class="sect">⚡ Cost Spikes Detected</div>', unsafe_allow_html=True)
    sdf = pd.DataFrame(spikes)
    sdf["name"] = sdf["key_id"].map(label_for)
    sdf = sdf[["provider", "name", "day", "avg_cost", "latest_cost", "ratio"]]
    st.dataframe(
        sdf, use_container_width=True, hide_index=True,
        column_config={
            "provider": st.column_config.TextColumn("Provider"),
            "name": st.column_config.TextColumn("API Key", width="large"),
            "day": st.column_config.TextColumn("Spike day"),
            "avg_cost": st.column_config.NumberColumn("Prior avg/day", format="$%.2f"),
            "latest_cost": st.column_config.NumberColumn("Latest day", format="$%.2f"),
            "ratio": st.column_config.NumberColumn("× normal", format="%.1fx"),
        })

# --------------------------------------------------------------------------
# Idle / unused keys (zero usage in the selected range)
# --------------------------------------------------------------------------
st.markdown('<div class="sect">Idle Keys (no usage in range)</div>', unsafe_allow_html=True)
used_keys = set(f[f.total_tokens > 0].key_id.unique())
all_keys = df[["provider", "key_id"]].drop_duplicates()
idle = all_keys[~all_keys.key_id.isin(used_keys)].copy()
if idle.empty:
    st.caption("None — every known key had usage in this range.")
else:
    idle["name"] = idle["key_id"].map(label_for)
    idle = idle[["provider", "name", "key_id"]].sort_values("provider")
    st.caption(f"{len(idle)} key(s) with zero usage in the selected range — possible cleanup candidates.")
    st.dataframe(
        idle, use_container_width=True, hide_index=True,
        column_config={
            "provider": st.column_config.TextColumn("Provider"),
            "name": st.column_config.TextColumn("API Key", width="large"),
            "key_id": st.column_config.TextColumn("Key ID"),
        })

# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------
st.markdown('<div class="sect">Export</div>', unsafe_allow_html=True)

def to_excel_bytes(frames: dict):
    import io
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        for sheet, frm in frames.items():
            frm.to_excel(xl, sheet_name=sheet[:31], index=False)
    return buf.getvalue()

e1, e2, e3 = st.columns(3)
e1.download_button(
    "⬇ Per-key (CSV)", per_key.to_csv(index=False).encode(),
    "per_key_usage.csv", "text/csv", use_container_width=True)
e2.download_button(
    "⬇ Per-model (CSV)", per_model.to_csv(index=False).encode(),
    "per_model_usage.csv", "text/csv", use_container_width=True)
try:
    xls = to_excel_bytes({"per_key": per_key, "per_model": per_model,
                          "raw_filtered": f.drop(columns=["name"], errors="ignore")})
    e3.download_button(
        "⬇ Everything (Excel)", xls, "api_usage.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True)
except Exception:
    e3.caption("Excel export needs `pip install openpyxl`")