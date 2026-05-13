# data_fetcher.py  v3
# FX pairs      : Bloomberg user inputs only (week open + close)
# DXY / Yields / Brent / Gold : Gemini AI search (editable review before generating)
# yfinance      : Brent 5-day series for chart + 52-week ranges (supplementary only)

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ── Date helpers ───────────────────────────────────────────────────────────────

def last_completed_week():
    """Monday and Friday of the most recently completed Mon–Fri week."""
    today = datetime.now()
    days_since_fri = (today.weekday() - 4) % 7
    if days_since_fri == 0:
        days_since_fri = 7
    last_fri = today - timedelta(days=days_since_fri)
    last_mon = last_fri - timedelta(days=4)
    return last_mon, last_fri

# ── Math / format helpers ──────────────────────────────────────────────────────

def pct_change(current, prior):
    if prior and prior != 0:
        return round((current - prior) / prior * 100, 2)
    return 0.0

def bps_change(current, prior):
    if prior is not None:
        return round((current - prior) * 100, 1)
    return 0.0

def range_pct(val, low, high):
    if low is None or high is None or high == low:
        return 50
    return round(max(0, min(100, (val - low) / (high - low) * 100)), 1)

def fmt_chg(val, unit='%', invert=False, suffix='WoW'):
    """Format a change value as coloured HTML span."""
    if val is None:
        return '<span class="grey">N/A</span>'
    is_up = val > 0
    is_red = is_up if not invert else not is_up
    color = 'red' if is_red else 'green'
    arrow = '▲' if is_up else '▼'
    if unit == 'bps':
        return f'<span class="{color}">{arrow} {abs(val):.0f} bps {suffix}</span>'
    return f'<span class="{color}">{arrow} {abs(val):.2f}% {suffix}</span>'

# ── yfinance helpers (supplementary only) ─────────────────────────────────────

def _yf_download(ticker, start, end):
    try:
        df = yf.download(
            ticker,
            start=start.strftime('%Y-%m-%d'),
            end=(end + timedelta(days=2)).strftime('%Y-%m-%d'),
            interval='1d', progress=False, auto_adjust=True
        )
        if not df.empty and isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if not df.empty:
            df = df[df.index.date >= start.date()]
            df = df[df.index.date <= end.date()]
        return df
    except Exception:
        return pd.DataFrame()

def _safe_series(df, n=5):
    try:
        closes = df['Close'].dropna().tolist()
        result = []
        for i in range(n):
            if i < len(closes):
                result.append(float(closes[i]))
            else:
                result.append(result[-1] if result else None)
        return result
    except Exception:
        return [None] * n

def get_52w(ticker):
    try:
        df = yf.download(ticker, period='1y', interval='1d', progress=False, auto_adjust=True)
        if df.empty:
            return None, None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return float(df['Low'].min()), float(df['High'].max())
    except Exception:
        return None, None

def fetch_brent_5d(week_start, week_end):
    """5-day Brent close series for the Brent chart (yfinance)."""
    df = _yf_download('BZ=F', week_start, week_end)
    series = _safe_series(df, 5)
    return [round(v, 2) if v else None for v in series]

def fetch_supplementary_52w(selected_sections):
    """
    Fetch 52-week ranges for non-FX instruments (yfinance).
    Returns dict: {instrument: (lo52, hi52)}
    Only fetches what's needed based on selected_sections.
    """
    tickers = {}
    if selected_sections.get('rates'):
        tickers['us10y'] = '^TNX'
        tickers['in10y'] = 'GIND10YR=X'
    if selected_sections.get('oil'):
        tickers['brent'] = 'BZ=F'
    if selected_sections.get('gold'):
        tickers['gold'] = 'GC=F'
    # DXY always if currency section shown
    if any(selected_sections.get(p) for p in ['usdinr', 'eurinr', 'gbpinr', 'jpyinr', 'cnhinr']):
        tickers['dxy'] = 'DX-Y.NYB'

    ranges = {}
    for key, ticker in tickers.items():
        lo, hi = get_52w(ticker)
        ranges[key] = (lo, hi)
    return ranges

# ── Bloomberg FX processor ─────────────────────────────────────────────────────

# Pair display labels and denominator notes
PAIR_META = {
    'usdinr': {'label': 'USD/INR',          'note': 'RBI Ref Rate: {rbi_ref}'},
    'eurinr': {'label': 'EUR/INR',          'note': ''},
    'gbpinr': {'label': 'GBP/INR',          'note': ''},
    'jpyinr': {'label': 'JPY/INR (per 100 JPY)', 'note': ''},
    'cnhinr': {'label': 'CNH/INR',          'note': ''},
}

ALL_FX_PAIRS = ['usdinr', 'eurinr', 'gbpinr', 'jpyinr', 'cnhinr']

def process_bloomberg_fx(fx_inputs, selected_fx_pairs):
    """
    Build FX section of data dict from Bloomberg week-open / week-close inputs.

    fx_inputs: {
        'usdinr': {'open': 84.20, 'close': 84.65},
        'eurinr': {'open': 91.50, 'close': 91.80},
        ...
    }
    selected_fx_pairs: list of pair keys that the user selected

    Returns: partial data dict with all FX fields.
    """
    data = {}

    for pair in ALL_FX_PAIRS:
        if pair not in selected_fx_pairs:
            # Mark as excluded so html_generator can skip
            data[f'{pair}_excluded'] = True
            continue

        inp = fx_inputs.get(pair, {})
        open_p = inp.get('open')
        close_p = inp.get('close')

        if open_p is None or close_p is None or open_p == 0:
            data[f'{pair}_close']   = 'N/A'
            data[f'{pair}_open']    = 'N/A'
            data[f'{pair}_wow']     = 'N/A'
            data[f'{pair}_wow_val'] = 0
            data[f'{pair}_52w_lo']  = 'N/A'
            data[f'{pair}_52w_hi']  = 'N/A'
            data[f'{pair}_52w_pct'] = 50
            continue

        wow_val = pct_change(close_p, open_p)
        # Positive pct = INR weaker vs that currency = red (invert=False)
        wow_html = fmt_chg(wow_val)

        data[f'{pair}_close']   = round(close_p, 2)
        data[f'{pair}_open']    = round(open_p, 2)
        data[f'{pair}_wow']     = wow_html
        data[f'{pair}_wow_val'] = wow_val
        # 52w ranges filled later from supplementary fetch
        data[f'{pair}_52w_lo']  = 'N/A'
        data[f'{pair}_52w_hi']  = 'N/A'
        data[f'{pair}_52w_pct'] = 50

    # RBI ref rate proxy (USD/INR close − 0.28)
    usdinr_close = fx_inputs.get('usdinr', {}).get('close')
    data['rbi_ref'] = round(usdinr_close - 0.28, 4) if usdinr_close else 'N/A'

    # INR weakness tracker (vs G3 + CNH)
    weak_against = []
    for pair in ['eurinr', 'gbpinr', 'jpyinr', 'cnhinr']:
        if pair in selected_fx_pairs and data.get(f'{pair}_wow_val', 0) > 0:
            weak_against.append(pair.replace('inr', '').upper())
    data['inr_weak_against'] = weak_against

    data['selected_fx_pairs'] = selected_fx_pairs
    return data

# ── Build full weekly data dict ────────────────────────────────────────────────

def build_weekly_data(fx_data, ai_data, week_start_dt, week_end_dt,
                      selected_sections, brent_5d=None, ranges_52w=None):
    """
    Assemble the full data dict from:
      fx_data       : output of process_bloomberg_fx()
      ai_data       : Gemini-fetched + user-reviewed market data
      week_start_dt : datetime
      week_end_dt   : datetime
      selected_sections : {section_key: bool | list}
      brent_5d      : [float|None] * 5 from fetch_brent_5d()
      ranges_52w    : {instrument: (lo, hi)} from fetch_supplementary_52w()

    ai_data expected keys:
        dxy_close, dxy_wow_val
        us10y_close, us10y_wow_val  (bps)
        in10y_close, in10y_wow_val  (bps)
        brent_close, brent_wow_val
        gold_usd,    gold_wow_val
        fed_rate (str), rbi_rate (str)
    """
    ranges_52w = ranges_52w or {}

    data = {
        'mode': 'weekly',
        'week_start':    week_start_dt.strftime('%b %d'),
        'week_end':      week_end_dt.strftime('%b %d, %Y'),
        'week_num':      week_start_dt.isocalendar()[1],
        'year':          week_end_dt.year,
        'generated_at':  datetime.now().strftime('%a %d %b %Y, %H:%M IST'),
        'day_labels':    [(week_start_dt + timedelta(days=i)).strftime('%a %d')
                          for i in range(5)],
        'selected_sections': selected_sections,
    }

    # ── Merge Bloomberg FX ──
    data.update(fx_data)

    # ── Apply 52w ranges to FX pairs (from supplementary yfinance) ──
    # Note: yfinance gives USD-based cross ranges which are indicative only for INR pairs
    # We skip for now; ranges are 'N/A' by default from process_bloomberg_fx

    # ── DXY ──
    dxy_c   = ai_data.get('dxy_close')
    dxy_wow = ai_data.get('dxy_wow_val', 0.0)
    dxy_lo, dxy_hi = ranges_52w.get('dxy', (None, None))
    data['dxy_close']   = round(dxy_c, 2) if dxy_c else 'N/A'
    data['dxy_wow']     = fmt_chg(dxy_wow, invert=True) if dxy_c else 'N/A'
    data['dxy_wow_val'] = dxy_wow
    data['dxy_52w_lo']  = round(dxy_lo, 2) if dxy_lo else 'N/A'
    data['dxy_52w_hi']  = round(dxy_hi, 2) if dxy_hi else 'N/A'
    data['dxy_52w_pct'] = range_pct(dxy_c, dxy_lo, dxy_hi) if dxy_c and dxy_lo else 50

    # ── Yields ──
    us_c    = ai_data.get('us10y_close')
    us_wow  = ai_data.get('us10y_wow_val', 0.0)   # bps
    in_c    = ai_data.get('in10y_close')
    in_wow  = ai_data.get('in10y_wow_val', 0.0)   # bps
    us_lo, us_hi = ranges_52w.get('us10y', (None, None))
    in_lo, in_hi = ranges_52w.get('in10y', (None, None))

    data['us10y_close']   = round(us_c, 2) if us_c else 'N/A'
    data['us10y_wow']     = fmt_chg(us_wow, unit='bps') if us_c else 'N/A'
    data['us10y_wow_val'] = us_wow
    data['us10y_52w_lo']  = round(us_lo, 2) if us_lo else 'N/A'
    data['us10y_52w_hi']  = round(us_hi, 2) if us_hi else 'N/A'
    data['us10y_52w_pct'] = range_pct(us_c, us_lo, us_hi) if us_c and us_lo else 50

    data['in10y_close']   = round(in_c, 2) if in_c else 'N/A'
    data['in10y_wow']     = fmt_chg(in_wow, unit='bps') if in_c else 'N/A'
    data['in10y_wow_val'] = in_wow
    data['in10y_52w_lo']  = round(in_lo, 2) if in_lo else 'N/A'
    data['in10y_52w_hi']  = round(in_hi, 2) if in_hi else 'N/A'
    data['in10y_52w_pct'] = range_pct(in_c, in_lo, in_hi) if in_c and in_lo else 50

    if us_c and in_c:
        spread     = round(in_c - us_c, 2)
        spread_chg = round(in_wow - us_wow, 0)
        data['yield_spread'] = f"{spread:.2f}% · {spread_chg:+.0f} bps WoW"
    else:
        data['yield_spread'] = 'N/A'

    # ── Brent ──
    b_c    = ai_data.get('brent_close')
    b_wow  = ai_data.get('brent_wow_val', 0.0)
    b5d    = brent_5d or [None] * 5
    b_lo, b_hi = ranges_52w.get('brent', (None, None))
    data['brent_close']   = round(b_c, 2) if b_c else 'N/A'
    data['brent_wow']     = fmt_chg(b_wow, invert=False) if b_c else 'N/A'
    data['brent_wow_val'] = b_wow
    data['brent_5d']      = b5d
    valid_b5d = [v for v in b5d if v]
    data['brent_wk_high'] = max(valid_b5d) if valid_b5d else (b_c or 'N/A')
    data['brent_52w_lo']  = round(b_lo, 2) if b_lo else 'N/A'
    data['brent_52w_hi']  = round(b_hi, 2) if b_hi else 'N/A'

    # ── Gold (international XAU/USD only) ──
    g_c   = ai_data.get('gold_usd')
    g_wow = ai_data.get('gold_wow_val', 0.0)
    data['gold_usd']      = f"${g_c:,.0f}" if g_c else 'N/A'
    data['gold_wow']      = fmt_chg(g_wow, invert=False) if g_c else 'N/A'
    data['gold_wow_val']  = g_wow

    # ── Policy rates ──
    data['fed_rate'] = ai_data.get('fed_rate', 'N/A')
    data['rbi_rate'] = ai_data.get('rbi_rate', 'N/A')

    # ── Programmatic INR insight (overridden by AI commentary if available) ──
    weak_against  = data.get('inr_weak_against', [])
    usd_wow_val   = data.get('usdinr_wow_val', 0)
    dxy_wow_v     = data.get('dxy_wow_val', 0)
    if len(weak_against) == 4 and usd_wow_val > 0 and dxy_wow_v < -0.5:
        data['inr_insight'] = (
            f"INR weakened vs the full G3 basket — not a pure USD-strength story. "
            f"DXY fell {abs(dxy_wow_v):.1f}% WoW yet INR did not recover. "
            f"India-specific pressures independently weighing."
        )
    elif usd_wow_val > 0.3:
        pairs_str = 'all G3' if len(weak_against) == 4 else \
                    ', '.join(weak_against) if weak_against else 'mixed'
        data['inr_insight'] = (
            f"INR under pressure vs USD ({usd_wow_val:+.2f}% WoW). "
            f"G3 moves: weaker vs {pairs_str}. Watch DXY and oil next week."
        )
    else:
        data['inr_insight'] = (
            f"INR broadly stable vs USD ({usd_wow_val:+.2f}% WoW). "
            f"Mixed G3 moves. No dominant directional bias this week."
        )

    return data
