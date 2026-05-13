# macro_generator.py  v6
#
# Model tiers (based on available free-tier quota):
#   INTENSIVE  gemini-2.5-flash → gemini-2.5-flash-lite
#              Heavy reasoning: commentary, story search+structure
#              ~20 RPD each — use sparingly
#
#   MEDIUM     gemini-2.5-flash-lite → gemini-3.1-flash-lite
#              Step-B structuring (prose→JSON)
#              20 + 500 RPD
#
#   LIGHT      gemini-3.1-flash-lite → gemini-2.5-flash-lite
#              Data lookups, one-liners, week-ahead
#              500 RPD first — preserves INTENSIVE budget

import json, re, time
from google import genai
from google.genai import types

# ── Model tiers ────────────────────────────────────────────────────────────────

INTENSIVE = ['gemini-2.5-flash',      'gemini-2.5-flash-lite']
MEDIUM    = ['gemini-2.5-flash-lite', 'gemini-3.1-flash-lite']
LIGHT     = ['gemini-3.1-flash-lite', 'gemini-2.5-flash-lite']

SKIP_ERRORS = ('429', '404', 'quota', 'limit: 0', 'not found',
               'not supported', 'RESOURCE_EXHAUSTED')

def _call_tier(api_key, tier_models, prompt, use_search=False):
    """
    Try each model in tier_models order (google-genai SDK).
    Skips on quota/availability errors; stops on auth/other errors.
    Returns (text, model_used, elapsed_s, error_or_None).
    """
    client = genai.Client(api_key=api_key)

    tools  = [types.Tool(google_search=types.GoogleSearch())] if use_search else []
    config = types.GenerateContentConfig(tools=tools) if tools else None

    all_errors = []
    for model_name in tier_models:
        try:
            t0 = time.time()
            r  = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            )
            return r.text, model_name, round(time.time() - t0, 1), None
        except Exception as e:
            err = str(e)
            all_errors.append(f'[{model_name}] {err[:140]}')
            if any(x in err for x in SKIP_ERRORS):
                continue
            break   # auth / prompt error — stop immediately

    return None, None, 0, '\n'.join(all_errors)

# ── JSON helpers ───────────────────────────────────────────────────────────────

def extract_json(text):
    if not text:
        return None
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*',     '', text)
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    for sc, ec in [('[', ']'), ('{', '}')]:
        s, e = text.find(sc), text.rfind(ec)
        if s != -1 and e != -1:
            try:
                return json.loads(text[s:e + 1])
            except Exception:
                pass
    return None

def fallback_stories(n=3, reason=''):
    body = f'Gemini error: {reason}' if reason else \
           'Macro stories unavailable — add manually before distributing.'
    return [{'tag': 'Data Unavailable',
             'headline': 'Macro stories could not be fetched — add manually',
             'body': body,
             'inr_relevance': '📌 INR: Update this section with relevant macro context.',
             'links': [], 'color': 'blue'}] * n

# ── Two-step helpers ───────────────────────────────────────────────────────────

def _step_a(api_key, search_prompt, fallback_prompt, tier=None):
    """Step A: search+summarise → raw prose. Falls back to no-search if quota fails."""
    t = tier or INTENSIVE
    text, model, elapsed, err = _call_tier(api_key, t, search_prompt, use_search=True)
    if not err and text:
        return text, f'{model}+search ({elapsed}s)', None
    search_err = err or 'empty response'
    text2, model2, elapsed2, err2 = _call_tier(api_key, t, fallback_prompt, use_search=False)
    if not err2 and text2:
        return text2, f'{model2} no-search ({elapsed2}s)', f'Search failed: {search_err}'
    return None, '', f'Search: {search_err} | Plain: {err2}'

def _step_b(api_key, prose, template, tier=None):
    """Step B: prose → structured JSON via plain call."""
    t = tier or MEDIUM
    prompt = template.replace('{{PROSE}}', prose or 'No content available.')
    text, model, elapsed, err = _call_tier(api_key, t, prompt, use_search=False)
    if err:
        return None, f'Step B ({elapsed}s): {err}'
    result = extract_json(text)
    if result is None:
        return None, f'Step B JSON parse failed. Output:\n{(text or "")[:400]}'
    return result, None

# ── AI market data fetch (LIGHT tier — burns 500 RPD budget, not 20) ──────────

def get_ai_market_data(api_key, week_start, week_end, selected_sections):
    """
    Use gemini-3.1-flash-lite with search to fetch DXY, yields, Brent, Gold,
    Fed Funds, RBI Repo for the specified week.

    Returns (dict_of_values, error_or_None).
    dict keys: dxy_close, dxy_wow_val, us10y_close, us10y_wow_val,
               in10y_close, in10y_wow_val, brent_close, brent_wow_val,
               gold_usd, gold_wow_val, fed_rate, rbi_rate
    wow_val for yields = bps.  wow_val for others = %.
    """
    fields = []
    if selected_sections.get('rates', True):
        fields += ['us10y', 'in10y', 'fed_rate', 'rbi_rate']
    # DXY always useful if any FX is shown
    fields.append('dxy')
    if selected_sections.get('oil', True):
        fields.append('brent')
    if selected_sections.get('gold', True):
        fields.append('gold')

    fields_str = '\n'.join({
        'dxy':      '- DXY (US Dollar Index): Friday close level and % change WoW',
        'us10y':    '- US 10-Year Treasury yield: Friday close (%) and WoW change in bps',
        'in10y':    '- India 10-Year G-Sec yield (CCIL/FIMMDA published rate): Friday close (%) and WoW change in bps',
        'brent':    '- Brent Crude: Friday close price USD and WoW % change',
        'gold':     '- Gold XAU/USD: Friday spot price USD and WoW % change',
        'fed_rate': '- Fed Funds Rate: current target range (string, e.g. "4.25-4.50%")',
        'rbi_rate': '- RBI Repo Rate: current rate (string, e.g. "6.00%")',
    }[f] for f in fields if f in ('dxy','us10y','in10y','brent','gold','fed_rate','rbi_rate'))

    search_prompt = f"""Search for the following market data for the week ending {week_end}
(week of {week_start} to {week_end}):

{fields_str}

For India 10Y, specifically look for CCIL or FIMMDA published government bond yields.
WoW change = Friday close minus previous Friday close.
Use null for any value you cannot find with high confidence.

Return ONLY a valid JSON object, no markdown fences, no explanation:
{{
  "dxy_close": 101.5,
  "dxy_wow_val": -0.8,
  "us10y_close": 4.42,
  "us10y_wow_val": -5,
  "in10y_close": 6.83,
  "in10y_wow_val": -3,
  "brent_close": 65.4,
  "brent_wow_val": -2.1,
  "gold_usd": 3285.0,
  "gold_wow_val": 1.2,
  "fed_rate": "4.25-4.50%",
  "rbi_rate": "6.00%"
}}"""

    fallback_prompt = f"""Using your training knowledge, provide approximate market data for the week
ending {week_end}. Return ONLY valid JSON (no fences) with these keys:
dxy_close, dxy_wow_val, us10y_close, us10y_wow_val (bps), in10y_close, in10y_wow_val (bps),
brent_close, brent_wow_val, gold_usd, gold_wow_val, fed_rate (str), rbi_rate (str).
Use null if unknown."""

    # Use LIGHT tier — preserves INTENSIVE budget; this is data lookup not reasoning
    text, model, elapsed, err = _call_tier(api_key, LIGHT, search_prompt, use_search=True)
    if err or not text:
        # Fallback: no-search on LIGHT
        text, model, elapsed, err2 = _call_tier(api_key, LIGHT, fallback_prompt, use_search=False)
        if err2 or not text:
            return {}, f'AI market data fetch failed:\n{err}\n{err2}'

    result = extract_json(text)
    if not result or not isinstance(result, dict):
        return {}, f'AI market data JSON parse failed. Output:\n{(text or "")[:300]}'

    # Coerce to float / keep strings for rate labels
    clean = {}
    for k, v in result.items():
        if k in ('fed_rate', 'rbi_rate'):
            clean[k] = str(v) if v else 'N/A'
        else:
            try:
                clean[k] = float(v) if v is not None else None
            except (TypeError, ValueError):
                clean[k] = None

    return clean, None

# ── Commentary (INTENSIVE, no search) ─────────────────────────────────────────

def generate_snapshot_commentary(api_key, data):
    """
    Theme bar, mood tag, per-section narrative + per-pair one-liners, INR insight.
    Uses INTENSIVE tier (gemini-2.5-flash) — best model for nuanced analysis.
    Returns (dict, error_or_None).
    """
    mode = data.get('mode', 'weekly')

    def v(k):
        val = data.get(k, 0)
        return val if isinstance(val, (int, float)) else 0

    if mode == 'weekly':
        # Build context only for sections that exist in data
        ctx_lines = [
            f"Week: {data.get('week_start','')} to {data.get('week_end','')} "
            f"(Week {data.get('week_num','')})"
        ]
        sel = data.get('selected_sections', {})
        fx_pairs = sel.get('fx_pairs', [])

        if 'usdinr' in fx_pairs:
            ctx_lines.append(
                f"USD/INR: close {data.get('usdinr_close','N/A')} "
                f"open {data.get('usdinr_open','N/A')} "
                f"WoW {v('usdinr_wow_val'):+.2f}%"
            )
        if data.get('dxy_close') != 'N/A':
            ctx_lines.append(f"DXY: {data.get('dxy_close','N/A')}  WoW {v('dxy_wow_val'):+.2f}%")
        for pair in ['eurinr', 'gbpinr', 'jpyinr', 'cnhinr']:
            if pair in fx_pairs and data.get(f'{pair}_close') != 'N/A':
                lbl = {'eurinr':'EUR/INR','gbpinr':'GBP/INR',
                       'jpyinr':'JPY/INR (per 100)','cnhinr':'CNH/INR'}[pair]
                ctx_lines.append(
                    f"{lbl}: {data.get(f'{pair}_close','N/A')}  WoW {v(f'{pair}_wow_val'):+.2f}%"
                )
        if sel.get('rates'):
            ctx_lines.append(
                f"US 10Y: {data.get('us10y_close','N/A')}%  WoW {v('us10y_wow_val'):+.1f} bps"
            )
            ctx_lines.append(
                f"India 10Y: {data.get('in10y_close','N/A')}%  WoW {v('in10y_wow_val'):+.1f} bps"
            )
            ctx_lines.append(
                f"Fed: {data.get('fed_rate','N/A')}  RBI: {data.get('rbi_rate','N/A')}"
            )
        if sel.get('oil'):
            ctx_lines.append(
                f"Brent: ${data.get('brent_close','N/A')}  WoW {v('brent_wow_val'):+.2f}%"
            )
        if sel.get('gold'):
            ctx_lines.append(
                f"Gold XAU/USD: {data.get('gold_usd','N/A')}  WoW {v('gold_wow_val'):+.2f}%"
            )
        ctx = '\n'.join(ctx_lines)

        # Build per-pair oneliner fields for JSON output
        pair_fields = ''
        for pair in fx_pairs:
            lbl = {'usdinr':'usdinr','eurinr':'eurinr','gbpinr':'gbpinr',
                   'jpyinr':'jpyinr','cnhinr':'cnhinr'}.get(pair, pair)
            pair_fields += (
                f'  "{lbl}_sub": "MAX 12 WORDS. Terse one-liner for {lbl.upper()} move this week. '
                f'Cite actual macro event.  e.g. \'Hawkish Fed + strong NFP kept dollar bid\'",\n'
            )

        prompt = f"""You are a senior FX analyst at Standard Chartered India FM Sales.

Verified market data for week {data.get('week_num','')}
({data.get('week_start','')}–{data.get('week_end','')}):
{ctx}

Using your knowledge of global macro events during this specific week, write professional
client-facing commentary. Name actual events (central bank meetings, data releases,
geopolitical events) that explain these price moves. Use ONLY the numbers above.

Return ONLY a valid JSON object, no markdown fences:
{{
  "theme": "1–2 sentences on 2–3 biggest events with key numbers. End with INR takeaway.",
  "mood_tag": "EXACTLY 2–3 ALL-CAPS keywords separated by ·  e.g. FOMC SPLIT · OIL SHOCK · INR PRESSURE",
  "dxy_sub": "MAX 12 WORDS. What drove DXY this week.",
{pair_fields}  "us10y_sub": "MAX 12 WORDS. What drove US yields.",
  "in10y_sub": "MAX 12 WORDS. What drove India 10Y.",
  "fed_sub": "MAX 10 WORDS starting ■.",
  "rbi_sub": "MAX 10 WORDS starting ■.",
  "brent_sub": "MAX 12 WORDS. Key driver for Brent move.",
  "gold_sub": "MAX 8 WORDS. Key driver for gold.",
  "inr_insight": "2–3 sentences. Is INR weakness USD-driven or broad? Name 1-2 India-specific factors. End: Watch: [specific trigger] next week.",
  "chart_callout": "6–9 words: single most important INR chart observation"
}}
Return ONLY valid JSON."""

    else:
        # Daily mode — keep simple
        ctx = (
            f"Date: {data.get('date','')}\n"
            f"USD/INR: {data.get('usdinr_close','N/A')}  24h: {v('usdinr_chg_val'):+.2f}%\n"
            f"DXY: {data.get('dxy_close','N/A')}  24h: {v('dxy_chg_val'):+.2f}%\n"
        )
        prompt = f"""You are a senior FX analyst at Standard Chartered India FM Sales.
Daily data for {data.get('date','')}:
{ctx}
Return ONLY valid JSON, no fences:
{{"theme":"1 sentence dominant driver + key number.",
  "mood_tag":"2–3 ALL-CAPS keywords separated by ·",
  "usdinr_sub":"1 line: key level and driver",
  "dxy_sub":"1 line: DXY direction and INR relevance",
  "inr_insight":"2 sentences: broad USD or INR-specific? What to watch.",
  "chart_callout":"5–7 words: key observation"}}"""

    text, model, elapsed, err = _call_tier(api_key, INTENSIVE, prompt, use_search=False)
    if err:
        return {}, f'Commentary ({elapsed}s): {err}'
    result = extract_json(text)
    if result and isinstance(result, dict):
        return result, None
    return {}, f'Commentary JSON parse failed ({elapsed}s). Output: {(text or "")[:300]}'

# ── Weekly stories (INTENSIVE search → MEDIUM structure) ──────────────────────

def get_weekly_stories(api_key, week_start, week_end, week_num, data=None):
    """Two-step: search+summarise → 3 story cards. Returns (list, error_or_None)."""

    search_p = f"""Search Google News and financial sources for the 3 most important macro
events from the week of {week_start} to {week_end} (Week {week_num}) that affected
global FX markets, especially USD/INR and INR vs G3 (EUR, GBP, JPY, CNH).

Focus on: central bank decisions, major data surprises (GDP, CPI, PCE, jobs, PMI),
geopolitical events affecting oil, major risk events.

For EACH of the 3 events write a paragraph covering:
- Exact date and what happened
- Key numbers (rate levels, beats/misses, bps changes)
- Immediate market reaction (FX, bonds, oil)
- Direct impact on USD/INR or INR vs G3"""

    fallback_p = f"""Using your training knowledge, write 3 detailed paragraphs about the
most significant global macro events from the week of {week_start} to {week_end}
(Week {week_num}) that affected India FX markets. Include actual numbers, dates,
central bank actions, and market reactions."""

    # Step A: INTENSIVE with search
    prose, source, err = _step_a(api_key, search_p, fallback_p, tier=INTENSIVE)
    if not prose:
        return fallback_stories(3, reason=err or 'No prose from Step A'), err

    verified = ''
    if data:
        verified = f"""
VERIFIED MARKET DATA (use ONLY these price levels — do not substitute different values):
- USD/INR: {data.get('usdinr_close','N/A')}
- DXY: {data.get('dxy_close','N/A')}
- EUR/INR: {data.get('eurinr_close','N/A')}  GBP/INR: {data.get('gbpinr_close','N/A')}
- US 10Y: {data.get('us10y_close','N/A')}%  India 10Y: {data.get('in10y_close','N/A')}%
- Brent: ${data.get('brent_close','N/A')}  Gold XAU/USD: {data.get('gold_usd','N/A')}
- Fed Funds: {data.get('fed_rate','N/A')}  RBI Repo: {data.get('rbi_rate','N/A')}"""

    struct = f"""You are a senior FX analyst at Standard Chartered.
{verified}
Macro events summary for {week_start}–{week_end}:

{{{{PROSE}}}}

Convert into exactly 3 story cards as a JSON array. Be specific — actual numbers, dates,
central bank names. Return ONLY valid JSON array, no fences:
[
  {{
    "tag": "Category · Date  e.g. Central Bank · {week_start[:6]}",
    "headline": "Max 15 words with key numbers",
    "body": "2–3 sentences. Wrap key numbers in <strong> tags.",
    "inr_relevance": "📌 INR: specific impact on USD/INR or INR vs G3 with price levels.",
    "links": [{{"text": "→ Source name", "url": "https://real-url.com"}}],
    "color": "red for central bank/hawkish | amber for geopolitics/oil | blue for macro data"
  }}
]
All 3 must be distinct events."""

    # Step B: MEDIUM tier
    result, struct_err = _step_b(api_key, prose, struct, tier=MEDIUM)
    if struct_err:
        return fallback_stories(3, reason=struct_err), struct_err
    if isinstance(result, list) and result:
        import urllib.parse
        for story in result:
            for link in story.get('links', []):
                url = link.get('url', '')
                if not url or 'source.com' in url or url == '#':
                    q = urllib.parse.quote(f"{story.get('headline', '')} {week_start}")
                    link['url'] = f"https://news.google.com/search?q={q}"
        return result[:3], None
    return fallback_stories(3, reason='Structure returned empty'), 'Structure returned empty'

# ── Week ahead (LIGHT search → LIGHT structure) ────────────────────────────────

def get_week_ahead(api_key, current_week_end):
    """Two-step on LIGHT tier: search upcoming events → calendar JSON."""

    search_p = f"""Search for the 4–6 most important macro events for the week
AFTER {current_week_end} relevant to India FX markets.
Include: central bank meetings (with rate expectations), major data (GDP, CPI, jobs, PMI),
geopolitical deadlines. For each: exact date, event name, expectation, INR relevance."""

    fallback_p = f"""List 4–6 important macro events for the week after {current_week_end}
relevant to India FX. Include dates, event names, and what to watch for."""

    # Both steps use LIGHT tier — week-ahead is lighter than story research
    prose, source, err = _step_a(api_key, search_p, fallback_p, tier=LIGHT)
    if not prose:
        return [], err

    struct = """Convert into a calendar JSON array.

{{PROSE}}

Return ONLY a valid JSON array, no markdown fences:
[{"date":"Day DD e.g. Mon 5","impact":"HIGH or MED",
  "event":"Event name and what to watch","url":"https://source.com"}]

impact=HIGH for central bank meetings and potential surprises. MED for routine releases."""

    result, err2 = _step_b(api_key, prose, struct, tier=LIGHT)
    if isinstance(result, list):
        import urllib.parse
        for evt in result:
            url = evt.get('url', '')
            if not url or 'source.com' in url or url == '#':
                q = urllib.parse.quote(evt.get('event', 'macro event week ahead'))
                evt['url'] = f"https://news.google.com/search?q={q}"
        return result[:6], err2
    return [], err2

# ── Daily stories (INTENSIVE search → MEDIUM structure) ───────────────────────

def get_daily_stories(api_key, date_str):
    """Two-step: search today → 2 story cards. Returns (list, error_or_None)."""

    search_p = f"""Search for the 2 most important macro events from the last 24 hours
(around {date_str}) that affected global FX and India assets.
Include numbers, market reactions, and source names. Write 2 detailed paragraphs."""

    fallback_p = f"""Describe the 2 most significant macro events on {date_str}
for India FX markets. Include specific numbers and market reactions."""

    prose, source, err = _step_a(api_key, search_p, fallback_p, tier=INTENSIVE)
    if not prose:
        return fallback_stories(2, reason=err or 'No prose'), err

    struct = f"""Convert into 2 daily story cards.

{{{{PROSE}}}}

Return ONLY a valid JSON array, no markdown fences:
[{{"tag":"Category · {date_str}","headline":"Max 15 words with numbers",
   "body":"2–3 sentences. Key numbers in <strong> tags.",
   "inr_relevance":"📌 INR: specific impact with price level.",
   "links":[{{"text":"→ Source","url":"https://real-url.com"}}],
   "color":"red | amber | blue"}}]"""

    result, err2 = _step_b(api_key, prose, struct, tier=MEDIUM)
    if isinstance(result, list) and result:
        return result[:2], err2
    return fallback_stories(2, reason=err2 or 'No result'), err2

# ── FX approximate rates (LIGHT, for pre-filling Bloomberg inputs) ─────────────

def get_fx_approximate_rates(api_key, week_start, week_end, selected_fx_pairs):
    """
    Search for approximate INR FX rates for the given week to seed Bloomberg inputs.
    Uses LIGHT tier (gemini-3.1-flash-lite + search) — burns 500 RPD budget.

    Returns (dict {pair: {'open': float, 'close': float}}, error_or_None).
    Values are indicative only — user must verify with actual Bloomberg prints.
    """
    PAIR_DESC = {
        'usdinr': 'USD/INR spot (Indian rupee per US dollar)',
        'eurinr': 'EUR/INR (rupee per euro — EURUSD × USDINR)',
        'gbpinr': 'GBP/INR (rupee per pound — GBPUSD × USDINR)',
        'jpyinr': 'JPY/INR as INR per 100 JPY (USDINR / USDJPY × 100)',
        'cnhinr': 'CNH/INR (rupee per offshore yuan — USDINR / USDCNH)',
    }
    pairs_text = '\n'.join(
        f'- {PAIR_DESC[p]}'
        for p in ['usdinr', 'eurinr', 'gbpinr', 'jpyinr', 'cnhinr']
        if p in selected_fx_pairs
    )

    prompt = f"""Search for INR FX rates for the week of {week_start} to {week_end}.

Find the Monday opening rate and Friday closing rate for each pair below.
Use RBI reference rates, Reuters, or Bloomberg data where available.

Pairs needed:
{pairs_text}

Return ONLY a valid JSON object, no markdown fences, no explanation:
{{
  "usdinr": {{"open": 84.20, "close": 84.65}},
  "eurinr": {{"open": 91.50, "close": 91.80}},
  "gbpinr": {{"open": 107.20, "close": 107.90}},
  "jpyinr": {{"open": 56.40, "close": 56.20}},
  "cnhinr": {{"open": 11.55, "close": 11.60}}
}}
Include only the requested pairs. Use null if genuinely unavailable.
All values must be floats rounded to 2 decimal places."""

    text, model, elapsed, err = _call_tier(api_key, LIGHT, prompt, use_search=True)
    if err or not text:
        return {}, f'FX rates fetch failed ({elapsed}s): {err}'

    result = extract_json(text)
    if not result or not isinstance(result, dict):
        return {}, f'FX rates JSON parse failed. Raw: {(text or "")[:200]}'

    clean = {}
    for pair in selected_fx_pairs:
        entry = result.get(pair)
        if not isinstance(entry, dict):
            continue
        try:
            o = entry.get('open')
            c = entry.get('close')
            if o is not None and c is not None:
                clean[pair] = {'open': round(float(o), 2), 'close': round(float(c), 2)}
        except (TypeError, ValueError):
            pass

    return clean, (None if clean else 'No valid rates returned from Gemini')
