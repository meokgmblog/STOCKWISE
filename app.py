import gzip
import io
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st

# ================================================================
# CONFIGURATION & PAGE SETUP
# ================================================================
st.set_page_config(
    page_title="F&O Live Position Builder",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Modern UI Styling Injection with Fixed Padding & High-Contrast Fonts
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');

    /* Global Theme & Font Enhancements */
    .stApp {
        background: radial-gradient(circle at top right, #131722 0%, #0e1117 60%);
        color: #f0f6fc;
        font-family: 'Plus Jakarta Sans', sans-serif;
        animation: fadeInPage 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    }

    /* Eliminate excess top white space and streamline container padding */
    .block-container {
        padding-top: 1.2rem !important;
        padding-bottom: 2rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
    }

    header[data-testid="stHeader"] {
        background: transparent !important;
    }

    @keyframes fadeInPage {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }

    @keyframes pulseGlow {
        0% { box-shadow: 0 0 10px rgba(8, 153, 129, 0.15); }
        50% { box-shadow: 0 0 25px rgba(8, 153, 129, 0.4); }
        100% { box-shadow: 0 0 10px rgba(8, 153, 129, 0.15); }
    }

    /* Native Streamlit Metric Cards Customization */
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, rgba(22, 27, 34, 0.9) 0%, rgba(31, 36, 44, 0.9) 100%);
        border: 1px solid rgba(48, 54, 61, 0.8);
        border-radius: 14px;
        padding: 18px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        backdrop-filter: blur(10px);
        transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
        animation: fadeInPage 0.6s ease-out;
    }
    
    [data-testid="stMetric"]:hover {
        transform: translateY(-4px) scale(1.01);
        border-color: #089981;
        box-shadow: 0 12px 30px rgba(8, 153, 129, 0.25);
    }

    [data-testid="stMetricLabel"] {
        font-size: 0.82rem !important;
        color: #c9d1d9 !important;
        text-transform: uppercase;
        font-weight: 700;
        letter-spacing: 0.08em;
    }
    
    [data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
        font-weight: 800;
        background: linear-gradient(90deg, #f0f6fc, #c9d1d9);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }

    /* Sidebar Customization & High Contrast Text Fixes */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #131722 0%, #0b0e14 100%);
        border-right: 1px solid rgba(42, 46, 57, 0.8);
        box-shadow: 5px 0 25px rgba(0, 0, 0, 0.5);
    }
    
    section[data-testid="stSidebar"] .block-container {
        padding-top: 2rem !important;
    }

    section[data-testid="stSidebar"] p, 
    section[data-testid="stSidebar"] span, 
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] div,
    .stSelectbox label, 
    .stSlider label {
        color: #f0f6fc !important;
        font-weight: 600 !important;
    }

    /* Headers */
    h1, h2, h3 {
        color: #f0f6fc;
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-weight: 800;
        letter-spacing: -0.02em;
    }

    /* Interactive Elements & Buttons Styling */
    .stButton>button {
        background: linear-gradient(135deg, #089981 0%, #066c5b 100%);
        color: white;
        border-radius: 8px;
        border: none;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(8, 153, 129, 0.4);
    }
</style>
""", unsafe_allow_html=True)

IST = ZoneInfo("Asia/Kolkata")
MARKET_START = "09:00"
MARKET_END = "15:45"
INTERVAL = 3

ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI2M0FZSEUiLCJqdGkiOiI2YThkNTc1Y2Y4MTJmNjA0MzcxZDNlM2MiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6ZmFsc2UsImlhdCI6MTc4NzY0NzgzNiwiaXNzIjoidWRhcGktZ2F0ZXdheS1zZXJ2aWNlIiwiZXhwIjoxNzg3Njk1MjAwfQ.Z4zP9w3MecFeZEcX5sUt4YdhxS6skp25fbKOv8-_gPU"

MAJOR_INDICES = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50", "SENSEX"]

@st.cache_data(ttl=3600)
def load_fno_symbols():
    symbols = []
    github_urls = [
        "https://raw.githubusercontent.com/meokgmblog/STRIKES-POSITION-BUILDER/main/FNO%20ALL%20LIST.txt",
        "https://raw.githubusercontent.com/meokgmblog/STRIKES-POSITION-BUILDER/main/FNO_ALL_LIST.txt",
        "https://raw.githubusercontent.com/meokgmblog/STRIKES-POSITION-BUILDER/main/FNO%20all%20list.txt"
    ]

    for url in github_urls:
        try:
            res = requests.get(url, timeout=5)
            if res.status_code == 200 and res.text.strip():
                lines = res.text.splitlines()
                symbols = [line.strip().upper() for line in lines if line.strip()]
                if len(symbols) > 5:
                    break
        except Exception:
            continue

    if not symbols:
        possible_filenames = ["FNO ALL LIST.txt", "FNO_ALL_LIST.txt", "FNO all list.txt", "fno_all_list.txt"]
        for fname in possible_filenames:
            if os.path.exists(fname):
                try:
                    with open(fname, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                        symbols = [line.strip().upper() for line in lines if line.strip()]
                        if len(symbols) > 5:
                            break
                except Exception:
                    continue

    return sorted(list(set(MAJOR_INDICES + symbols)))

fno_symbol_list = load_fno_symbols()

# ================================================================
# SIDEBAR CONTROLS
# ================================================================
st.sidebar.markdown("### 📊 Command Center")
st.sidebar.markdown("Configure your live market feed parameters below.")

default_index = fno_symbol_list.index("NIFTY") if "NIFTY" in fno_symbol_list else 0
SYMBOL_INPUT = st.sidebar.selectbox(
    "Select F&O Symbol",
    options=fno_symbol_list,
    index=default_index
).strip().upper()

NUM_STRIKES_BOUND = st.sidebar.slider("Strikes Range (± ATM)", min_value=2, max_value=12, value=2)

st.sidebar.markdown("---")
st.sidebar.info("💡 **Pro Tip:** Use mouse drag on the chart to pan across sessions or scroll to zoom in.")

# Main Dashboard Title Header
st.markdown(f"## 📈 {SYMBOL_INPUT} Live Position Builder")
st.markdown("Real-time intraday open interest dynamics mapped directly against spot price action.")

# ================================================================
# API HELPERS & MASTER FETCHERS
# ================================================================
def get_headers(token):
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {token.strip()}",
        "Cache-Control": "no-cache",
    }

def upstox_get(url, token, params=None):
    try:
        response = requests.get(url, headers=get_headers(token), params=params, timeout=10)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network Error: {str(e)}")

    if response.status_code != 200:
        raise RuntimeError(f"Upstox HTTP {response.status_code}: {response.text[:200]}")

    data = response.json()
    if data.get("status") != "success":
        raise RuntimeError(f"Upstox API Error: {data}")

    return data

@st.cache_data(ttl=3600)
def fetch_upstox_master_instruments():
    nse_url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.csv.gz"
    bse_url = "https://assets.upstox.com/market-quote/instruments/exchange/BSE.csv.gz"
    try:
        df_nse = pd.DataFrame()
        df_bse = pd.DataFrame()

        try:
            res_nse = requests.get(nse_url, timeout=20)
            if res_nse.status_code == 200:
                with gzip.open(io.BytesIO(res_nse.content), "rt") as f:
                    df_nse = pd.read_csv(f)
        except Exception:
            pass

        try:
            res_bse = requests.get(bse_url, timeout=20)
            if res_bse.status_code == 200:
                with gzip.open(io.BytesIO(res_bse.content), "rt") as f:
                    df_bse = pd.read_csv(f)
        except Exception:
            pass

        if df_nse.empty and df_bse.empty:
            raise Exception("Failed to fetch master csv files for NSE and BSE.")

        df = pd.concat([df_nse, df_bse], ignore_index=True)
        df.columns = [c.lower() for c in df.columns]
        return df
    except Exception as e:
        raise RuntimeError(f"Master file download error: {str(e)}")

def resolve_stock_instruments(master_df, symbol):
    key_col = "instrument_key" if "instrument_key" in master_df.columns else "instrument_token"
    sym_col = "trading_symbol" if "trading_symbol" in master_df.columns else "tradingsymbol"
    type_col = "instrument_type" if "instrument_type" in master_df.columns else "segment"
    name_col = "name" if "name" in master_df.columns else ("asset_symbol" if "asset_symbol" in master_df.columns else sym_col)
    strike_col = "strike" if "strike" in master_df.columns else "strike_price"

    clean_symbol = symbol.strip().upper()

    spot_mask = (
        (master_df[sym_col].astype(str).str.upper() == clean_symbol) |
        (master_df[sym_col].astype(str).str.upper() == f"{clean_symbol}-EQ") |
        (master_df[name_col].astype(str).str.upper() == clean_symbol)
    ) & (
        master_df[type_col].astype(str).str.upper().str.contains("EQ|EQUITY|INDEX|NSE_EQ|BSE_INDEX", regex=True)
    )

    spot_rows = master_df[spot_mask]

    if spot_rows.empty:
        spot_rows = master_df[
            master_df[sym_col].astype(str).str.upper().str.startswith(clean_symbol) &
            master_df[type_col].astype(str).str.upper().str.contains("EQ|EQUITY|INDEX|NSE_EQ|BSE_INDEX", regex=True)
        ]

    if spot_rows.empty:
        raise RuntimeError(f"Could not find Equity Spot instrument for '{clean_symbol}'.")

    spot_key = spot_rows.iloc[0][key_col]

    opts_mask = (
        (master_df[name_col].astype(str).str.upper() == clean_symbol) |
        (master_df[sym_col].astype(str).str.upper().str.startswith(clean_symbol))
    ) & master_df[type_col].astype(str).str.upper().str.contains("OPTSTK|OPTIDX|CE|PE", regex=True)

    opts = master_df[opts_mask].copy()
    if opts.empty:
        raise RuntimeError(f"No active options contracts found for {clean_symbol}.")

    opts["expiry_dt"] = pd.to_datetime(opts["expiry"], errors="coerce")
    opts = opts.dropna(subset=["expiry_dt"])
    today = pd.Timestamp(datetime.now().date())

    active_opts = opts[opts["expiry_dt"].dt.date >= today.date()].sort_values("expiry_dt")
    if active_opts.empty:
        raise RuntimeError(f"No upcoming unexpired options contracts found for {clean_symbol}.")

    nearest_expiry = active_opts.iloc[0]["expiry_dt"]
    matching_opts = active_opts[active_opts["expiry_dt"] == nearest_expiry].copy()

    return spot_key, matching_opts, key_col, sym_col, strike_col

def get_intraday_candles(token, instrument_key):
    if not instrument_key:
        return pd.DataFrame()

    encoded_key = quote(str(instrument_key), safe="")
    url = f"https://api.upstox.com/v3/historical-candle/intraday/{encoded_key}/minutes/{INTERVAL}"

    try:
        res = upstox_get(url, token)
        candles = res.get("data", {}).get("candles", [])
        if not candles:
            return pd.DataFrame()

        df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_convert(IST).dt.tz_localize(None)
        return df.sort_values("timestamp").reset_index(drop=True)
    except Exception:
        return pd.DataFrame()

def filter_market_hours(df):
    if df.empty:
        return df
    df = df.copy()
    df["time"] = df["timestamp"].dt.time
    start = datetime.strptime(MARKET_START, "%H:%M").time()
    end = datetime.strptime(MARKET_END, "%H:%M").time()
    df = df[(df["time"] >= start) & (df["time"] <= end)].copy()
    return df.drop(columns=["time"]).reset_index(drop=True)

def fetch_option_data_parallel(token, option_rows, key_col):
    keys = [row[key_col] for _, row in option_rows.iterrows()]

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(
            executor.map(
                lambda key: filter_market_hours(get_intraday_candles(token, key)),
                keys,
            )
        )

    combined_df = None
    for opt_data in results:
        if not opt_data.empty:
            opt_sub = opt_data[["timestamp", "oi"]].copy()
            if combined_df is None:
                combined_df = opt_sub.rename(columns={"oi": "sum_oi"})
            else:
                combined_df = pd.merge(combined_df, opt_sub, on="timestamp", how="outer")
                combined_df["sum_oi"] = combined_df["sum_oi"].fillna(0) + combined_df["oi"].fillna(0)
                combined_df.drop(columns=["oi"], inplace=True)

    return combined_df

# ================================================================
# CALCULATIONS & POSITION BUILDER
# ================================================================
def calculate_position_builder(price_df, ce_df, pe_df):
    clean_price = price_df[["timestamp", "open", "high", "low", "close"]].copy()

    opts_merged = pd.merge(ce_df, pe_df, on="timestamp", how="inner").sort_values("timestamp")
    df = pd.merge(clean_price, opts_merged, on="timestamp", how="inner").sort_values("timestamp")

    if df.empty:
        raise RuntimeError("Timestamp alignment mismatch across spot and option market feeds.")

    df["ce_oi_diff"] = df["ce_oi"].diff(1).fillna(0)
    df["pe_oi_diff"] = df["pe_oi"].diff(1).fillna(0)

    df["net_oi_change"] = df["pe_oi_diff"] - df["ce_oi_diff"]

    max_val = max(abs(df["net_oi_change"].min()), abs(df["net_oi_change"].max()), 1)
    df["position_builder_scaled"] = (df["net_oi_change"] / max_val) * 100

    return df

# ================================================================
# STACKED SUBPLOTS CHART RENDERER
# ================================================================
def render_chart(df, symbol, expiry_str):
    last_price = df["close"].iloc[-1]
    last_time = df["timestamp"].iloc[-1].strftime("%H:%M:%S")

    # Calculate price extremes to keep candles in the top ~75% of the canvas
    price_min = df["low"].min()
    price_max = df["high"].max()
    price_span = price_max - price_min if price_max != price_min else 1.0

    y1_min = price_min - (price_span * 0.35)
    y1_max = price_max + (price_span * 0.05)

    # Fixed intraday range from 09:00 to 15:45 for the current session date
    current_date = df["timestamp"].dt.date.iloc[-1]
    xaxis_range = [
        pd.Timestamp(f"{current_date} {MARKET_START}:00"),
        pd.Timestamp(f"{current_date} {MARKET_END}:00")
    ]

    fig = go.Figure()

    # 1. Position Builder Histogram Trace (Y2 Axis - Shifted to Bottom)
    values = df["position_builder_scaled"].fillna(0)
    colors = ["#089981" if v >= 0 else "#f23645" for v in values]

    # Custom date-time string formatting for the tooltip
    formatted_times = df["timestamp"].dt.strftime("%B %d, %Y at %I:%M %p")

    fig.add_trace(
        go.Bar(
            x=df["timestamp"],
            y=values,
            customdata=formatted_times,
            name="Net OI Scaled",
            marker_color=colors,
            marker_line_width=0,
            opacity=0.8,
            yaxis="y2",
            hovertemplate="%{customdata}<extra></extra>",  # Shows ONLY the Date and Time
        )
    )

    # 2. Candlestick Price Trace (Y1 Axis) - Regular Solid Filled Candles
    fig.add_trace(
        go.Candlestick(
            x=df["timestamp"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name=symbol,
            increasing=dict(
                line=dict(color="#089981", width=1),
                fillcolor="#089981"
            ),
            decreasing=dict(
                line=dict(color="#f23645", width=1),
                fillcolor="#f23645"
            ),
            whiskerwidth=1,
            yaxis="y1",
            hoverinfo="none",  # Hides candlestick OHLC values from tooltip
        )
    )

    fig.update_layout(
        title=dict(
            text=f"<b>{symbol} Spot</b> (3m) | Last: {last_price:.2f} | Updated: {last_time} IST | {expiry_str}",
            font=dict(size=14, color="#d1d4dc", family="Plus Jakarta Sans"),
            x=0.01,
            y=0.98,
        ),
        template="plotly_dark",
        paper_bgcolor="#161b22",
        plot_bgcolor="#161b22",
        height=480,
        margin=dict(l=20, r=20, t=45, b=40),
        showlegend=False,
        hovermode="x",
        dragmode="pan",
        # Unified X-Axis placed at the bottom below histogram with fixed session range
        xaxis=dict(
            type="date",
            range=xaxis_range,
            side="bottom",  # Forces time labels to the very bottom
            showspikes=True,
            spikemode="across",
            spikesnap="cursor",
            spikecolor="#ffffff",
            spikethickness=1,
            spikedash="dash",
            gridcolor="#2a2e39",
            rangebreaks=[dict(bounds=["sat", "mon"])],
            rangeslider=dict(visible=False),
        ),
        # Primary Y-Axis (Candlesticks Upper Canvas)
        yaxis=dict(
            title="Price",
            range=[y1_min, y1_max],
            showspikes=True,
            spikemode="across",
            spikesnap="cursor",
            spikecolor="#ffffff",
            spikethickness=1,
            spikedash="dash",
            gridcolor="#2a2e39",
            side="right",
        ),
        # Secondary Y-Axis (Histogram Floor)
        yaxis2=dict(
            title="",
            overlaying="y",
            side="left",
            range=[-110, 480],
            showgrid=False,
            showticklabels=False,
            zeroline=True,
            zerolinecolor="#363a45",
            zerolinewidth=1,
        ),
    )

    config = {
        "scrollZoom": True,
        "displayModeBar": True,
        "modeBarButtonsToAdd": ["pan2d"],
        "modeBarButtonsToRemove": ["autoscale2d"],  # Prevents autoscale layout breaking
        "displaylogo": False,
    }

    st.plotly_chart(fig, use_container_width=True, config=config)

# ================================================================
# MAIN EXECUTION ENGINE
# ================================================================
try:
    with st.spinner("Downloading market metadata..."):
        master_df = fetch_upstox_master_instruments()

    spot_key, opts_df, key_col, sym_col, strike_col = resolve_stock_instruments(master_df, SYMBOL_INPUT)

    spot_df = filter_market_hours(get_intraday_candles(ACCESS_TOKEN, spot_key))
    if spot_df.empty:
        st.error(f"No intraday candle data returned for {SYMBOL_INPUT} spot.")
        st.stop()

    last_close = spot_df["close"].iloc[-1]

    opts_df["strike_num"] = pd.to_numeric(opts_df[strike_col], errors="coerce")
    unique_strikes = sorted(opts_df["strike_num"].dropna().unique())

    if len(unique_strikes) > 1:
        strike_diffs = np.diff(unique_strikes)
        step_size = float(np.median(strike_diffs))
    else:
        step_size = 5.0

    atm_strike = round(last_close / step_size) * step_size
    min_stk = atm_strike - (NUM_STRIKES_BOUND * step_size)
    max_stk = atm_strike + (NUM_STRIKES_BOUND * step_size)

    atm_opts = opts_df[(opts_df["strike_num"] >= min_stk) & (opts_df["strike_num"] <= max_stk)].copy()
    if atm_opts.empty:
        atm_opts = opts_df

    ce_opts = atm_opts[atm_opts[sym_col].astype(str).str.endswith("CE")]
    pe_opts = atm_opts[atm_opts[sym_col].astype(str).str.endswith("PE")]

    with st.spinner(f"Scouting {len(ce_opts) + len(pe_opts)} contracts around ATM ({atm_strike})..."):
        ce_df = fetch_option_data_parallel(ACCESS_TOKEN, ce_opts, key_col)
        pe_df = fetch_option_data_parallel(ACCESS_TOKEN, pe_opts, key_col)

    if ce_df is not None and pe_df is not None:
        ce_df = ce_df.rename(columns={"sum_oi": "ce_oi"}).sort_values("timestamp").ffill().dropna()
        pe_df = pe_df.rename(columns={"sum_oi": "pe_oi"}).sort_values("timestamp").ffill().dropna()

        builder_df = calculate_position_builder(spot_df, ce_df, pe_df)
        exp_date_str = opts_df.iloc[0]["expiry_dt"].strftime("%b-%d")

        # UI Metrics Panel Display before Rendering Chart
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(label="Spot Price", value=f"{last_close:.2f}")
        with col2:
            st.metric(label="ATM Strike", value=f"{atm_strike:.0f}")
        with col3:
            st.metric(label="Expiry Date", value=exp_date_str)
        with col4:
            net_val = builder_df["position_builder_scaled"].iloc[-1]
            st.metric(label="Net OI Momentum", value=f"{net_val:.1f}%")

        render_chart(builder_df, SYMBOL_INPUT, f"Expiry: {exp_date_str}")
    else:
        st.error("Failed to fetch concurrent open interest data for strikes.")

except Exception as err:
    st.error(f"Execution Error: {str(err)}")

# ================================================================
# AUTO-REFRESH TRIGGER (Silent Clock-Aligned Rerun)
# ================================================================
now = datetime.now(IST)
market_end_time = datetime.strptime(MARKET_END, "%H:%M").time()

if now.time() >= market_end_time:
    st.info("🔒 Market hours ended (Frozen after 3:45 PM). Data and chart are locked for the session.")
else:
    total_seconds = now.hour * 3600 + now.minute * 60 + now.second
    market_start_seconds = 9 * 3600 + 0 * 60
    remainder = (total_seconds - market_start_seconds) % 180
    seconds_to_wait = 180 - remainder if remainder != 0 else 180
    sleep_time = seconds_to_wait + 3

    time.sleep(sleep_time)
    st.rerun()
